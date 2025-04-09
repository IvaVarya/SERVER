import logging
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
from flask_restx import Api, Resource, fields
from prometheus_flask_exporter import PrometheusMetrics
from schemas import UserSchema, ProfileSchema
from flask_cors import CORS
import os
import json
from minio import Minio
from minio.error import S3Error

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metrics = PrometheusMetrics(app)

api = Api(app, version='1.0', title='User Service API', 
          description='API для управления пользователями и их профилями')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'profile-photos')
MINIO_SECURE = False

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def init_minio():
    try:
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
            logger.info(f"Создана корзина {MINIO_BUCKET} в MinIO")
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"]
                }
            ]
        }
        minio_client.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
        logger.info(f"Установлена публичная политика для {MINIO_BUCKET}")
    except S3Error as e:
        logger.error(f"Ошибка инициализации MinIO: {e}")
        raise

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    gender = db.Column(db.String(20))
    country = db.Column(db.String(50))
    city = db.Column(db.String(50))
    birth_date = db.Column(db.Date)
    profile_photo = db.Column(db.String(200))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def init_db():
    with app.app_context():
        db.create_all()
        init_minio()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = db.session.get(User, data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
            return f(current_user=current_user, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 401
    return decorated

user_model = api.model('User', {
    'first_name': fields.String(required=True),
    'last_name': fields.String(required=True),
    'login': fields.String(required=True),
    'password': fields.String(required=True),
    'confirm_password': fields.String(required=True),
    'email': fields.String(required=True)
})

profile_model = api.model('Profile', {
    'first_name': fields.String(required=False),
    'last_name': fields.String(required=False),
    'gender': fields.String(required=False),
    'country': fields.String(required=False),
    'city': fields.String(required=False),
    'birth_date': fields.String(required=False, description='Date in YYYY-MM-DD format'),
    'profile_photo': fields.String(required=False)
})

user_response_model = api.model('UserResponse', {
    'id': fields.Integer,
    'first_name': fields.String,
    'last_name': fields.String,
    'login': fields.String,
    'email': fields.String,
    'registration_date': fields.DateTime,
    'gender': fields.String,
    'country': fields.String,
    'city': fields.String,
    'birth_date': fields.String(description='Date in YYYY-MM-DD format'),
    'profile_photo': fields.String
})

search_result_model = api.model('SearchResult', {
    'id': fields.Integer(description='ID пользователя'),
    'login': fields.String(description='Логин пользователя'),
    'first_name': fields.String(description='Имя'),
    'last_name': fields.String(description='Фамилия'),
    'profile_photo': fields.String(description='URL фото профиля')  # Добавляем поле для фото
})

@api.route('/register')
class Register(Resource):
    @api.expect(user_model)
    @api.response(201, 'User registered successfully', user_response_model)
    def post(self):
        data = request.get_json()
        schema = UserSchema()
        errors = schema.validate(data)
        if errors:
            return {'message': 'Ошибка валидации', 'errors': errors}, 400

        if data['password'] != data['confirm_password']:
            return {'message': 'Пароли не совпадают.'}, 400

        if User.query.filter_by(login=data['login']).first():
            return {'message': 'Пользователь с таким логином уже существует.'}, 400

        if User.query.filter_by(email=data['email']).first():
            return {'message': 'Пользователь с таким email уже существует.'}, 400

        user = User(
            first_name=data['first_name'],
            last_name=data['last_name'],
            login=data['login'],
            email=data['email']
        )
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()

        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])

        return {
            'message': 'Пользователь успешно зарегистрирован!',
            'token': token,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, 201

    @api.response(200, 'Registration model', user_model)
    def get(self):
        return {
            'first_name': 'string',
            'last_name': 'string',
            'login': 'string',
            'password': 'string',
            'confirm_password': 'string',
            'email': 'string'
        }, 200

@api.route('/login')
class Login(Resource):
    @api.expect(user_model)
    def post(self):
        data = request.get_json()
        user = User.query.filter_by(login=data['login']).first()

        if not user or not user.check_password(data['password']):
            return {'message': 'Неверный логин или пароль.'}, 401

        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])

        return {
            'token': token,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, 200

@api.route('/profile')
class Profile(Resource):
    @api.doc(security='Bearer Auth')
    @token_required
    @api.expect(profile_model)
    def put(self, current_user):
        try:
            if request.content_type == 'application/json':
                data = request.get_json() or {}
            else:
                data = request.form.to_dict() if request.form else {}
            
            logger.info(f"Полученные данные: {data}")

            schema = ProfileSchema()
            errors = schema.validate(data)
            if errors:
                logger.error(f"Ошибка валидации: {errors}")
                return {'message': 'Ошибка валидации', 'errors': errors}, 400

            if 'first_name' in data:
                current_user.first_name = data['first_name']
            if 'last_name' in data:
                current_user.last_name = data['last_name']
            if 'gender' in data:
                current_user.gender = data['gender']
            if 'country' in data:
                current_user.country = data['country']
            if 'city' in data:
                current_user.city = data['city']
            if 'birth_date' in data:
                try:
                    birth_date_str = data['birth_date']
                    current_user.birth_date = datetime.datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка формата даты: {e}")
                    return {'message': 'Некорректный формат даты, ожидается YYYY-MM-DD'}, 400

            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and allowed_file(file.filename):
                    filename = f"{current_user.id}_{datetime.datetime.utcnow().timestamp()}_{file.filename}"
                    try:
                        minio_client.put_object(
                            MINIO_BUCKET,
                            filename,
                            file.stream,
                            length=-1,
                            part_size=5*1024*1024,
                            content_type=file.content_type
                        )
                        logger.info(f"Фото {filename} успешно загружено в MinIO")

                        if current_user.profile_photo:
                            try:
                                minio_client.remove_object(MINIO_BUCKET, current_user.profile_photo)
                                logger.info(f"Старое фото {current_user.profile_photo} удалено из MinIO")
                            except S3Error as e:
                                logger.error(f"Ошибка удаления старого фото: {e}")

                        current_user.profile_photo = filename

                    except S3Error as e:
                        logger.error(f"Ошибка загрузки в MinIO: {e}")
                        return {'message': 'Ошибка загрузки фото в хранилище'}, 500
                else:
                    return {'message': 'Некорректный формат файла (PNG, JPG, JPEG)'}, 400

            db.session.add(current_user)
            db.session.commit()
            logger.info(f"Профиль пользователя {current_user.id} успешно обновлён")

            return {'message': 'Профиль успешно обновлен!'}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при обновлении профиля: {str(e)}")
            return {'message': 'Ошибка сервера при обновлении профиля', 'error': str(e)}, 500

    @api.doc(security='Bearer Auth')
    @token_required
    @api.response(200, 'User profile', user_response_model)
    def get(self, current_user):
        profile_photo_url = None
        if current_user.profile_photo:
            profile_photo_url = f"http://localhost:9000/{MINIO_BUCKET}/{current_user.profile_photo}"

        return {
            'id': current_user.id,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'login': current_user.login,
            'email': current_user.email,
            'registration_date': current_user.registration_date.isoformat(),
            'gender': current_user.gender,
            'country': current_user.country,
            'city': current_user.city,
            'birth_date': current_user.birth_date.strftime('%Y-%m-%d') if current_user.birth_date else None,
            'profile_photo': profile_photo_url
        }, 200

@api.route('/users/<int:user_id>')
class UserInfo(Resource):
    @api.doc(security='Bearer Auth')
    @token_required
    @api.response(200, 'User info', user_response_model)
    def get(self, current_user, user_id):
        user = db.session.get(User, user_id)
        if not user:
            return {'message': 'Пользователь не найден!'}, 404

        profile_photo_url = None
        if user.profile_photo:
            profile_photo_url = f"http://localhost:9000/{MINIO_BUCKET}/{user.profile_photo}"

        return {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'login': user.login,
            'email': user.email,
            'registration_date': user.registration_date.isoformat(),
            'gender': user.gender,
            'country': user.country,
            'city': user.city,
            'birth_date': user.birth_date.strftime('%Y-%m-%d') if user.birth_date else None,
            'profile_photo': profile_photo_url
        }, 200

@api.route('/users/search')
class SearchUsers(Resource):
    @api.doc(security='Bearer Auth')
    @token_required
    @api.doc(params={'query': 'Поисковый запрос (логин, имя или фамилия)'})
    @api.marshal_with(search_result_model, as_list=True)
    def get(self, current_user):
        query = request.args.get('query', '').strip()
        if not query:
            return {'message': 'Параметр query обязателен!'}, 400

        try:
            logger.info(f"Searching users with query: {query}")
            users = User.query.filter(
                (User.login.ilike(f'%{query}%')) |
                (User.first_name.ilike(f'%{query}%')) |
                (User.last_name.ilike(f'%{query}%'))
            ).all()

            return [{
                'id': user.id,
                'login': user.login,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'profile_photo': f"http://localhost:9000/{MINIO_BUCKET}/{user.profile_photo}" if user.profile_photo else None
            } for user in users], 200
        except Exception as e:
            logger.error(f"Error searching users: {str(e)}")
            return {'message': 'Ошибка сервера'}, 500

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5001)