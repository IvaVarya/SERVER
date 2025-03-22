import logging
import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
import jwt
from functools import wraps
from datetime import datetime
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger
api = Api(app, version='1.0', title='Friend Service API', description='API для управления друзьями')

# Конфигурация приложения
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

db = SQLAlchemy(app)

# Модель дружбы
class Friendship(db.Model):
    __tablename__ = 'friendships'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
      
    status = db.Column(db.String(20), default='pending')  # pending, accepted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Создание таблиц
with app.app_context():
    db.create_all()

# Декоратор для проверки токена
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Токен отсутствует!'}, 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            kwargs['user_id'] = data['user_id']
        except jwt.InvalidTokenError:
            logger.warning('Token is invalid!')
            return {'message': 'Неверный токен!'}, 401
        return f(*args, **kwargs)
    return decorated

# Модель для Swagger
friend_request_model = api.model('FriendRequestModel', {
    'friend_id': fields.Integer(required=True, description='ID пользователя для добавления в друзья')
})

# Отправка запроса в друзья
@api.route('/friends/request')
class FriendRequest(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        friend_id = request.json['friend_id']
        if user_id == friend_id:
            return {'message': 'Нельзя добавить себя в друзья!'}, 400

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

# Принятие запроса в друзья
@api.route('/friends/accept')
class AcceptFriend(Resource):
    @token_required
    @api.expect(friend_request_model)
    def post(self, user_id):
        friend_id = request.json['friend_id']
        friendship = Friendship.query.filter_by(user_id=friend_id, friend_id=user_id, status='pending').first()
        if not friendship:
            return {'message': 'Запрос в друзья не найден!'}, 404

        try:
            friendship.status = 'accepted'
            # Создаем обратную связь
            reverse_friendship = Friendship(user_id=user_id, friend_id=friend_id, status='accepted')
            db.session.add(reverse_friendship)
            db.session.commit()
            logger.info(f'Friendship accepted between user_id: {user_id} and friend_id: {friend_id}')
            return {'message': 'Друг добавлен!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error accepting friend request: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

# Удаление друга
@api.route('/friends/<int:friend_id>')
class DeleteFriend(Resource):
    @token_required
    def delete(self, user_id, friend_id):
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

# Получение списка друзей
@api.route('/friends')
class GetFriends(Resource):
    @token_required
    def get(self, user_id):
        friends = Friendship.query.filter_by(user_id=user_id, status='accepted').all()
        return jsonify({
            'friends': [{
                'friend_id': f.friend_id,
                'created_at': f.created_at.isoformat()
            } for f in friends]
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)