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
api = Api(app, version='1.0', title='Post Service API', 
          description='API для управления постами, лайками и комментариями. '
                      'Все защищенные эндпоинты требуют заголовок Authorization с Bearer-токеном.')

# Конфигурация приложения
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = '/app/uploads'

db = SQLAlchemy(app)

# Модели базы данных (без изменений)
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

# Создание таблиц и папки для загрузок
with app.app_context():
    db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

# Декоратор для проверки токена (без изменений)
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

# Модели для Swagger с подробными описаниями
post_model = api.model('PostModel', {
    'text': fields.String(required=False, description='Текст поста (опционально). Максимальная длина - 5000 символов.'),
    # Указываем, что можно загружать файлы через multipart/form-data
}, description='Модель для создания поста. Поддерживает как JSON, так и multipart/form-data с полем "photos" для загрузки изображений.')

photo_model = api.model('Photo', {
    'id': fields.Integer(description='ID фотографии'),
    'filename': fields.String(description='Имя файла фотографии')
})

post_response_model = api.model('PostResponse', {
    'id': fields.Integer(description='ID поста'),
    'user_id': fields.Integer(description='ID пользователя, создавшего пост'),
    'text': fields.String(description='Текст поста'),
    'created_at': fields.String(description='Дата создания поста в формате ISO'),
    'photos': fields.List(fields.Nested(photo_model), description='Список загруженных фотографий')
})

like_model = api.model('LikeModel', {
    'post_id': fields.Integer(required=True, description='ID поста, который нужно лайкнуть/удалить лайк')
}, description='Модель для добавления или удаления лайка.')

comment_model = api.model('CommentModel', {
    'post_id': fields.Integer(required=True, description='ID поста, к которому добавляется комментарий'),
    'text': fields.String(required=True, description='Текст комментария. Максимальная длина - 2000 символов.')
}, description='Модель для добавления комментария.')

comment_response_model = api.model('CommentResponse', {
    'id': fields.Integer(description='ID комментария'),
    'user_id': fields.Integer(description='ID пользователя, оставившего комментарий'),
    'text': fields.String(description='Текст комментария'),
    'created_at': fields.String(description='Дата создания комментария в формате ISO')
})

# Создание поста с загрузкой фотографий
@api.route('/posts')
class CreatePost(Resource):
    @token_required
    @api.expect(post_model, validate=True)
    @api.doc(description='Создает новый пост. Поддерживает текст и загрузку фотографий. '
                         'Принимает либо JSON с полем "text", либо multipart/form-data с полями "text" (опционально) и "photos" (файлы). '
                         'Требуется заголовок Authorization с Bearer-токеном.',
             responses={201: 'Пост успешно создан', 400: 'Ошибка валидации', 401: 'Токен отсутствует или неверный', 500: 'Ошибка сервера'})
    def post(self, user_id):
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '')
        else:
            data = request.form
            text = data.get('text', '')

        schema = PostSchema()
        errors = schema.validate({'text': text})
        if errors:
            logger.warning(f'Validation errors: {errors}')
            return {'message': 'Ошибка валидации', 'errors': errors}, 400

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

# Получение поста
@api.route('/posts/<int:post_id>')
class GetPost(Resource):
    @api.doc(description='Получает информацию о посте по его ID.',
             responses={200: 'Успешно', 404: 'Пост не найден'})
    @api.marshal_with(post_response_model)
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
# Получение постов по user_ids
@api.route('/posts/by_users')
class GetPostsByUsers(Resource):
    @api.doc(description='Получает список постов для указанных пользователей. '
                         'Параметр "user_ids" передается в query string как строка с ID пользователей, разделенными запятыми. '
                         'Пример запроса: GET /posts/by_users?user_ids=1,2,3',
             params={'user_ids': {
                 'description': 'Список ID пользователей, разделенных запятыми (например, "1,2,3"). Обязательный параметр.',
                 'required': True,
                 'type': 'string',
                 'example': '1,2,3'
             }},
             responses={
                 200: 'Успешно возвращен список постов',
                 400: 'Параметр user_ids отсутствует или содержит только неверные значения',
                 500: 'Ошибка сервера'
             })
    @api.marshal_with(post_response_model, as_list=True)
    def get(self):
        try:
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
        except Exception as e:
            logger.error(f'Error in GetPostsByUsers: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Удаление поста
@api.route('/posts/<int:post_id>')
class DeletePost(Resource):
    @token_required
    @api.doc(description='Удаляет пост по его ID. Доступно только автору поста. '
                         'Требуется заголовок Authorization с Bearer-токеном.',
             responses={200: 'Пост успешно удален', 401: 'Токен отсутствует или неверный', 
                        404: 'Пост не найден', 500: 'Ошибка сервера'})
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

    @api.doc(description='Обработка preflight-запросов для CORS.')
    def options(self, post_id):
        return {'message': 'OK'}, 200

# Добавление лайка
@api.route('/posts/like')
class LikePost(Resource):
    @token_required
    @api.expect(like_model, validate=True)
    @api.doc(description='Добавляет лайк к посту. Требуется JSON с полем "post_id". '
                         'Требуется заголовок Authorization с Bearer-токеном.',
             responses={201: 'Лайк успешно поставлен', 400: 'Лайк уже существует', 
                        401: 'Токен отсутствует или неверный', 404: 'Пост не найден', 500: 'Ошибка сервера'})
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
    @api.expect(like_model, validate=True)
    @api.doc(description='Удаляет лайк с поста. Требуется JSON с полем "post_id". '
                         'Требуется заголовок Authorization с Bearer-токеном.',
             responses={200: 'Лайк успешно убран', 401: 'Токен отсутствует или неверный', 
                        404: 'Лайк не найден', 500: 'Ошибка сервера'})
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
    @api.expect(comment_model, validate=True)
    @api.doc(description='Добавляет комментарий к посту. Требуется JSON с полями "post_id" и "text". '
                         'Требуется заголовок Authorization с Bearer-токеном.',
             responses={201: 'Комментарий успешно добавлен', 401: 'Токен отсутствует или неверный', 
                        404: 'Пост не найден', 500: 'Ошибка сервера'})
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
    @api.doc(description='Получает список комментариев для поста по его ID.',
             responses={200: 'Успешно', 404: 'Пост не найден'})
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)