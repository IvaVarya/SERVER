import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_restx import Api, Resource, fields
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from prometheus_flask_exporter import PrometheusMetrics
import os

app = Flask(__name__)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus
metrics = PrometheusMetrics(app)

# Swagger
api = Api(app, version='1.0', title='Sets Service API', description='API для поиска наборов для вышивания')

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:server@db:5432/PostgreSQL'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Модель набора для вышивания
class Set(db.Model):
    __tablename__ = 'sets'
    id = db.Column(db.Integer, primary_key=True)
    manufacturer = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    width = db.Column(db.Integer, nullable=False)  # Добавляем ширину
    height = db.Column(db.Integer, nullable=False)  # Добавляем высоту
    photo = db.Column(db.String(256))

# Создание таблицы
with app.app_context():
    db.create_all()

# Модель для Swagger
set_model = api.model('Set', {
    'manufacturer': fields.String(required=True, description='Производитель'),
    'name': fields.String(required=True, description='Название набора'),
    'category': fields.String(required=True, description='Категория'),
    'description': fields.String(required=True, description='Описание'),
    'width': fields.Integer(required=True, description='Ширина в стежках'),  # Добавляем в Swagger
    'height': fields.Integer(required=True, description='Высота в стежках')  # Добавляем в Swagger
})

# Эндпоинт для поиска
@api.route('/search')
class SearchSets(Resource):
    def get(self):
        query = request.args.get('q', '')
        sets = Set.query.filter(
            (Set.name.ilike(f'%{query}%')) |
            (Set.manufacturer.ilike(f'%{query}%')) |
            (Set.category.ilike(f'%{query}%'))
        ).all()
        return [{
            'id': s.id,
            'manufacturer': s.manufacturer,
            'name': s.name,
            'category': s.category,
            'description': s.description,
            'width': s.width,  # Добавляем в ответ
            'height': s.height,  # Добавляем в ответ
            'photo': s.photo
        } for s in sets], 200

# Flask-Admin
class SetAdmin(ModelView):
    column_list = ['manufacturer', 'name', 'category', 'description', 'width', 'height', 'photo']  # Добавляем в список колонок
    form_columns = ['manufacturer', 'name', 'category', 'description', 'width', 'height', 'photo']  # Добавляем в форму

admin = Admin(app, name='Sets Admin', template_mode='bootstrap3')
admin.add_view(SetAdmin(Set, db.session))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006)