# ══════════════════════════════════════════════════════════════════════════════
# Dockerfile – Imagen Docker para aplicación Flask (multi-stage build)
# Soluciones Tecnológicas del Futuro
#
# Etapas:
#   1. builder  → instala dependencias Python en un entorno aislado
#   2. final    → imagen de producción mínima (~120 MB vs ~1.2 GB sin optimizar)
#
# Uso:
#   docker build -t stf-web .
#   docker run -p 5000:5000 stf-web
# ══════════════════════════════════════════════════════════════════════════════


# ─── ETAPA 1: BUILDER ─────────────────────────────────────────────────────────
# Imagen completa solo para compilar/instalar dependencias.
# Esta etapa NO llega a producción.
FROM python:3.11-slim AS builder

WORKDIR /build

# Copiar solo el archivo de dependencias primero (aprovecha caché de Docker)
COPY requirements.txt .

# Instalar dependencias en un directorio aislado (--prefix)
# --no-cache-dir  → no guarda caché de pip (reduce tamaño)
# --prefix        → instala en /install para copiar fácilmente a la etapa final
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── ETAPA 2: FINAL (PRODUCCIÓN) ─────────────────────────────────────────────
# Imagen mínima: solo Python slim + código + dependencias compiladas.
# No incluye pip, compiladores ni herramientas de build.
FROM python:3.11-slim AS final

# Metadatos de la imagen
LABEL maintainer="STF DevOps <devops@stf.com>"
LABEL version="1.0"
LABEL description="Aplicación web Flask – Soluciones Tecnológicas del Futuro"

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AMBIENTE=production \
    FLASK_APP=app.py

WORKDIR /app

# Copiar dependencias instaladas desde la etapa builder
COPY --from=builder /install /usr/local

# Copiar el código fuente de la aplicación
COPY app.py .

# Crear usuario sin privilegios (nunca correr como root en producción)
RUN addgroup --system appgroup && \
    adduser  --system --ingroup appgroup appuser

# Cambiar propietario del directorio de trabajo
RUN chown -R appuser:appgroup /app

# Cambiar al usuario sin privilegios
USER appuser

EXPOSE 5000

# Health check: Docker reinicia el contenedor si /health no responde
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

# Iniciar con gunicorn (servidor WSGI de producción, no el servidor dev de Flask)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
