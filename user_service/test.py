import pytest
from user_service import app, db, User
import jwt
import datetime

# Настройка фикстур
@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # SQLite в памяти для тестов
    with app.test_client() as client:
        with app.app_context():
            db.create_all()  # Создаём таблицы в тестовой базе
        yield client
        with app.app_context():
            db.drop_all()  # Удаляем таблицы после тестов

@pytest.fixture
def token(client):
    user_data = {
        "first_name": "Test",
        "last_name": "User",
        "login": "testuser",
        "password": "testpass",
        "confirm_password": "testpass",
        "email": "test@example.com"
    }
    client.post('/register', json=user_data)
    user = User.query.filter_by(login="testuser").first()
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return token

# Тесты для /register
def test_register_success(client):
    user_data = {
        "first_name": "John",
        "last_name": "Doe",
        "login": "johndoe",
        "password": "password123",
        "confirm_password": "password123",
        "email": "john@example.com"
    }
    response = client.post('/register', json=user_data)
    assert response.status_code == 201
    assert "token" in response.get_json()

def test_register_duplicate_login(client):
    user_data = {
        "first_name": "John",
        "last_name": "Doe",
        "login": "johndoe",
        "password": "password123",
        "confirm_password": "password123",
        "email": "john@example.com"
    }
    client.post('/register', json=user_data)  # Первая регистрация
    response = client.post('/register', json=user_data)  # Повторная
    assert response.status_code == 400
    data = response.get_json()  # Парсим JSON
    assert data["message"] == "Пользователь с таким логином уже существует."  # Исправлено

# Тесты для /login
def test_login_success(client):
    user_data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "login": "janedoe",
        "password": "password123",
        "confirm_password": "password123",
        "email": "jane@example.com"
    }
    client.post('/register', json=user_data)
    login_data = {"login": "janedoe", "password": "password123"}
    response = client.post('/login', json=login_data)
    assert response.status_code == 200
    assert "token" in response.get_json()

def test_login_invalid_password(client):
    user_data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "login": "janedoe",
        "password": "password123",
        "confirm_password": "password123",
        "email": "jane@example.com"
    }
    client.post('/register', json=user_data)
    login_data = {"login": "janedoe", "password": "wrongpass"}
    response = client.post('/login', json=login_data)
    assert response.status_code == 401
    data = response.get_json()  # Парсим JSON
    assert data["message"] == "Неверный логин или пароль."  # Исправлено

# Тесты для /profile (GET)
def test_get_profile_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get('/profile', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["login"] == "testuser"

# Тесты для /profile (PUT)
def test_update_profile_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "first_name": "Updated",
        "last_name": "UserUpdated",
        "gender": "Male",
        "country": "USA",
        "city": "New York",
        "birth_date": "1990-01-01"
    }
    response = client.put('/profile', headers=headers, json=data)
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data["message"] == "Профиль успешно обновлен!"
    user = User.query.filter_by(login="testuser").first()
    assert user.first_name == "Updated"
    assert user.birth_date == datetime.datetime.strptime("1990-01-01", '%Y-%m-%d').date()