import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import SecureForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import validators, Form, StringField, IntegerField, TextAreaField
from prometheus_flask_exporter import PrometheusMetrics
import os
from flask_cors import CORS
from minio import Minio
from minio.error import S3Error
import json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metrics = PrometheusMetrics(app)

api = Api(app, version='1.0', title='Sets Service API', description='API для поиска наборов для вышивания и управления избранным')

# Конфигурация базы данных и приложения
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:server@db:5432/PostgreSQL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Ограничение размера файла - 5 MB

# Конфигурация MinIO
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'set-photos')
MINIO_SECURE = False

# Инициализация клиента MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

# Проверка и создание корзины с публичной политикой
def init_minio():
    try:
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
            logger.info(f"Создана корзина {MINIO_BUCKET} в MinIO")
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"]
                }
            ]
        }
        minio_client.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
        logger.info(f"Установлена публичная политика для {MINIO_BUCKET}")
    except S3Error as e:
        logger.error(f"Ошибка инициализации MinIO: {e}")
        raise

db = SQLAlchemy(app)

# Модель набора для вышивания
class Set(db.Model):
    __tablename__ = 'sets'
    id = db.Column(db.Integer, primary_key=True)
    manufacturer = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    photo = db.Column(db.String(256))  # Хранит имя файла в MinIO или внешний URL

# Модель для избранного
class FavoriteSet(db.Model):
    __tablename__ = 'favorite_sets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    set = db.relationship('Set', backref='favorites')  # Добавляем связь
    added_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint('user_id', 'set_id', name='unique_favorite'),
    )

# Функция для инициализации базы данных с предопределёнными наборами
def init_db():
    with app.app_context():
        if Set.query.count() == 0:
            default_sets = [
                Set(
                    manufacturer="DMC",
                    name="Цветочный сад",
                    category="Природа",
                    description="Набор для вышивания крестиком с изображением цветочного сада.",
                    width=150,
                    height=100,
                    photo="https://i.pinimg.com/736x/d6/5e/85/d65e859db614052853cc08f04999c6be.jpg"
                ),
                Set(
                    manufacturer="Riolis",
                    name="Зимний лес",
                    category="Пейзаж",
                    description="Зимний пейзаж с деревьями и снегом для вышивания крестиком.",
                    width=200,
                    height=150,
                    photo="https://cdn1.ozone.ru/s3/multimedia-6/c600/6289401306.jpg"
                ),
                Set(
                    manufacturer="Астра",
                    name="Премиум",
                    category="Цветы",
                    description="Набор для вышивания с цветочными мотивами.",
                    width=15,
                    height=20,
                    photo="set_3_1744827081.416665_CJRC1269.JPG"
                )
            ]
            db.session.bulk_save_objects(default_sets)
            db.session.commit()
            logger.info("Добавлены предопределённые наборы для вышивания с внешними URL.")

# Инициализация базы данных и MinIO
def init_app():
    with app.app_context():
        db.create_all()
        init_db()
        init_minio()

# Декоратор для проверки токена
def token_required(f):
    from functools import wraps
    import jwt
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

# Модели для Swagger
set_model = api.model('Set', {
    'id': fields.Integer(description='ID набора'),
    'manufacturer': fields.String(description='Производитель'),
    'name': fields.String(description='Название набора'),
    'category': fields.String(description='Категория'),
    'description': fields.String(description='Описание'),
    'width': fields.Integer(description='Ширина в стежках'),
    'height': fields.Integer(description='Высота в стежках'),
    'photo': fields.String(description='URL изображения в MinIO или внешний URL')
})

favorite_model = api.model('Favorite', {
    'set_id': fields.Integer(required=True, description='ID набора для добавления в избранное')
})

@api.route('/search')
class SearchSets(Resource):
    @api.marshal_with(set_model, as_list=True)
    @api.doc(params={'q': 'Поисковый запрос (имя, производитель, категория, ширина или высота)'})
    def get(self):
        query = request.args.get('q', '').strip()
        if not query:
            return [], 200
        query_terms = query.split()
        filters = []
        for term in query_terms:
            try:
                num = int(term)
                filters.append((Set.width == num) | (Set.height == num))
            except ValueError:
                filters.append(
                    (Set.name.ilike(f'%{term}%')) |
                    (Set.manufacturer.ilike(f'%{term}%')) |
                    (Set.category.ilike(f'%{term}%'))
                )
        if filters:
            query_filter = filters[0]
            for f in filters[1:]:
                query_filter = query_filter & f
            sets = Set.query.filter(query_filter).all()
        else:
            sets = Set.query.all()
        return [{
            'id': s.id,
            'manufacturer': s.manufacturer,
            'name': s.name,
            'category': s.category,
            'description': s.description,
            'width': s.width,
            'height': s.height,
            'photo': f"http://localhost:9000/{MINIO_BUCKET}/{s.photo}" if s.photo and not s.photo.startswith('http') else s.photo
        } for s in sets], 200

@api.route('/favorites/add')
class AddFavorite(Resource):
    @token_required
    @api.expect(favorite_model)
    @api.doc(responses={201: 'Набор добавлен в избранное', 400: 'Набор уже в избранном', 404: 'Набор не найден'})
    def post(self, user_id):
        data = request.get_json()
        set_id = data.get('set_id')
        if not set_id:
            return {'message': 'set_id обязателен!'}, 400

        if not Set.query.get(set_id):
            return {'message': 'Набор не найден!'}, 404

        existing = FavoriteSet.query.filter_by(user_id=user_id, set_id=set_id).first()
        if existing:
            return {'message': 'Набор уже в избранном!'}, 400

        try:
            favorite = FavoriteSet(user_id=user_id, set_id=set_id)
            db.session.add(favorite)
            db.session.commit()
            logger.info(f'Set {set_id} added to favorites by user_id: {user_id}')
            return {'message': 'Набор добавлен в избранное!'}, 201
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error adding favorite: {str(e)}', exc_info=True)
            return {'message': 'Ошибка сервера', 'error': str(e)}, 500

@api.route('/favorites/<int:set_id>')
class RemoveFavorite(Resource):
    @token_required
    @api.doc(responses={200: 'Набор удален из избранного', 404: 'Набор не найден в избранном', 401: 'Токен неверный'})
    def delete(self, user_id, set_id):
        favorite = FavoriteSet.query.filter_by(user_id=user_id, set_id=set_id).first()
        if not favorite:
            logger.warning(f'Favorite set {set_id} not found for user_id: {user_id}')
            return {'message': 'Набор не найден в избранном!'}, 404

        try:
            db.session.delete(favorite)
            db.session.commit()
            logger.info(f'Set {set_id} removed from favorites by user_id: {user_id}')
            return {'message': 'Набор удален из избранного!'}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error removing favorite: {str(e)}', exc_info=True)
            return {'message': 'Ошибка сервера', 'error': str(e)}, 500

@api.route('/favorites')
class GetFavorites(Resource):
    @token_required
    @api.marshal_with(set_model, as_list=True)
    @api.doc(responses={200: 'Список избранных наборов', 401: 'Токен неверный'})
    def get(self, user_id):
        try:
            favorites = FavoriteSet.query.filter_by(user_id=user_id).all()
            logger.info(f"Found {len(favorites)} favorite entries for user_id: {user_id}")

            result = []
            for f in favorites:
                if f.set is None:
                    logger.warning(f"No Set found for favorite with set_id: {f.set_id}, user_id: {user_id}")
                    continue
                set_data = {
                    'id': f.set.id,
                    'manufacturer': f.set.manufacturer,
                    'name': f.set.name,
                    'category': f.set.category,
                    'description': f.set.description,
                    'width': f.set.width,
                    'height': f.set.height,
                    'photo': f"http://localhost:9000/{MINIO_BUCKET}/{f.set.photo}" if f.set.photo and not f.set.photo.startswith('http') else f.set.photo
                }
                result.append(set_data)
            logger.info(f"Returning {len(result)} favorite sets for user_id: {user_id}")
            return result, 200
        except Exception as e:
            logger.error(f'Error getting favorites: {str(e)}', exc_info=True)
            return {'message': 'Ошибка сервера', 'error': str(e)}, 500

# Проверка допустимых форматов файлов
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Кастомизация формы для поддержки загрузки файлов
class SetAdminForm(Form):
    manufacturer = StringField('Manufacturer', [validators.DataRequired()])
    name = StringField('Name', [validators.DataRequired()])
    category = StringField('Category', [validators.DataRequired()])
    description = TextAreaField('Description', [validators.DataRequired()])
    width = IntegerField('Width', [validators.DataRequired()])
    height = IntegerField('Height', [validators.DataRequired()])
    photo = FileField('Photo', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')])

# Кастомный ModelView для Set
class SetAdmin(ModelView):
    form = SetAdminForm
    column_list = ['manufacturer', 'name', 'category', 'description', 'width', 'height', 'photo']
    form_columns = ['manufacturer', 'name', 'category', 'description', 'width', 'height', 'photo']
    
    # Отображение фотографии в списке
    def _photo_formatter(view, context, model, name):
        if model.photo and not model.photo.startswith('http'):
            return f'<a href="http://localhost:9000/{MINIO_BUCKET}/{model.photo}" target="_blank">View Photo</a>'
        elif model.photo:
            return f'<a href="{model.photo}" target="_blank">View Photo</a>'
        return ''

    column_formatters = {
        'photo': _photo_formatter
    }

    def create_model(self, form):
        try:
            model = self.model()
            # Вручную заполняем поля, исключая photo
            model.manufacturer = form.manufacturer.data
            model.name = form.name.data
            model.category = form.category.data
            model.description = form.description.data
            model.width = form.width.data
            model.height = form.height.data
            
            # Добавляем модель в сессию и получаем ID
            self.session.add(model)
            self.session.flush()  # Получаем model.id без коммита

            # Обрабатываем фото, если оно загружено
            if form.photo.data:
                file = form.photo.data
                if file and allowed_file(file.filename):
                    filename = f"set_{model.id}_{datetime.utcnow().timestamp()}_{secure_filename(file.filename)}"
                    try:
                        minio_client.put_object(
                            MINIO_BUCKET,
                            filename,
                            file.stream,
                            length=-1,
                            part_size=5*1024*1024,
                            content_type=file.mimetype
                        )
                        model.photo = filename
                        logger.info(f"Фотография {filename} загружена в MinIO")
                    except S3Error as e:
                        logger.error(f"Ошибка загрузки в MinIO: {e}")
                        self.session.rollback()
                        raise ValueError("Ошибка загрузки фотографии в MinIO")
                else:
                    self.session.rollback()
                    raise ValueError("Недопустимый формат файла (PNG, JPG, JPEG)")

            self.session.commit()
            self.after_model_change(form, model, True)
            return model
        except Exception as ex:
            logger.error(f"Ошибка создания записи: {str(ex)}")
            self.session.rollback()
            raise

    def update_model(self, form, model):
        try:
            # Вручную обновляем поля, исключая photo
            model.manufacturer = form.manufacturer.data
            model.name = form.name.data
            model.category = form.category.data
            model.description = form.description.data
            model.width = form.width.data
            model.height = form.height.data

            # Обрабатываем фото, если оно загружено
            if form.photo.data:
                file = form.photo.data
                if file and allowed_file(file.filename):
                    # Удаляем старую фотографию, если она есть
                    if model.photo and not model.photo.startswith('http'):
                        try:
                            minio_client.remove_object(MINIO_BUCKET, model.photo)
                            logger.info(f"Старая фотография {model.photo} удалена из MinIO")
                        except S3Error as e:
                            logger.error(f"Ошибка удаления старой фотографии: {e}")

                    filename = f"set_{model.id}_{datetime.utcnow().timestamp()}_{secure_filename(file.filename)}"
                    try:
                        minio_client.put_object(
                            MINIO_BUCKET,
                            filename,
                            file.stream,
                            length=-1,
                            part_size=5*1024*1024,
                            content_type=file.mimetype
                        )
                        model.photo = filename
                        logger.info(f"Фотография {filename} загружена в MinIO")
                    except S3Error as e:
                        logger.error(f"Ошибка загрузки в MinIO: {e}")
                        self.session.rollback()
                        raise ValueError("Ошибка загрузки фотографии в MinIO")
                else:
                    self.session.rollback()
                    raise ValueError("Недопустимый формат файла (PNG, JPG, JPEG)")

            self.session.commit()
            self.after_model_change(form, model, False)
            return True
        except Exception as ex:
            logger.error(f"Ошибка обновления записи: {str(ex)}")
            self.session.rollback()
            return False

class FavoriteSetAdmin(ModelView):
    column_list = ['user_id', 'set_id', 'added_at']
    form_columns = ['user_id', 'set_id']
    form_base_class = SecureForm

admin = Admin(app, name='Sets Admin', template_mode='bootstrap3')
admin.add_view(SetAdmin(Set, db.session))
admin.add_view(FavoriteSetAdmin(FavoriteSet, db.session))

if __name__ == '__main__':
    init_app()
    app.run(host='0.0.0.0', port=5005)