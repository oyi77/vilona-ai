FROM python:3.11-slim
WORKDIR /app
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt
COPY . .
ENV vilona_PAPER_TRADING=true
ENV vilona_HEADLESS=true
ENTRYPOINT ["python", "app_server.py"]
