import logging
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields, Namespace
import jwt
from functools import wraps
from werkzeug.utils import secure_filename
from prometheus_flask_exporter import PrometheusMetrics
from flask_cors import CORS

app = Flask(__name__)

# Настройка CORS
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger
api = Api(app, version='1.0', title='Post Service API', 
          description='API для управления постами, лайками и комментариями.')

# Отдельный Namespace для внутренних эндпоинтов (не отображается в Swagger)
internal_ns = Namespace('internal', description='Внутренние эндпоинты (не для внешнего использования)')
api.add_namespace(internal_ns)

# Конфигурация приложения
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = '/app/uploads'

db = SQLAlchemy(app)

# Модели базы данных
class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos = db.relationship('Photo', backref='post', lazy=True)

class Photo(db.Model):
    __tablename__ = 'photos'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

# Декораторы
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Токен отсутствует!'}, 401
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            kwargs['user_id'] = data['user_id']
        except jwt.InvalidTokenError:
            logger.warning('Token is invalid!')
            return {'message': 'Неверный токен!'}, 401
        return f(*args, **kwargs)
    return decorated

def internal_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        internal_key = request.headers.get('X-Internal-Key')
        if internal_key != os.getenv('INTERNAL_KEY', 'internal-secret'):
            logger.warning('Invalid internal key!')
            return {'message': 'Доступ запрещен'}, 403
        return f(*args, **kwargs)
    return decorated

# Модели для Swagger
post_model = api.model('PostModel', {
    'text': fields.String(required=False, description='Текст поста (опционально).'),
})
photo_model = api.model('Photo', {
    'id': fields.Integer(description='ID фотографии'),
    'filename': fields.String(description='Имя файла фотографии')
})
post_response_model = api.model('PostResponse', {
    'id': fields.Integer(description='ID поста'),
    'user_id': fields.Integer(description='ID пользователя'),
    'text': fields.String(description='Текст поста'),
    'created_at': fields.String(description='Дата создания в формате ISO'),
    'photos': fields.List(fields.Nested(photo_model), description='Список фотографий')
})
like_model = api.model('LikeModel', {
    'post_id': fields.Integer(required=True, description='ID поста для лайка')
})
comment_model = api.model('CommentModel', {
    'post_id': fields.Integer(required=True, description='ID поста'),
    'text': fields.String(required=True, description='Текст комментария')
})
comment_response_model = api.model('CommentResponse', {
    'id': fields.Integer(description='ID комментария'),
    'user_id': fields.Integer(description='ID пользователя'),
    'text': fields.String(description='Текст комментария'),
    'created_at': fields.String(description='Дата создания в формате ISO')
})

# Публичные эндпоинты
@api.route('/posts')
class CreatePost(Resource):
    @token_required
    @api.expect(post_model, validate=True)
    @api.doc(responses={201: 'Пост создан', 400: 'Ошибка валидации', 401: 'Токен неверный', 500: 'Ошибка сервера'})
    def post(self, user_id):
        text = request.form.get('text', '') if not request.is_json else request.get_json().get('text', '')
        files = request.files.getlist('photos')
        try:
            post = Post(user_id=user_id, text=text)
            db.session.add(post)
            db.session.commit()

            for file in files:
                if file:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    photo = Photo(post_id=post.id, filename=filename)
                    db.session.add(photo)
            db.session.commit()

            logger.info(f'Post created by user_id: {user_id}, post_id: {post.id}')
            return {'message': 'Пост успешно создан!', 'post_id': post.id}, 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creating post: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/posts/<int:post_id>')
class PostResource(Resource):
    @api.marshal_with(post_response_model)
    @api.doc(responses={200: 'Успешно', 404: 'Пост не найден', 401: 'Неверный токен (если передан)'})
    def get(self, post_id):
        token = request.headers.get('Authorization')
        if token:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            try:
                jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            except jwt.InvalidTokenError:
                logger.warning(f'Invalid token provided for GET /posts/{post_id}')
                return {'message': 'Неверный токен!'}, 401

        post = Post.query.get_or_404(post_id)
        return {
            'id': post.id,
            'user_id': post.user_id,
            'text': post.text,
            'created_at': post.created_at.isoformat(),
            'photos': [{'id': p.id, 'filename': p.filename} for p in post.photos]
        }

    @token_required
    @api.doc(responses={200: 'Пост удален', 401: 'Токен неверный', 404: 'Пост не найден', 500: 'Ошибка сервера'})
    def delete(self, user_id, post_id):
        post = Post.query.filter_by(id=post_id, user_id=user_id).first()
        if not post:
            logger.warning(f'Post not found for user_id: {user_id}, post_id: {post_id}')
            return {'message': 'Пост не найден.'}, 404
        try:
            Photo.query.filter_by(post_id=post_id).delete()
            Like.query.filter_by(post_id=post_id).delete()
            Comment.query.filter_by(post_id=post_id).delete()
            db.session.delete(post)
            db.session.commit()
            logger.info(f'Post deleted by user_id: {user_id}, post_id: {post_id}')
            return {'message': 'Пост успешно удален!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error deleting post: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/posts/like')
class LikePost(Resource):
    @token_required
    @api.expect(like_model, validate=True)
    def post(self, user_id):
        data = request.get_json()
        post_id = data['post_id']
        if not Post.query.get(post_id):
            return {'message': 'Пост не найден'}, 404
        if Like.query.filter_by(user_id=user_id, post_id=post_id).first():
            return {'message': 'Вы уже поставили лайк.'}, 400
        try:
            like = Like(user_id=user_id, post_id=post_id)
            db.session.add(like)
            db.session.commit()
            return {'message': 'Лайк успешно поставлен!'}, 201
        except Exception as e:
            db.session.rollback()
            return {'message': 'Ошибка сервера'}, 500

@api.route('/posts/unlike')
class UnlikePost(Resource):
    @token_required
    @api.expect(like_model, validate=True)
    def post(self, user_id):
        data = request.get_json()
        post_id = data['post_id']
        like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
        if not like:
            return {'message': 'Лайк не найден.'}, 404
        try:
            db.session.delete(like)
            db.session.commit()
            return {'message': 'Лайк успешно убран!'}, 200
        except Exception as e:
            db.session.rollback()
            return {'message': 'Ошибка сервера'}, 500

@api.route('/posts/comment')
class CommentPost(Resource):
    @token_required
    @api.expect(comment_model, validate=True)
    def post(self, user_id):
        data = request.get_json()
        post_id = data['post_id']
        text = data['text']
        if not Post.query.get(post_id):
            return {'message': 'Пост не найден'}, 404
        try:
            comment = Comment(user_id=user_id, post_id=post_id, text=text)
            db.session.add(comment)
            db.session.commit()
            return {'message': 'Комментарий успешно добавлен!', 'comment_id': comment.id}, 201
        except Exception as e:
            db.session.rollback()
            return {'message': 'Ошибка сервера'}, 500

@api.route('/posts/<int:post_id>/comments')
class GetComments(Resource):
    @api.marshal_with(comment_response_model, as_list=True)
    def get(self, post_id):
        if not Post.query.get(post_id):
            return {'message': 'Пост не найден'}, 404
        comments = Comment.query.filter_by(post_id=post_id).all()
        return [{
            'id': c.id,
            'user_id': c.user_id,
            'text': c.text,
            'created_at': c.created_at.isoformat()
        } for c in comments]

# Новый эндпоинт для получения постов пользователя
@api.route('/posts/user/<int:user_id>')
class GetPostsByUser(Resource):
    @api.marshal_with(post_response_model, as_list=True)
    @api.doc(responses={200: 'Успешно', 404: 'Посты не найдены'})
    def get(self, user_id):
        posts = Post.query.filter_by(user_id=user_id).order_by(Post.created_at.desc()).all()
        if not posts:
            logger.info(f'No posts found for user_id: {user_id}')
            return {'message': 'Посты не найдены'}, 404
        return [{
            'id': post.id,
            'user_id': post.user_id,
            'text': post.text,
            'created_at': post.created_at.isoformat(),
            'photos': [{'id': p.id, 'filename': p.filename} for p in post.photos]
        } for post in posts]
    
@api.route('/posts/all')
class GetAllPosts(Resource):
    @api.marshal_with(post_response_model, as_list=True)
    @api.doc(security='Bearer Auth')
    @token_required
    @api.doc(responses={200: 'Успешно', 404: 'Посты не найдены', 500: 'Ошибка сервера'})
    def get(self, user_id):
        try:
            # Фильтруем посты по user_id из токена
            posts = Post.query.filter_by(user_id=user_id).order_by(Post.created_at.desc()).all()
            if not posts:
                logger.info(f"No posts found for user_id: {user_id}")
                return {'message': 'Посты не найдены'}, 404
            
            # Формируем ответ
            response = [{
                'id': post.id,
                'user_id': post.user_id,
                'text': post.text or '',  # Обрабатываем случай, если text=None
                'created_at': post.created_at.isoformat(),  # Предполагаем, что created_at всегда есть
                'photos': [{'id': p.id, 'filename': p.filename} for p in post.photos]
            } for post in posts]
            
            logger.info(f"Successfully retrieved {len(posts)} posts for user_id: {user_id}")
            return response, 200
        
        except Exception as e:
            # Логируем точную ошибку для диагностики
            logger.error(f"Error in GetAllPosts for user_id {user_id}: {str(e)}")
            return {'message': 'Ошибка сервера', 'error': str(e)}, 500

# Внутренний эндпоинт
@internal_ns.route('/posts/by_users')
class GetPostsByUsersInternal(Resource):
    @internal_only
    @api.marshal_with(post_response_model, as_list=True)
    def get(self):
        user_ids_str = request.args.get('user_ids', '')
        if not user_ids_str:
            return {'message': 'Параметр user_ids обязателен'}, 400
        
        user_ids = []
        for uid in user_ids_str.split(','):
            try:
                user_ids.append(int(uid))
            except ValueError:
                continue
        
        if not user_ids:
            return {'message': 'Нет валидных user_ids'}, 400

        posts = Post.query.filter(Post.user_id.in_(user_ids)).order_by(Post.created_at.desc()).all()
        return [{
            'id': post.id,
            'user_id': post.user_id,
            'text': post.text,
            'created_at': post.created_at.isoformat(),
            'photos': [{'id': p.id, 'filename': p.filename} for p in post.photos]
        } for post in posts]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)