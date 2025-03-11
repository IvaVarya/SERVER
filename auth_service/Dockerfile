# Используем базовый образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY auth_service.py .
COPY schemas.py .

# Открываем порт, который будет использовать микросервис
EXPOSE 5001

# Команда для запуска приложения
CMD ["python", "auth_service.py"]