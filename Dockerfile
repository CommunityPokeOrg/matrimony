FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY matrimony ./matrimony

VOLUME /data
ENV MATRIMONY_DB_PATH=/data/matrimony.db

CMD ["python", "-m", "matrimony"]
