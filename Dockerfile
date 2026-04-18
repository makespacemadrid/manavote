FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY translations.py app.py ./
COPY templates ./templates
COPY static ./static

RUN mkdir -p static/uploads

EXPOSE 5000

CMD ["python", "app.py"]
