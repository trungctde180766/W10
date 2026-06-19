# LAB 2 - Flask API
# Đọc DB_PASSWORD từ K8s Secret (được ESO sync từ AWS Secrets Manager)
import os
import random
from flask import Flask, jsonify
# pyrefly: ignore [missing-import]
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)

ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
VERSION = os.getenv("VERSION", "v1")
# Đọc từ env (inject từ K8s Secret db-password)
# Không bao giờ hardcode — grep -ri password sẽ không thấy giá trị thật
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

@app.get("/")
def index():
    if random.random() < ERROR_RATE:
        return jsonify(error="injected", version=VERSION), 500
    # Không trả DB_PASSWORD trong response!
    return jsonify(ok=True, version=VERSION, db_connected=bool(DB_PASSWORD))

@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
