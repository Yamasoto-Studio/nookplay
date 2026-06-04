FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "from app import init_db; init_db()"

EXPOSE 80

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:80", "--workers", "2", "--timeout", "120"]