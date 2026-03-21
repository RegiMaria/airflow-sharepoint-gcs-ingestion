#!/usr/bin/env bash
# scripts/setup.sh
# Script de configuração inicial do ambiente
set -euo pipefail

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# 1. Verifica pré-requisitos
# ---------------------------------------------------------------------------
log_info "Verificando pré-requisitos..."

for cmd in docker docker-compose python3; do
  if ! command -v "$cmd" &>/dev/null; then
    log_error "Comando '$cmd' não encontrado. Instale antes de continuar."
    exit 1
  fi
done
log_info "Pré-requisitos OK."

# ---------------------------------------------------------------------------
# 2. Cria .env a partir do exemplo
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
  cp .env.example .env
  log_warn ".env criado a partir do .env.example. Edite-o com seus valores reais!"
else
  log_info ".env já existe. Pulando criação."
fi

# ---------------------------------------------------------------------------
# 3. Cria diretórios necessários
# ---------------------------------------------------------------------------
log_info "Criando diretórios de trabalho..."
mkdir -p logs config

# Placeholder para a service account — não faz commit deste arquivo!
if [ ! -f "config/gcp-service-account.json" ]; then
  echo '{}' > config/gcp-service-account.json
  log_warn "config/gcp-service-account.json criado como placeholder."
  log_warn "Substitua pelo seu arquivo real de Service Account do GCP!"
fi

# ---------------------------------------------------------------------------
# 4. Gera chaves de segurança do Airflow (se não existirem no .env)
# ---------------------------------------------------------------------------
log_info "Verificando chaves de segurança..."

if grep -q "SUA_FERNET_KEY_AQUI" .env 2>/dev/null; then
  FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  sed -i "s|SUA_FERNET_KEY_AQUI|${FERNET_KEY}|g" .env
  log_info "FERNET_KEY gerada e aplicada no .env."
fi

if grep -q "SUA_WEBSERVER_SECRET_KEY_AQUI" .env 2>/dev/null; then
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s|SUA_WEBSERVER_SECRET_KEY_AQUI|${SECRET_KEY}|g" .env
  log_info "WEBSERVER_SECRET_KEY gerada e aplicada no .env."
fi

# ---------------------------------------------------------------------------
# 5. Configura permissões dos logs
# ---------------------------------------------------------------------------
AIRFLOW_UID=${AIRFLOW_UID:-50000}
log_info "Configurando permissões (UID=${AIRFLOW_UID})..."
mkdir -p logs
echo -e "AIRFLOW_UID=${AIRFLOW_UID}" >> .env 2>/dev/null || true

log_info "✅ Setup concluído!"
log_info ""
log_info "Próximos passos:"
log_info "  1. Edite o arquivo .env com suas credenciais reais"
log_info "  2. Adicione o arquivo real de Service Account GCP em config/gcp-service-account.json"
log_info "  3. Execute: ./scripts/start.sh"
