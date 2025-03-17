import logging
import os
from flask import Flask, request, jsonify
import requests
from functools import wraps
import jwt
from prometheus_flask_exporter import PrometheusMetrics
from flask_restx import Api, Resource, fields
from flask_cors import CORS

app = Flask(__name__)

# Настройка CORS
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

# Настройка Swagger
api = Api(app, version='1.0', title='Feed Service API',
          description='API для получения ленты новостей.')

# Конфигурация приложения
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
FRIEND_SERVICE_URL = 'http://friend_service:5005'
POST_SERVICE_URL = 'http://post_service:5003'
INTERNAL_KEY = os.getenv('INTERNAL_KEY', 'internal-secret')

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
feed_model = api.model('FeedResponse', {
    'feed': fields.List(fields.Raw, description='Список постов')
})

@api.route('/feed')
class GetFeed(Resource):
    @token_required
    @api.marshal_with(feed_model)
    @api.doc(responses={200: 'Успешно', 401: 'Токен неверный', 500: 'Ошибка сервера'})
    def get(self, user_id):
        try:
            headers = {'Authorization': request.headers.get('Authorization')}
            friends_response = requests.get(f'{FRIEND_SERVICE_URL}/friends', headers=headers, timeout=5)
            if friends_response.status_code != 200:
                logger.error(f'Error fetching friends: {friends_response.text}')
                return {'message': 'Ошибка получения списка друзей'}, 500
            friends_data = friends_response.json()
            friend_ids = [f['friend_id'] for f in friends_data.get('friends', [])]
            friend_ids.append(user_id)

            internal_headers = {'X-Internal-Key': INTERNAL_KEY}
            posts_response = requests.get(
                f'{POST_SERVICE_URL}/internal/posts/by_users',
                headers=internal_headers,
                params={'user_ids': ','.join(map(str, friend_ids))},
                timeout=5
            )
            if posts_response.status_code != 200:
                logger.error(f'Error fetching posts: {posts_response.text}')
                return {'message': 'Ошибка получения постов'}, 500
            posts = posts_response.json()

            logger.info(f'Feed retrieved for user_id: {user_id}')
            return {'feed': posts}
        except requests.RequestException as e:
            logger.error(f'Error in feed service: {str(e)}')
            return {'message': 'Ошибка сервера'}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)