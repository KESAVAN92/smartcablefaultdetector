FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_ENV=production
ENV MODULE1_START_BACKGROUND=0
EXPOSE 5000
CMD ["python", "app.py"]
