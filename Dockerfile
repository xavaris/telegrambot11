FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget curl ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libatk1.0-0 libcups2 libdrm2 libxkbcommon0 libxshmfence1 libx11-xcb1 \
    libxcb1 libxext6 libx11-6 libglib2.0-0 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium

COPY . .

CMD ["python", "-m", "app.main"]
