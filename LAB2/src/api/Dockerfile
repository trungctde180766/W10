# LAB 2 - Dockerfile
# Dùng non-root user → pass K8sNoRunAsRoot constraint
FROM python:3.13-alpine

# Tạo user non-root
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

RUN pip install --no-cache-dir flask prometheus-flask-exporter

COPY app.py /app/app.py
WORKDIR /app

# Chạy với user non-root (UID 1000)
USER appuser

ENV FLASK_APP=app.py
EXPOSE 8080
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
