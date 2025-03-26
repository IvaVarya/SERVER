import pytest
from post_service import app, db, Post, Like, Comment
from flask import json
import jwt
import datetime

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()

@pytest.fixture
def token(client):
    token = jwt.encode({
        'user_id': 1,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'])
    return token

# Тесты для /posts (POST) — только текст
def test_create_post_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    data = {"text": "Test post"}
    response = client.post('/posts', headers=headers, json=data)
    assert response.status_code == 201
    assert "Пост успешно создан" in response.data.decode('utf-8')
    assert Post.query.count() == 1

# Тесты для /posts/<post_id> (GET)
def test_get_post_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    post = Post(user_id=1, text="Test post")
    db.session.add(post)
    db.session.commit()
    response = client.get(f'/posts/{post.id}', headers=headers)
    assert response.status_code == 200
    assert b"Test post" in response.data

# Тесты для /posts/like
def test_like_post_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    post = Post(user_id=1, text="Test post")
    db.session.add(post)
    db.session.commit()
    data = {"post_id": post.id}
    response = client.post('/posts/like', headers=headers, json=data)
    assert response.status_code == 201
    assert "Лайк успешно поставлен" in response.data.decode('utf-8')
    assert Like.query.count() == 1

# Тесты для /posts/comment
def test_comment_post_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    post = Post(user_id=1, text="Test post")
    db.session.add(post)
    db.session.commit()
    data = {"post_id": post.id, "text": "Nice post!"}
    response = client.post('/posts/comment', headers=headers, json=data)
    assert response.status_code == 201
    assert "Комментарий успешно добавлен" in response.data.decode('utf-8')
    assert Comment.query.count() == 1

# Тесты для /posts/<post_id>/comments
def test_get_comments_success(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    post = Post(user_id=1, text="Test post")
    db.session.add(post)
    db.session.commit()
    comment = Comment(user_id=1, post_id=post.id, text="Nice post!")
    db.session.add(comment)
    db.session.commit()
    response = client.get(f'/posts/{post.id}/comments', headers=headers)
    assert response.status_code == 200
    assert b"Nice post!" in response.data