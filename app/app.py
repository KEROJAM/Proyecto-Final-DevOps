"""
app.py - Aplicación web Flask
Soluciones Tecnológicas del Futuro
"""

from flask import Flask, jsonify, render_template_string
import os
import socket
from datetime import datetime

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>STF DevOps</title>
  <style>
    body { font-family: Arial, sans-serif; background: #0D1B2A; color: #E8EDF3;
           display: flex; justify-content: center; align-items: center;
           min-height: 100vh; margin: 0; }
    .card { background: #1A237E; border-radius: 12px; padding: 2rem 3rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4); text-align: center; }
    h1 { color: #FF6F00; margin-bottom: 0.5rem; }
    p  { color: #90A4AE; }
    .badge { background: #00838F; color: #fff; border-radius: 6px;
             padding: 0.3rem 0.8rem; font-size: 0.85rem; display: inline-block;
             margin-top: 1rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚀 STF DevOps</h1>
    <p>Plataforma Automatizada de Despliegue en AWS</p>
    <p>Host: <strong>{{ hostname }}</strong></p>
    <p>Ambiente: <strong>{{ ambiente }}</strong></p>
    <p>Hora UTC: <strong>{{ hora }}</strong></p>
    <span class="badge">Flask + nginx + Docker</span>
  </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML,
        hostname=socket.gethostname(),
        ambiente=os.getenv("AMBIENTE", "development"),
        hora=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
