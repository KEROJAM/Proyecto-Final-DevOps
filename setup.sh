#!/bin/bash
# setup.sh - Configuración de entorno Ubuntu EC2
# Soluciones Tecnológicas del Futuro
# Uso: sudo bash setup.sh

set -euo pipefail

LOG="/var/log/setup.log"
echo "========================================" | tee -a "$LOG"
echo "Inicio setup: $(date)" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"

# ─── 1. ACTUALIZAR SISTEMA ───────────────────────────────────────────────────
echo "[1/6] Actualizando paquetes..." | tee -a "$LOG"
apt-get update -qq
apt-get upgrade -y -qq
echo "OK: Sistema actualizado" | tee -a "$LOG"

# ─── 2. INSTALAR PAQUETES ESENCIALES ─────────────────────────────────────────
echo "[2/6] Instalando paquetes esenciales..." | tee -a "$LOG"
apt-get install -y \
    git \
    vim \
    curl \
    gnupg \
    ca-certificates \
    python3 \
    python3-pip \
    unzip \
    awscli
echo "OK: Paquetes esenciales instalados" | tee -a "$LOG"

# ─── 3. INSTALAR DOCKER (repositorio oficial) ────────────────────────────────
echo "[3/6] Instalando Docker..." | tee -a "$LOG"

# Crear directorio para keyrings
install -m 0755 -d /etc/apt/keyrings

# Descargar clave GPG oficial de Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Agregar repositorio oficial de Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Agregar usuario ubuntu al grupo docker
usermod -aG docker ubuntu

# Habilitar e iniciar Docker
systemctl enable docker
systemctl start docker

echo "OK: Docker instalado ($(docker --version))" | tee -a "$LOG"

# ─── 4. INSTALAR DEPENDENCIAS PYTHON ─────────────────────────────────────────
echo "[4/6] Instalando librerías Python..." | tee -a "$LOG"
pip3 install --quiet boto3 requests
echo "OK: boto3 y requests instalados" | tee -a "$LOG"

# ─── 5. CONFIGURAR CRON PARA LIMPIEZA DE LOGS ────────────────────────────────
echo "[5/6] Configurando cron de limpieza de logs..." | tee -a "$LOG"

CRON_JOB="0 2 * * * find /var/log -name '*.log' -mtime +7 -delete >> /var/log/limpieza_logs.log 2>&1"

# Agregar solo si no existe ya
( crontab -l 2>/dev/null | grep -qF "limpieza_logs" ) \
    || ( crontab -l 2>/dev/null; echo "$CRON_JOB" ) | crontab -

echo "OK: Cron configurado (limpieza diaria a las 2 AM)" | tee -a "$LOG"

# ─── 6. VERIFICACIÓN FINAL ───────────────────────────────────────────────────
echo "[6/6] Verificación final..." | tee -a "$LOG"
echo "  Git:    $(git --version)" | tee -a "$LOG"
echo "  Python: $(python3 --version)" | tee -a "$LOG"
echo "  pip3:   $(pip3 --version)" | tee -a "$LOG"
echo "  Docker: $(docker --version)" | tee -a "$LOG"
echo "  AWS:    $(aws --version 2>&1)" | tee -a "$LOG"

echo "========================================" | tee -a "$LOG"
echo "Setup completado: $(date)" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"
echo ""
echo "IMPORTANTE: Cierra sesión y vuelve a entrar para usar Docker sin sudo."
