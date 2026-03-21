#!/usr/bin/env bash
# scripts/start.sh
# Sobe o ambiente Airflow completo
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🚀 Iniciando sharepoint-to-gcs Airflow..."

# Build da imagem customizada
docker-compose build --no-cache

# Inicialização do banco e usuário admin (apenas na primeira vez)
docker-compose up airflow-init

# Sobe todos os serviços
docker-compose up -d airflow-webserver airflow-scheduler airflow-worker airflow-triggerer

echo ""
echo "✅ Ambiente iniciado!"
echo "   Webserver: http://localhost:${AIRFLOW_WEBSERVER_PORT:-8080}"
echo "   Usuário  : ${AIRFLOW_ADMIN_USER:-admin}"
echo ""

# Importa variáveis e connections após o webserver estar saudável
echo "⏳ Aguardando webserver ficar saudável..."
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${AIRFLOW_WEBSERVER_PORT:-8080}/health" > /dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "📥 Importando variáveis do Airflow..."
docker-compose exec -T airflow-webserver \
  airflow variables import /opt/airflow/config/airflow_variables.json || true

echo "🔌 Importando connections do Airflow..."
docker-compose exec -T airflow-webserver \
  airflow connections import /opt/airflow/config/airflow_connections.json || true

echo ""
echo "✅ Configuração concluída. Acesse http://localhost:${AIRFLOW_WEBSERVER_PORT:-8080}"
