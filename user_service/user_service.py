import logging
from flask import Flask, request, make_response
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

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger
api = Api(app, version='1.0', title='User Service API', 
          description='API для управления пользователями и их профилями')

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:server@db:5432/PostgreSQL'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)

# Обновленная модель пользователя
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
            return {'message': 'Token is missing!'}, 401
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = db.session.get(User, data['user_id'])
            if not current_user:
                return {'message': 'User not found!'}, 401
            return f(current_user=current_user, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            return {'message': 'Token has expired!'}, 401
        except jwt.InvalidTokenError:
            return {'message': 'Invalid token!'}, 401
    return decorated

# Модели для Swagger
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
    'birth_date': fields.Date(required=False),
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
    'birth_date': fields.Date,
    'profile_photo': fields.String
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
        data = request.get_json() or {}
        schema = ProfileSchema()
        errors = schema.validate(data)
        if errors:
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
                current_user.birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
            except ValueError:
                return {'message': 'Некорректный формат даты (YYYY-MM-DD)'}, 400

        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and allowed_file(file.filename):
                filename = f"{current_user.id}_{file.filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_photo = filename
            else:
                return {'message': 'Некорректный формат файла (PNG, JPG, JPEG)'}, 400

        db.session.commit()
        return {'message': 'Профиль успешно обновлен!'}, 200

    @api.doc(security='Bearer Auth')
    @token_required
    @api.response(200, 'User profile', user_response_model)
    def get(self, current_user):
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
            'birth_date': str(current_user.birth_date) if current_user.birth_date else None,
            'profile_photo': current_user.profile_photo
        }, 200

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)