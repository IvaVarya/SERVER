import logging
import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
import jwt
from functools import wraps
from datetime import datetime
from prometheus_flask_exporter import PrometheusMetrics
from flask_cors import CORS
import requests  # Добавляем для HTTP-запросов

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metrics = PrometheusMetrics(app)

api = Api(app, version='1.0', title='Friend Service API', description='API для управления друзьями')

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['USER_SERVICE_URL'] = os.getenv('USER_SERVICE_URL', 'http://localhost:5001')  # URL user_service

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
        logger.info(f"Received Authorization header: {token}")
        if not token:
            logger.warning('Token is missing!')
            return jsonify({'message': 'Токен отсутствует!'}), 401
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            logger.info(f"Extracted token: {token}")
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            logger.info(f"Decoded token data: {data}")
            kwargs['user_id'] = data['user_id']
        except jwt.InvalidTokenError as e:
            logger.warning(f'Token is invalid: {str(e)}')
            return jsonify({'message': 'Неверный токен!'}), 401
        except Exception as e:
            logger.error(f'Unexpected error decoding token: {str(e)}')
            return jsonify({'message': 'Ошибка обработки токена!'}), 500
        return f(*args, **kwargs)
    return decorated

friend_request_model = api.model('FriendRequestModel', {
    'friend_id': fields.Integer(required=True, description='ID пользователя для добавления в друзья')
})

friend_model = api.model('Friend', {
    'friend_id': fields.Integer(description='ID друга'),
    'created_at': fields.String(description='Дата создания дружбы в формате ISO')
})

search_model = api.model('SearchResult', {
    'id': fields.Integer(description='ID пользователя'),
    'login': fields.String(description='Логин пользователя'),
    'first_name': fields.String(description='Имя'),
    'last_name': fields.String(description='Фамилия')
})

@api.route('/friends/request')
class FriendRequest(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        data = request.get_json()
        friend_id = data.get('friend_id')
        if not friend_id:
            return jsonify({'message': 'friend_id обязателен!'}), 400
        if user_id == friend_id:
            return jsonify({'message': 'Нельзя добавить себя в друзья!'}), 400

        existing = Friendship.query.filter_by(user_id=user_id, friend_id=friend_id).first()
        if existing:
            return jsonify({'message': 'Запрос уже отправлен или вы уже друзья!'}), 400

        try:
            friendship = Friendship(user_id=user_id, friend_id=friend_id)
            db.session.add(friendship)
            db.session.commit()
            logger.info(f'Friend request from user_id: {user_id} to friend_id: {friend_id}')
            return jsonify({'message': 'Запрос в друзья отправлен!', 'request_id': friendship.id}), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error sending friend request: {str(e)}')
            return jsonify({'message': 'Ошибка сервера'}), 500

@api.route('/friends/accept')
class AcceptFriend(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        data = request.get_json()
        friend_id = data.get('friend_id')
        if not friend_id:
            return jsonify({'message': 'friend_id обязателен!'}), 400
        
        friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='pending').first()
        if not friendship:
            return jsonify({'message': 'Запрос в друзья не найден!'}), 404

        try:
            friendship.status = 'accepted'
            reverse_friendship = Friendship(user_id=user_id, friend_id=friend_id, status='accepted')
            db.session.add(reverse_friendship)
            db.session.commit()
            logger.info(f'Friendship accepted between user_id: {user_id} and friend_id: {friend_id}')
            return jsonify({'message': 'Друг добавлен!'}), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error accepting friend request: {str(e)}')
            return jsonify({'message': 'Ошибка сервера'}), 500

@api.route('/friends/<int:friend_id>')
class DeleteFriend(Resource):
    @token_required
    def delete(self, user_id, friend_id):
        friendship = Friendship.query.filter_by(user_id=user_id, friend_id=friend_id, status='accepted').first()
        if not friendship:
            return jsonify({'message': 'Друг не найден!'}), 404

        try:
            reverse_friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='accepted').first()
            db.session.delete(friendship)
            if reverse_friendship:
                db.session.delete(reverse_friendship)
            db.session.commit()
            logger.info(f'Friendship deleted between user_id: {user_id} and friend_id: {friend_id}')
            return jsonify({'message': 'Друг удален!'}), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error deleting friend: {str(e)}')
            return jsonify({'message': 'Ошибка сервера'}), 500

@api.route('/friends')
class GetFriends(Resource):
    @token_required
    @api.marshal_with(friend_model, as_list=True)
    def get(self, user_id):
        try:
            logger.info(f"Fetching friends for user_id: {user_id}")
            friends = Friendship.query.filter_by(user_id=user_id, status='accepted').all()
            logger.info(f"Found {len(friends)} friends")
            return [{
                'friend_id': f.friend_id,
                'created_at': f.created_at.isoformat()
            } for f in friends]
        except Exception as e:
            logger.error(f'Error fetching friends: {str(e)}')
            return jsonify({'message': 'Ошибка сервера'}), 500

@api.route('/friends/search')
class SearchFriends(Resource):
    @token_required
    @api.doc(params={'query': 'Поисковый запрос (логин, имя или фамилия)'})
    @api.marshal_with(search_model, as_list=True)
    def get(self, user_id):
        query = request.args.get('query', '').strip()
        if not query:
            return jsonify({'message': 'Параметр query обязателен!'}), 400

        try:
            logger.info(f"Searching friends for user_id: {user_id} with query: {query}")
            # Делаем запрос к user_service
            user_service_url = f"{app.config['USER_SERVICE_URL']}/users/search?query={query}"
            headers = {'Authorization': request.headers.get('Authorization')}
            response = requests.get(user_service_url, headers=headers, timeout=5)
            response.raise_for_status()  # Вызывает исключение при ошибке HTTP

            users = response.json()
            # Фильтруем текущего пользователя
            users = [user for user in users if user['id'] != user_id]
            return users[:10], 200  # Ограничиваем до 10 результатов
        except requests.RequestException as e:
            logger.error(f'Error calling user_service: {str(e)}')
            return jsonify({'message': 'Ошибка при запросе к user_service'}), 500
        except Exception as e:
            logger.error(f'Error searching friends: {str(e)}')
            return jsonify({'message': 'Ошибка сервера'}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5004)