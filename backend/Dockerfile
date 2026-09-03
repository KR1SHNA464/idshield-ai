FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/models /app/backend/models
RUN python /app/backend/models/download_models.py --output /app/backend/models
COPY backend/app /app/backend/app
ENV IDSHIELD_DATA_DIR=/data
RUN useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser /data
USER appuser
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
