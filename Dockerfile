FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libjpeg-dev zlib1g-dev libfreetype6-dev libopenjp2-7-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip wheel setuptools && \
    pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY ./rules ./rules
COPY ./static ./static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
