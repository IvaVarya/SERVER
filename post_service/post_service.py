import logging
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
import jwt
from functools import wraps
from werkzeug.utils import secure_filename
from prometheus_flask_exporter import PrometheusMetrics
from schemas import PostSchema
from flask_cors import CORS

app = Flask(__name__)

# Настройка CORS
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger с использованием Flask-RESTX
api = Api(app, version='1.0', title='Post Service API', description='API для управления постами, лайками и комментариями')

# Конфигурация приложения
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')  # Из переменной окружения
app.config['UPLOAD_FOLDER'] = '/app/uploads'

db = SQLAlchemy(app)

# Модель поста
class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos = db.relationship('Photo', backref='post', lazy=True)

# Модель фотографии
class Photo(db.Model):
    __tablename__ = 'photos'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# Модель лайка
class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Модель комментария
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Создание таблиц и папки для загрузок
with app.app_context():
    db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

# Декоратор для проверки токена
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

# Модели для Swagger
post_model = api.model('PostModel', {
    'text': fields.String(required=False, description='Текст поста'),
})

like_model = api.model('LikeModel', {
    'post_id': fields.Integer(required=True, description='ID поста')
})

comment_model = api.model('CommentModel', {
    'post_id': fields.Integer(required=True, description='ID поста'),
    'text': fields.String(required=True, description='Текст комментария')
})

# Создание поста с загрузкой фотографий
@api.route('/posts')
class CreatePost(Resource):
    @token_required
    @api.expect(post_model)
    def post(self, user_id):
        # Проверяем, пришел ли запрос в формате JSON или multipart/form-data
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '')
        else:
            data = request.form
            text = data.get('text', '')

        # Валидация текста
        schema = PostSchema()
        errors = schema.validate({'text': text})
        if errors:
            logger.warning(f'Validation errors: {errors}')
            return {'message': 'Ошибка валидации', 'errors': errors}, 400

        # Получение файлов (если есть)
        files = request.files.getlist('photos')

        try:
            # Создание поста
            post = Post(user_id=user_id, text=text)
            db.session.add(post)
            db.session.commit()

            # Обработка загруженных фотографий
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

# Получение поста
@api.route('/posts/<int:post_id>')
class GetPost(Resource):
    def get(self, post_id):
        post = Post.query.get_or_404(post_id)
        return {
            'id': post.id,
            'user_id': post.user_id,
            'text': post.text,
            'created_at': post.created_at.isoformat(),
            'photos': [{'id': p.id, 'filename': p.filename} for p in post.photos]
        }

# Получение постов по user_ids
@api.route('/posts/by_users')
class GetPostsByUsers(Resource):
    def get(self):
        try:
            user_ids_str = request.args.get('user_ids', '')
            if not user_ids_str:
                return {'message': 'Параметр user_ids обязателен'}, 400
            
            # Преобразуем строки в целые числа, игнорируя некорректные значения
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
        except Exception as e:
            logger.error(f'Error in GetPostsByUsers: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Удаление поста
@api.route('/posts/<int:post_id>')
class DeletePost(Resource):
    @token_required
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

    # Добавляем обработку OPTIONS для preflight-запросов
    def options(self, post_id):
        return {'message': 'OK'}, 200

# Добавление лайка
@api.route('/posts/like')
class LikePost(Resource):
    @token_required
    @api.expect(like_model)
    def post(self, user_id):
        data = request.get_json()
        post_id = data['post_id']

        if not Post.query.get(post_id):
            return {'message': 'Пост не найден'}, 404

        if Like.query.filter_by(user_id=user_id, post_id=post_id).first():
            logger.warning(f'User {user_id} already liked post {post_id}')
            return {'message': 'Вы уже поставили лайк этому посту.'}, 400

        try:
            like = Like(user_id=user_id, post_id=post_id)
            db.session.add(like)
            db.session.commit()
            logger.info(f'Post {post_id} liked by user_id: {user_id}')
            return {'message': 'Лайк успешно поставлен!'}, 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error liking post: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Удаление лайка
@api.route('/posts/unlike')
class UnlikePost(Resource):
    @token_required
    @api.expect(like_model)
    def post(self, user_id):
        data = request.get_json()
        post_id = data['post_id']

        like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
        if not like:
            logger.warning(f'Like not found for user_id: {user_id}, post_id: {post_id}')
            return {'message': 'Лайк не найден.'}, 404

        try:
            db.session.delete(like)
            db.session.commit()
            logger.info(f'Post {post_id} unliked by user_id: {user_id}')
            return {'message': 'Лайк успешно убран!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error unliking post: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Добавление комментария
@api.route('/posts/comment')
class CommentPost(Resource):
    @token_required
    @api.expect(comment_model)
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
            logger.info(f'Comment added to post {post_id} by user_id: {user_id}')
            return {'message': 'Комментарий успешно добавлен!', 'comment_id': comment.id}, 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error adding comment: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Получение комментариев
@api.route('/posts/<int:post_id>/comments')
class GetComments(Resource):
    def get(self, post_id):
        if not Post.query.get(post_id):
            return {'message': 'Пост не найден'}, 404
        comments = Comment.query.filter_by(post_id=post_id).all()
        return jsonify([{
            'id': c.id,
            'user_id': c.user_id,
            'text': c.text,
            'created_at': c.created_at.isoformat()
        } for c in comments])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)