FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY feed_service.py .
EXPOSE 5003
CMD ["python", "feed_service.py"]