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

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metrics = PrometheusMetrics(app)

api = Api(app, version='1.0', title='Feed Service API',
          description='API для получения ленты новостей.')

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
FRIEND_SERVICE_URL = 'http://friend_service:5004'
POST_SERVICE_URL = 'http://post_service:5002'
INTERNAL_KEY = os.getenv('INTERNAL_KEY', 'internal-secret')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            logger.warning('Token is missing!')
            return {'message': 'Токен отсутствует!'}, 401
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            kwargs['user_id'] = data['user_id']
        except jwt.InvalidTokenError:
            logger.warning('Token is invalid!')
            return {'message': 'Неверный токен!'}, 401
        return f(*args, **kwargs)
    return decorated

feed_model = api.model('FeedResponse', {
    'feed': fields.List(fields.Raw, description='Список постов'),
    'total': fields.Integer(description='Общее количество постов'),
    'page': fields.Integer(description='Текущая страница'),
    'per_page': fields.Integer(description='Количество постов на странице')
})

@api.route('/feed')
class GetFeed(Resource):
    @token_required
    @api.marshal_with(feed_model)
    @api.doc(params={'page': 'Номер страницы (по умолчанию 1)', 'per_page': 'Количество постов на странице (по умолчанию 10)'})
    @api.doc(responses={200: 'Успешно', 401: 'Токен неверный', 500: 'Ошибка сервера'})
    def get(self, user_id):
        try:
            page = int(request.args.get('page', 1))
            per_page = int(request.args.get('per_page', 10))
            if page < 1 or per_page < 1:
                return {'message': 'Неверные параметры пагинации'}, 400

            # Запрос к friend_service
            friend_ids = []
            headers = {'Authorization': request.headers.get('Authorization')}
            logger.info(f"Requesting friends for user_id: {user_id}")
            try:
                friends_response = requests.get(f'{FRIEND_SERVICE_URL}/friends', headers=headers, timeout=3)
                logger.debug(f"Friend service response: {friends_response.status_code}, {friends_response.text}")
                if friends_response.status_code == 200:
                    try:
                        friends_data = friends_response.json()
                        if not isinstance(friends_data, list):
                            logger.error(f"Invalid friends data format: {friends_data}")
                            friend_ids = [user_id]
                        else:
                            friend_ids = [f['friend_id'] for f in friends_data if isinstance(f, dict) and 'friend_id' in f]
                            friend_ids.append(user_id)
                    except ValueError:
                        logger.error(f"Failed to parse JSON from friend_service: {friends_response.text}")
                        friend_ids = [user_id]
                else:
                    logger.error(f"Friend service returned {friends_response.status_code}: {friends_response.text}")
                    friend_ids = [user_id]
            except requests.RequestException as e:
                logger.error(f"Failed to reach friend_service: {str(e)}")
                friend_ids = [user_id]  # Деградация: только посты пользователя

            logger.info(f"Retrieved friend_ids: {friend_ids}")
            if not friend_ids:
                logger.info(f"No friends found for user_id: {user_id}")
                return {'feed': [], 'total': 0, 'page': page, 'per_page': per_page}, 200

            # Запрос к post_service
            internal_headers = {'X-Internal-Key': INTERNAL_KEY}
            logger.info(f"Requesting posts for user_ids: {friend_ids}")
            posts_response = requests.get(
                f'{POST_SERVICE_URL}/internal/posts/by_users',
                headers=internal_headers,
                params={'user_ids': ','.join(map(str, friend_ids))},
                timeout=3
            )
            logger.debug(f"Post service response: {posts_response.status_code}, {posts_response.text}")
            if posts_response.status_code != 200:
                logger.error(f"Error fetching posts: {posts_response.status_code}, {posts_response.text}")
                return {'message': 'Ошибка получения постов'}, 500
            
            try:
                posts = posts_response.json()
                if not isinstance(posts, list):
                    logger.error(f"Invalid posts data format: {posts}")
                    return {'message': 'Ошибка обработки постов'}, 500
            except ValueError:
                logger.error(f"Failed to parse JSON from post_service: {posts_response.text}")
                return {'message': 'Ошибка обработки постов'}, 500

            total = len(posts)
            start = (page - 1) * per_page
            end = start + per_page
            paginated_posts = posts[start:end]

            logger.info(f"Feed retrieved for user_id: {user_id}, total posts: {total}")
            return {
                'feed': paginated_posts,
                'total': total,
                'page': page,
                'per_page': per_page
            }, 200
        except ValueError:
            logger.error(f"Invalid pagination parameters: page={request.args.get('page')}, per_page={request.args.get('per_page')}")
            return {'message': 'Неверные параметры пагинации'}, 400
        except Exception as e:
            logger.error(f"Unexpected error in feed_service for user_id {user_id}: {str(e)}")
            return {'message': 'Ошибка сервера'}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)