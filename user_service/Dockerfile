FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY user_service.py .
COPY schemas.py .
EXPOSE 5001
CMD ["python", "user_service.py"]