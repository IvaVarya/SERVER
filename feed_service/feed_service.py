import logging
import os
from flask import Flask, request, jsonify
import requests
from functools import wraps
import jwt
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Prometheus
metrics = PrometheusMetrics(app)

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

# Получение ленты новостей
@app.route('/feed', methods=['GET'])
@token_required
def get_feed(user_id):
    try:
        # Получаем список друзей
        headers = {'Authorization': request.headers.get('Authorization')}
        friends_response = requests.get(f'{FRIEND_SERVICE_URL}/friends', headers=headers, timeout=5)
        if friends_response.status_code != 200:
            logger.error(f'Error fetching friends: {friends_response.text}')
            return {'message': 'Ошибка получения списка друзей'}, 500
        friends_data = friends_response.json()
        friend_ids = [f['friend_id'] for f in friends_data.get('friends', [])]
        friend_ids.append(user_id)  # Добавляем себя

        # Получаем посты через внутренний API
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
        return jsonify({'feed': posts})
    except requests.RequestException as e:
        logger.error(f'Error in feed service: {str(e)}')
        return {'message': 'Ошибка сервера'}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)