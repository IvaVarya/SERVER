import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import jwt
from functools import wraps
import os
from datetime import datetime, date
from flask_restx import Api, Resource, fields
from prometheus_flask_exporter import PrometheusMetrics
from schemas import ProfileSchema
from flask_cors import CORS

app = Flask(__name__)

CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger с использованием Flask-RESTX
api = Api(app, version='1.0', title='Profile Service API', description='API для управления изменениями профиля')

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:server@db:5432/PostgreSQL'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')  # Use environment variable
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)

class Profile(db.Model):
    __tablename__ = 'profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    gender = db.Column(db.String(20))
    country = db.Column(db.String(50))
    city = db.Column(db.String(50))
    birth_date = db.Column(db.Date)
    profile_photo = db.Column(db.String(200))

with app.app_context():
    db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Token is missing!'}, 401
        
        # Handle Bearer token format
        if token.startswith('Bearer '):
            token = token.split('Bearer ')[1]
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            kwargs['user_id'] = data['user_id']
        except jwt.InvalidTokenError as e:
            logger.warning(f'Token is invalid! Error: {str(e)}')
            return {'message': f'Token is invalid! {str(e)}'}, 401
        except Exception as e:
            logger.warning(f'Token processing error: {str(e)}')
            return {'message': 'Token processing error'}, 401
        return f(*args, **kwargs)
    return decorated

profile_model = api.model('ProfileModel', {
    "first_name": fields.String(required=False, description='Имя пользователя'),
    "last_name": fields.String(required=False, description='Фамилия пользователя'),
    "gender": fields.String(required=False, description='Пол'),
    "birth_date": fields.Date(required=False, description='Дата рождения'),
    "country": fields.String(required=False, description='Страна'),
    "city": fields.String(required=False, description='Город'),
    "profile_picture": fields.String(required=False, description='Фото профиля')
})

@api.route('/profile')
class ProfileResource(Resource):
    @token_required
    @api.expect(profile_model)
    def put(self, user_id):
        data = request.get_json() or {}
        schema = ProfileSchema()
        errors = schema.validate(data)
        if errors:
            logger.warning(f'Validation errors: {errors}')
            return {'message': 'Ошибка валидации', 'errors': errors}, 400

        profile = Profile.query.filter_by(user_id=user_id).first()

        if not profile:
            profile = Profile(user_id=user_id)
            db.session.add(profile)

        if 'first_name' in data and data['first_name']:
            profile.first_name = data['first_name']
        if 'last_name' in data and data['last_name']:
            profile.last_name = data['last_name']
        if 'gender' in data and data['gender']:
            profile.gender = data['gender']
        if 'country' in data and data['country']:
            profile.country = data['country']
        if 'city' in data and data['city']:
            profile.city = data['city']
        if 'birth_date' in data and data['birth_date']:
            if isinstance(data['birth_date'], str):
                try:
                    profile.birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
                except ValueError:
                    logger.warning(f'Invalid birth_date format for user_id: {user_id}')
                    return {'message': 'Некорректный формат даты. Используйте YYYY-MM-DD.'}, 400
            elif isinstance(data['birth_date'], date):
                profile.birth_date = data['birth_date']
            else:
                logger.warning(f'Invalid birth_date type for user_id: {user_id}')
                return {'message': 'Некорректный формат даты. Используйте YYYY-MM-DD.'}, 400

        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and allowed_file(file.filename):
                filename = f"{user_id}_{file.filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile.profile_photo = filename
            else:
                logger.warning(f'Invalid file format for user_id: {user_id}')
                return {'message': 'Некорректный формат файла. Разрешены только PNG, JPG, JPEG.'}, 400

        try:
            db.session.commit()
            logger.info(f'Profile updated for user_id: {user_id}')
            return {'message': 'Профиль успешно обновлен!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Failed to update profile for user_id: {user_id}. Error: {str(e)}')
            return {'message': 'Ошибка при обновлении профиля'}, 500

    @token_required
    def get(self, user_id):
        profile = Profile.query.filter_by(user_id=user_id).first()
        if not profile:
            logger.warning(f'Profile not found for user_id: {user_id}')
            return {'message': 'Профиль не найден.'}, 404

        profile_data = {
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'gender': profile.gender,
            'country': profile.country,
            'city': profile.city,
            'birth_date': str(profile.birth_date) if profile.birth_date else None,
            'profile_photo': profile.profile_photo
        }
        logger.info(f'Profile retrieved for user_id: {user_id}')
        return profile_data, 200

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)