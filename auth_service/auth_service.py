#auth_service.py
import logging
from flask import Flask, request, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
from flask_restx import Api, Resource, fields
from prometheus_flask_exporter import PrometheusMetrics
from schemas import UserSchema
from flask_cors import CORS

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger с использованием Flask-RESTX
api = Api(app, version='1.0', title='Auth Service API', description='API для управления пользователями')

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:server@db:5432/PostgreSQL'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'

db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

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
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            with db.session() as session:
                current_user = session.get(User, data['user_id'])
                if not current_user:
                    logger.warning(f'User with ID {data["user_id"]} not found!')
                    return {'message': 'User not found!'}, 401
                return f(current_user=current_user, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            logger.warning('Token has expired!')
            return {'message': 'Token has expired!'}, 401
        except jwt.InvalidTokenError:
            logger.warning('Invalid token!')
            return {'message': 'Invalid token!'}, 401
        except Exception as e:
            logger.error(f'Unexpected error in token validation: {str(e)}')
            return {'message': 'Internal server error'}, 500
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

user_response_model = api.model('UserResponse', {
    'id': fields.Integer(description='ID пользователя'),
    'first_name': fields.String(description='Имя пользователя'),
    'last_name': fields.String(description='Фамилия пользователя'),
    'login': fields.String(description='Логин пользователя'),
    'email': fields.String(description='Email пользователя'),
    'registration_date': fields.DateTime(description='Дата регистрации')
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

        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'])

        logger.info(f'User {user.login} registered successfully!')
        return {
            'message': 'Пользователь успешно зарегистрирован!',
            'token': token,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, 201

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
        return {
            'token': token,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, 200

# Новый GET метод для получения данных пользователя
# Новый GET метод для получения данных пользователя
@api.route('/user')
class UserProfile(Resource):
    @api.doc(security='Bearer Auth')
    @api.response(200, 'Success', user_response_model)
    @api.response(401, 'Unauthorized')
    @token_required
    def get(self, current_user):
        response_data = {
            'id': current_user.id,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'login': current_user.login,
            'email': current_user.email,
            'registration_date': current_user.registration_date.isoformat()
        }
        response = make_response(response_data, 200)
        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)