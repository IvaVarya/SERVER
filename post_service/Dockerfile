FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY post_service.py .
COPY schemas.py .
EXPOSE 5002
CMD ["python", "post_service.py"]