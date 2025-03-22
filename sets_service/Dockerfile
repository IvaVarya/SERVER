FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sets_service.py .
EXPOSE 5005
CMD ["python", "sets_service.py"]