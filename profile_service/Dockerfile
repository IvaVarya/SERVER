# Используем базовый образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY profile_service.py .
COPY schemas.py .

# Создаем папку для загрузки файлов
RUN mkdir uploads

# Открываем порт, который будет использовать микросервис
EXPOSE 5002

# Команда для запуска приложения
CMD ["python", "profile_service.py"]