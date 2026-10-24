FROM python:3.12-slim

# cairosvg needs the native cairo library to rasterize tree images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY matrimony ./matrimony

VOLUME /data
ENV MATRIMONY_DB_PATH=/data/matrimony.db

CMD ["python", "-m", "matrimony"]
