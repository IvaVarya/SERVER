#auth_service.py
import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
from flask_restx import Api, Resource, fields
from prometheus_flask_exporter import PrometheusMetrics
from schemas import UserSchema

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger с использованием Flask-RESTX
api = Api(app, version='1.0', title='Auth Service API', description='API для управления пользователями')

# Конфигурация базы данных (PostgreSQL, например)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:server@db:5432/PostgreSQL'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'  # Секретный ключ для JWT, замените на свой

db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # Увеличено до 256 символов
    email = db.Column(db.String(120), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # Добавлено поле

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Создание таблицы в БД
with app.app_context():
    db.create_all()

# Декоратор для проверки токена
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Token is missing!'}, 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            logger.warning('Token is invalid!')
            return {'message': 'Token is invalid!'}, 401
        return f(*args, **kwargs)
    return decorated

# Модель для Swagger
user_model = api.model('User', {
    'first_name': fields.String(required=True, description='Имя пользователя'),
    'last_name': fields.String(required=True, description='Фамилия пользователя'),
    'login': fields.String(required=True, description='Логин пользователя'),
    'password': fields.String(required=True, description='Пароль пользователя'),
    'confirm_password': fields.String(required=True, description='Подтверждение пароля'),
    'email': fields.String(required=True, description='Email пользователя')
})

# Регистрация
@api.route('/register')
class Register(Resource):
    @api.expect(user_model)
    def post(self):
        data = request.get_json()
        schema = UserSchema()
        errors = schema.validate(data)
        if errors:
            logger.warning(f'Validation errors: {errors}')
            return {'message': 'Ошибка валидации', 'errors': errors}, 400

        if data['password'] != data['confirm_password']:
            logger.warning('Passwords do not match!')
            return {'message': 'Пароли не совпадают.'}, 400

        if User.query.filter_by(login=data['login']).first():
            logger.warning(f'User with login {data["login"]} already exists!')
            return {'message': 'Пользователь с таким логином уже существует.'}, 400

        if User.query.filter_by(email=data['email']).first():
            logger.warning(f'User with email {data["email"]} already exists!')
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

        logger.info(f'User {user.login} registered successfully!')
        return {'message': 'Пользователь успешно зарегистрирован!'}, 201

# Вход
@api.route('/login')
class Login(Resource):
    @api.expect(user_model)
    def post(self):
        data = request.get_json()
        user = User.query.filter_by(login=data['login']).first()

        if not user:
            logger.warning(f'User with login {data["login"]} not found!')
            return {'message': 'Пользователь с таким логином не найден.'}, 401

        if not user.check_password(data['password']):
            logger.warning(f'Invalid password for user {data["login"]}!')
            return {'message': 'Неверный пароль.'}, 401

        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])

        logger.info(f'User {user.login} logged in successfully!')
        return {'token': token}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)