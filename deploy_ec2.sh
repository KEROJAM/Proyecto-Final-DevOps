#!/bin/bash
# deploy_ec2.sh – Script de despliegue en EC2 via AWS Systems Manager
# Soluciones Tecnológicas del Futuro
#
# Este script es ejecutado por el pipeline de GitHub Actions
# a través de SSM Send-Command (sin SSH, sin abrir puertos).
#
# Flujo:
#   1. Descarga el artefacto desde S3
#   2. Detiene los contenedores actuales
#   3. Despliega la nueva versión con docker compose
#   4. Verifica que los contenedores quedaron corriendo
#   5. Registra el resultado en un log local

set -euo pipefail

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
APP_DIR="/home/ubuntu/stf-app"
LOG_FILE="/var/log/stf-deploy.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# El bucket y el SHA del commit se pasan como variables de entorno
# desde el pipeline (SSM los inyecta al comando)
BUCKET="${BUCKET_ARTEFACTOS:-}"
COMMIT_SHA="${COMMIT_SHA:-desconocido}"

# ─── FUNCIÓN DE LOG ───────────────────────────────────────────────────────────
log() {
    echo "[${TIMESTAMP}] $*" | tee -a "$LOG_FILE"
}

# ─── VALIDACIONES ─────────────────────────────────────────────────────────────
log "=========================================="
log "Iniciando deploy – commit: ${COMMIT_SHA}"
log "=========================================="

if [ -z "$BUCKET" ]; then
    log "ERROR: Variable BUCKET_ARTEFACTOS no definida."
    exit 1
fi

# Verificar que docker está disponible
export PATH="$PATH:/usr/bin:/usr/local/bin:/snap/bin"
if ! command -v docker &>/dev/null; then
    log "ERROR: Docker no está instalado o no está en el PATH."
    exit 1
fi

# ─── 1. PREPARAR DIRECTORIO ───────────────────────────────────────────────────
log "Preparando directorio $APP_DIR..."
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# ─── 2. DESCARGAR ARTEFACTO DESDE S3 ─────────────────────────────────────────
log "Descargando artefacto desde s3://${BUCKET}/artefacto.zip..."
aws s3 cp "s3://${BUCKET}/artefacto.zip" . --region us-east-1

if [ ! -f "artefacto.zip" ]; then
    log "ERROR: No se pudo descargar artefacto.zip"
    exit 1
fi
log "Artefacto descargado correctamente."

# ─── 3. DESCOMPRIMIR ──────────────────────────────────────────────────────────
log "Descomprimiendo artefacto..."
unzip -o artefacto.zip
log "Archivos extraídos."

# ─── 4. DETENER CONTENEDORES ACTUALES ────────────────────────────────────────
log "Deteniendo contenedores actuales..."
docker compose down || {
    log "WARN: No había contenedores corriendo (primer deploy)."
}

# ─── 5. LEVANTAR NUEVA VERSIÓN ────────────────────────────────────────────────
log "Construyendo y levantando contenedores..."
docker compose up -d --build

# ─── 6. VERIFICAR QUE LOS CONTENEDORES ESTÁN CORRIENDO ───────────────────────
log "Verificando estado de los contenedores..."
sleep 8

CONTENEDORES_CORRIENDO=$(docker compose ps --status running --quiet | wc -l)

if [ "$CONTENEDORES_CORRIENDO" -eq 0 ]; then
    log "ERROR: Ningún contenedor quedó en estado running."
    log "Logs de docker compose:"
    docker compose logs --tail=50 >> "$LOG_FILE" 2>&1
    exit 1
fi

log "Contenedores corriendo: $CONTENEDORES_CORRIENDO"
docker compose ps >> "$LOG_FILE" 2>&1

# ─── 7. VERIFICAR HEALTH CHECK LOCAL ─────────────────────────────────────────
log "Verificando respuesta de la aplicación en localhost..."
INTENTOS=0
MAX_INTENTOS=5

until curl -sf http://localhost/health > /dev/null 2>&1; do
    INTENTOS=$((INTENTOS + 1))
    if [ "$INTENTOS" -ge "$MAX_INTENTOS" ]; then
        log "WARN: La app no respondió en localhost:80 tras $MAX_INTENTOS intentos."
        log "      El deploy continuó pero verifica nginx manualmente."
        break
    fi
    log "Esperando respuesta... intento $INTENTOS/$MAX_INTENTOS"
    sleep 5
done

if curl -sf http://localhost/health > /dev/null 2>&1; then
    log "Health check OK – la aplicación responde en localhost:80"
fi

# ─── 8. LIMPIAR ARTEFACTO ────────────────────────────────────────────────────
log "Limpiando artefacto temporal..."
rm -f artefacto.zip

# ─── FIN ──────────────────────────────────────────────────────────────────────
log "=========================================="
log "Deploy completado exitosamente."
log "Commit: ${COMMIT_SHA}"
log "=========================================="
