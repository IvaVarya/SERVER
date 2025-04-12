import logging
import os
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
import jwt
from functools import wraps
from datetime import datetime
from prometheus_flask_exporter import PrometheusMetrics
from flask_cors import CORS
import requests

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metrics = PrometheusMetrics(app)

api = Api(app, version='1.0', title='Friend Service API', description='API для управления друзьями')

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['USER_SERVICE_URL'] = os.getenv('USER_SERVICE_URL', 'http://user_service:5001')  # Исправлено

db = SQLAlchemy(app)

class Friendship(db.Model):
    __tablename__ = 'friendships'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    friend_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'friend_id', name='unique_friendship'),
    )

def init_db():
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        logger.debug(f"Received Authorization header: {token}")
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Токен отсутствует!'}, 401
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            logger.debug(f"Extracted token: {token[:10]}...")
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            kwargs['user_id'] = data['user_id']
            logger.info(f"Decoded user_id: {kwargs['user_id']}")
        except jwt.InvalidTokenError as e:
            logger.warning(f'Token is invalid: {str(e)}')
            return {'message': 'Неверный токен!'}, 401
        except Exception as e:
            logger.error(f'Unexpected error decoding token: {str(e)}')
            return {'message': 'Ошибка обработки токена!'}, 500
        return f(*args, **kwargs)
    return decorated

def get_user_info(user_id, auth_token=None):
    """
    Получает информацию о пользователе из user_service.

    Args:
        user_id (int): ID пользователя.
        auth_token (str, optional): JWT-токен для аутентификации. Если None, берется из текущего запроса.

    Returns:
        dict: Данные пользователя {'id', 'first_name', 'last_name', 'login'} или None, если пользователь не найден.
    """
    try:
        # Используем переданный токен или берем из текущего запроса
        headers = {}
        if auth_token:
            headers['Authorization'] = auth_token
        elif hasattr(request, 'headers'):
            headers['Authorization'] = request.headers.get('Authorization')
        else:
            logger.error(f"No authorization token provided for user_id {user_id}")
            return None

        if not headers.get('Authorization'):
            logger.error(f"Missing Authorization header for user_id {user_id}")
            return None

        # Запрос к user_service
        logger.debug(f"Requesting user info for user_id {user_id} from {app.config['USER_SERVICE_URL']}")
        response = requests.get(
            f"{app.config['USER_SERVICE_URL']}/users/{user_id}",
            headers=headers,
            timeout=3
        )
        response.raise_for_status()  # Вызывает исключение для статусов 4xx/5xx

        # Проверка формата ответа
        try:
            user_data = response.json()
            required_keys = {'id', 'first_name', 'last_name', 'login'}
            if not isinstance(user_data, dict) or not all(key in user_data for key in required_keys):
                logger.error(f"Invalid user data format for user_id {user_id}: {user_data}")
                return None
            return {
                'id': user_data['id'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
                'login': user_data['login']
            }
        except ValueError:
            logger.error(f"Failed to parse JSON for user_id {user_id}: {response.text}")
            return None

    except requests.HTTPError as e:
        if response.status_code == 404:
            logger.warning(f"User not found for user_id {user_id}")
            return None
        logger.error(f"HTTP error fetching user info for user_id {user_id}: {str(e)}, status: {response.status_code}, body: {response.text}")
        return None
    except requests.ConnectionError:
        logger.error(f"User service unavailable for user_id {user_id}")
        return None
    except requests.Timeout:
        logger.error(f"Timeout fetching user info for user_id {user_id}")
        return None
    except requests.RequestException as e:
        logger.error(f"Unexpected error fetching user info for user_id {user_id}: {str(e)}")
        return None

def check_user_exists(user_id):
    """
    Проверяет существование пользователя через user_service.
    """
    try:
        headers = {'Authorization': request.headers.get('Authorization')}
        response = requests.get(f"{app.config['USER_SERVICE_URL']}/users/{user_id}", headers=headers, timeout=3)
        response.raise_for_status()
        return True
    except requests.HTTPError as e:
        if response.status_code == 404:
            logger.warning(f"User not found for user_id {user_id}")
            return False
        logger.error(f"HTTP error checking user_id {user_id}: {str(e)}, status: {response.status_code}")
        raise Exception("Ошибка проверки пользователя")
    except requests.ConnectionError:
        logger.error(f"User service unavailable for user_id {user_id}")
        raise Exception("Сервис пользователей недоступен!")
    except requests.RequestException as e:
        logger.error(f"Error checking user_id {user_id} existence: {str(e)}")
        raise Exception("Ошибка проверки пользователя")

friend_request_model = api.model('FriendRequestModel', {
    'friend_id': fields.Integer(required=True, description='ID пользователя для добавления в друзья')
})

friend_model = api.model('Friend', {
    'friend_id': fields.Integer(description='ID друга'),
    'first_name': fields.String(description='Имя друга'),
    'last_name': fields.String(description='Фамилия друга'),
    'login': fields.String(description='Логин друга'),
    'created_at': fields.String(description='Дата создания дружбы в формате ISO')
})

search_result_model = api.model('SearchResult', {
    'id': fields.Integer(description='ID пользователя'),
    'login': fields.String(description='Логин пользователя'),
    'first_name': fields.String(description='Имя'),
    'last_name': fields.String(description='Фамилия'),
    'profile_photo': fields.String(description='URL фото профиля')
})

@api.route('/friends/request')
class FriendRequest(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        data = request.get_json()
        friend_id = data.get('friend_id')
        if not friend_id:
            return {'message': 'friend_id обязателен!'}, 400
        if user_id == friend_id:
            return {'message': 'Нельзя добавить себя в друзья!'}, 400

        try:
            if not check_user_exists(friend_id):
                return {'message': 'Пользователь с таким friend_id не существует!'}, 404
        except Exception as e:
            logger.error(f"Failed to check user existence for friend_id {friend_id}: {str(e)}")
            return {'message': str(e)}, 503

        existing = Friendship.query.filter_by(user_id=user_id, friend_id=friend_id).first()
        if existing:
            return {'message': 'Запрос уже отправлен или вы уже друзья!'}, 400

        try:
            friendship = Friendship(user_id=user_id, friend_id=friend_id)
            db.session.add(friendship)
            db.session.commit()
            logger.info(f'Friend request from user_id: {user_id} to friend_id: {friend_id}')
            return {'message': 'Запрос в друзья отправлен!', 'request_id': friendship.id}, 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error sending friend request: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends/accept')
class AcceptFriend(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        data = request.get_json()
        friend_id = data.get('friend_id')
        if not friend_id:
            return {'message': 'friend_id обязателен!'}, 400

        try:
            if not check_user_exists(friend_id):
                return {'message': 'Пользователь с таким friend_id не существует!'}, 404
        except Exception as e:
            logger.error(f"Failed to check user existence for friend_id {friend_id}: {str(e)}")
            return {'message': str(e)}, 503

        friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='pending').first()
        if not friendship:
            return {'message': 'Запрос в друзья не найден!'}, 404

        try:
            friendship.status = 'accepted'
            reverse_friendship = Friendship(user_id=user_id, friend_id=friend_id, status='accepted')
            db.session.add(reverse_friendship)
            db.session.commit()
            logger.info(f'Friendship accepted between user_id: {user_id} and friend_id: {friend_id}')
            return {'message': 'Друг добавлен!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error accepting friend request: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends/<int:friend_id>')
class DeleteFriend(Resource):
    @token_required
    def delete(self, user_id, friend_id):
        try:
            if not check_user_exists(friend_id):
                return {'message': 'Пользователь с таким friend_id не существует!'}, 404
        except Exception as e:
            logger.error(f"Failed to check user existence for friend_id {friend_id}: {str(e)}")
            return {'message': str(e)}, 503

        friendship = Friendship.query.filter_by(user_id=user_id, friend_id=friend_id, status='accepted').first()
        if not friendship:
            return {'message': 'Друг не найден!'}, 404

        try:
            reverse_friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='accepted').first()
            db.session.delete(friendship)
            if reverse_friendship:
                db.session.delete(reverse_friendship)
            db.session.commit()
            logger.info(f'Friendship deleted between user_id: {user_id} and friend_id: {friend_id}')
            return {'message': 'Друг удален!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error deleting friend: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends')
class GetFriends(Resource):
    @token_required
    @api.marshal_with(friend_model, as_list=True)
    def get(self, user_id):
        try:
            logger.info(f"Fetching friends for user_id: {user_id}")
            friends = Friendship.query.filter_by(user_id=user_id, status='accepted').all()
            logger.info(f"Found {len(friends)} friends")

            friend_list = []
            auth_token = request.headers.get('Authorization')
            for f in friends:
                friend_info = get_user_info(f.friend_id, auth_token=auth_token)
                if friend_info:
                    friend_list.append({
                        'friend_id': f.friend_id,
                        'first_name': friend_info['first_name'],
                        'last_name': friend_info['last_name'],
                        'login': friend_info['login'],
                        'created_at': f.created_at.isoformat()
                    })
                else:
                    logger.warning(f"Skipping friend with id {f.friend_id}: user info not available")
                    # Пропускаем друга, вместо сбоя

            return friend_list, 200
        except Exception as e:
            logger.error(f"Error fetching friends for user_id {user_id}: {str(e)}")
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends/requests/incoming')
class IncomingFriendRequests(Resource):
    @token_required
    @api.marshal_with(friend_model, as_list=True)
    def get(self, user_id):
        logger.info(f'Fetching incoming friend requests for user_id: {user_id}')
        try:
            requests = Friendship.query.filter_by(friend_id=user_id, status='pending').all()
            logger.info(f'Found {len(requests)} incoming requests')
            incoming_requests = []
            auth_token = request.headers.get('Authorization')
            for req in requests:
                user_info = get_user_info(req.user_id, auth_token=auth_token)
                if user_info:
                    incoming_requests.append({
                        'friend_id': req.user_id,
                        'first_name': user_info['first_name'],
                        'last_name': user_info['last_name'],
                        'login': user_info['login'],
                        'created_at': req.created_at.isoformat()
                    })
                else:
                    logger.warning(f"Skipping request from user_id {req.user_id}: user info not available")
            return incoming_requests, 200
        except Exception as e:
            logger.error(f"Error fetching incoming requests for user_id {user_id}: {str(e)}")
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends/reject')
class RejectFriend(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        data = request.get_json()
        friend_id = data.get('friend_id')
        if not friend_id:
            return {'message': 'friend_id обязателен!'}, 400
        
        friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='pending').first()
        if not friendship:
            return {'message': 'Запрос в друзья не найден!'}, 404

        try:
            db.session.delete(friendship)
            db.session.commit()
            logger.info(f'Friend request from user_id: {friend_id} to user_id: {user_id} rejected')
            return {'message': 'Запрос отклонен!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error rejecting friend request: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

@api.route('/friends/search')
class SearchUsers(Resource):
    @token_required
    @api.doc(params={'query': 'Поисковый запрос (логин, имя или фамилия)'})
    @api.marshal_with(search_result_model, as_list=True)
    def get(self, user_id):
        query = request.args.get('query', '').strip()
        if not query:
            return {'message': 'Параметр query обязателен!'}, 400

        try:
            logger.info(f"Searching users with query: {query} for user_id: {user_id}")
            headers = {'Authorization': request.headers.get('Authorization')}
            response = requests.get(
                f"{app.config['USER_SERVICE_URL']}/users/search?query={query}",
                headers=headers,
                timeout=3
            )
            response.raise_for_status()
            users = response.json()
            return users, 200
        except requests.HTTPError as e:
            logger.error(f"HTTP error searching users: {str(e)}, status: {response.status_code}")
            return {'message': 'Ошибка поиска пользователей'}, 500
        except requests.ConnectionError:
            logger.error(f"User service unavailable")
            return {'message': 'Сервис пользователей недоступен!'}, 503
        except requests.RequestException as e:
            logger.error(f"Error searching users: {str(e)}")
            return {'message': 'Ошибка поиска пользователей'}, 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5004)