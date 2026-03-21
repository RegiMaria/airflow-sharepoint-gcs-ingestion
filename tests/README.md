# SharePoint → GCS Airflow Pipeline

Pipeline de ingestão automática de documentos do **Microsoft SharePoint** para o **Google Cloud Storage (GCS)**, orquestrado com **Apache Airflow** e containerizado com **Docker**.

---

## Sumário

1. [Arquitetura](#arquitetura)
2. [Estrutura de Pastas](#estrutura-de-pastas)
3. [Pré-requisitos](#pré-requisitos)
4. [Passo a Passo de Configuração](#passo-a-passo)
5. [Executando o Projeto](#executando-o-projeto)
6. [Variáveis e Connections do Airflow](#variáveis-e-connections)
7. [Alertas por E-mail](#alertas-por-e-mail)
8. [Testes](#testes)
9. [Boas Práticas Adotadas](#boas-práticas)
10. [Troubleshooting](#troubleshooting)

---

## Arquitetura

```
SharePoint (OneDrive/Graph API)
        │
        │  [Sensor — a cada 30 min]
        │  Detecta arquivos novos/modificados
        ▼
  Apache Airflow (Docker)
  ┌─────────────────────────┐
  │  DAG: sharepoint_to_gcs │
  │                         │
  │  start                  │
  │    └─► sensor           │  ← SharePointNewFilesSensor
  │          └─► operator   │  ← SharePointToGCSOperator
  │                └─► end  │
  └─────────────────────────┘
        │
        │  Upload via google-cloud-storage
        ▼
  GCS — Data Lake
  gs://meu-bucket/raw/sharepoint/YYYY/MM/DD/arquivo.ext
        │
        └─► [Notificação por e-mail]
```

---

## Estrutura de Pastas

```
sharepoint-to-gcs/
├── dags/
│   └── sharepoint_to_gcs_dag.py       # DAG principal
├── plugins/
│   ├── hooks/
│   │   └── sharepoint_hook.py         # Hook Microsoft Graph API
│   ├── operators/
│   │   └── sharepoint_to_gcs_operator.py  # Operator de transferência
│   └── sensors/
│       └── sharepoint_new_files_sensor.py # Sensor de novos arquivos
├── config/
│   ├── airflow_variables.json         # Variáveis para importar no Airflow
│   ├── airflow_connections.json       # Connections para importar no Airflow
│   └── gcp-service-account.json       # ⚠️  NÃO commitar — adicionar manualmente
├── docker/
│   └── Dockerfile                     # Imagem customizada do Airflow
├── scripts/
│   ├── setup.sh                       # Configuração inicial do ambiente
│   └── start.sh                       # Sobe o ambiente completo
├── tests/
│   ├── unit/
│   │   └── test_sharepoint_sensor.py  # Testes unitários
│   └── integration/                   # Testes de integração (a implementar)
├── logs/                              # Logs do Airflow (gerado automaticamente)
├── .env.example                       # Template de variáveis de ambiente
├── .gitignore
├── docker-compose.yml                 # Orquestração dos containers
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Pré-requisitos

| Ferramenta | Versão mínima | Verificar |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Python | 3.11+ (local, para testes) | `python3 --version` |
| Conta Azure AD | App Registration com `Sites.Read.All` | Portal Azure |
| Conta GCP | Service Account com `roles/storage.objectCreator` | Console GCP |

---

## Passo a Passo

### Passo 1 — Clonar o repositório

```bash
git clone https://github.com/RegiMaria/airflow-sharepoint-gcs-ingestion.git
cd sharepoint-to-gcs
```

### Passo 2 — Configurar o Azure AD (SharePoint)

1. Acesse o [Portal Azure](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**
2. Dê um nome (ex: `airflow-sharepoint-reader`) e registre
3. Vá em **Certificates & secrets** → **New client secret** → copie o valor
4. Vá em **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**
5. Adicione: `Sites.Read.All` e `Files.Read.All`
6. Clique em **Grant admin consent**
7. Anote: `Tenant ID`, `Client ID`, `Client Secret`

### Passo 3 — Configurar o GCP (Service Account)

```bash
# Cria a service account
gcloud iam service-accounts create airflow-gcs-writer \
  --display-name="Airflow GCS Writer"

# Concede permissão de escrita no bucket
gcloud storage buckets add-iam-policy-binding gs://SEU_BUCKET \
  --member="serviceAccount:airflow-gcs-writer@SEU_PROJETO.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

# Gera e baixa a chave JSON
gcloud iam service-accounts keys create config/gcp-service-account.json \
  --iam-account="airflow-gcs-writer@SEU_PROJETO.iam.gserviceaccount.com"
```

### Passo 4 — Configurar variáveis de ambiente

```bash
# Executa o setup automático (cria .env, gera chaves, cria diretórios)
chmod +x scripts/setup.sh
./scripts/setup.sh

# Edite o .env com seus valores reais
nano .env   # ou code .env / vim .env
```

Preencha no `.env`:

```env
AZURE_TENANT_ID=seu-tenant-id
AZURE_CLIENT_ID=seu-client-id
AZURE_CLIENT_SECRET=seu-client-secret
SHAREPOINT_SITE_URL=https://seudominio.sharepoint.com/sites/seu-site
GCS_DATALAKE_BUCKET=nome-do-seu-bucket
SMTP_USER=seu-email@gmail.com
SMTP_PASSWORD=sua-senha-de-app   # Senha de App do Gmail, não a senha normal
ALERT_EMAIL=data-team@company.com
```

### Passo 5 — Subir o ambiente

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

O script vai:
- Fazer o build da imagem Docker customizada
- Inicializar o banco de dados do Airflow
- Criar o usuário admin
- Subir todos os serviços (webserver, scheduler, worker, triggerer)
- Importar as variáveis e connections automaticamente

### Passo 6 — Configurar Connections na UI do Airflow

Acesse `http://localhost:8080` → **Admin** → **Connections**

#### Connection: `sharepoint_default`

| Campo | Valor |
|---|---|
| Conn Id | `sharepoint_default` |
| Conn Type | `HTTP` |
| Host | `https://graph.microsoft.com` |
| Login | `SEU_CLIENT_ID` |
| Password | `SEU_CLIENT_SECRET` |
| Extra | `{"tenant_id": "SEU_TENANT_ID"}` |

#### Connection: `google_cloud_default`

| Campo | Valor |
|---|---|
| Conn Id | `google_cloud_default` |
| Conn Type | `Google Cloud` |
| Project Id | `SEU_GCP_PROJECT` |
| Keyfile Path | `/opt/airflow/config/gcp-service-account.json` |

### Passo 7 — Ativar a DAG

1. Acesse `http://localhost:8080`
2. Localize a DAG `sharepoint_to_gcs`
3. Clique no toggle para **ativar**
4. Opcionalmente, clique em **Trigger DAG** para executar manualmente

---

## Variáveis e Connections

### Importar em lote via CLI

```bash
# Variáveis
docker-compose exec airflow-webserver \
  airflow variables import /opt/airflow/config/airflow_variables.json

# Connections
docker-compose exec airflow-webserver \
  airflow connections import /opt/airflow/config/airflow_connections.json
```

### Variáveis disponíveis

| Variável | Descrição | Padrão |
|---|---|---|
| `sharepoint_site_url` | URL do site SharePoint | — |
| `sharepoint_folder_path` | Pasta monitorada | `/Shared Documents` |
| `sharepoint_sync_schedule` | Cron da DAG | `*/30 * * * *` |
| `gcs_datalake_bucket` | Nome do bucket GCS | — |
| `gcs_destination_prefix` | Prefixo no bucket | `raw/sharepoint` |
| `alert_email` | E-mail(s) para alertas | — |

---

## Alertas por E-mail

O sistema envia alertas automáticos quando:

- ✅ **Novos arquivos são ingeridos com sucesso** — lista todos os objetos GCS criados
- ❌ **Falha parcial ou total** — lista arquivos que não foram processados
- ⚠️ **Falha na DAG** — configurado via `email_on_failure: True` no `default_args`

Para usar Gmail, gere uma **Senha de App** em: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

---

## Testes

```bash
# Instalar dependências de teste localmente
pip install pytest pytest-mock apache-airflow

# Rodar testes unitários
pytest tests/unit/ -v

# Rodar com cobertura
pip install pytest-cov
pytest tests/ --cov=plugins --cov-report=html
```

---

## Boas Práticas Adotadas

### Docker
- **Multi-stage build** — imagem final sem ferramentas de compilação
- **Usuário não-root** (`airflow`, UID 50000) em todos os containers
- **Health checks** em todos os serviços
- **Restart policy** `unless-stopped` para resiliência
- **Secrets via variáveis de ambiente** — nunca hard-coded
- **Volumes nomeados** para persistência do banco de dados

### Airflow
- **CeleryExecutor** com Redis para escalabilidade horizontal
- **`mode="reschedule"`** no sensor — não bloqueia slots de worker
- **`max_active_runs=1`** — evita execuções paralelas conflitantes
- **`catchup=False`** — não executa runs históricas ao ativar a DAG
- **`soft_fail=True`** no sensor — não falha a DAG quando não há arquivos novos
- **`retry_exponential_backoff=True`** — backoff inteligente em falhas
- **XCom** para passagem de dados entre tasks (sem acoplamento direto)
- **Airflow Variables** para toda configuração — sem hard-code no código

### Segurança
- `.env` no `.gitignore` — credenciais nunca vão para o repositório
- `gcp-service-account.json` no `.gitignore`
- `FERNET_KEY` e `WEBSERVER_SECRET_KEY` geradas automaticamente
- Princípio do menor privilégio nas permissões IAM (GCP e Azure)

---

## Troubleshooting

**Erro: `FERNET_KEY` não definida**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Cole o resultado em FERNET_KEY no .env
```

**Erro de permissão nos logs**
```bash
mkdir -p logs && chmod 777 logs
```

**Worker não conecta ao Redis**
```bash
docker-compose logs redis
docker-compose restart redis
```

**Sensor não detecta arquivos**
- Verifique se o App Registration do Azure tem `Sites.Read.All` com **admin consent** concedido
- Teste manualmente: `docker-compose exec airflow-worker python3 -c "from plugins.hooks.sharepoint_hook import SharePointHook; ..."`

**Upload GCS falha**
- Verifique se o arquivo `config/gcp-service-account.json` é válido
- Confirme que a Service Account tem `roles/storage.objectCreator` no bucket correto

---

## Parando o ambiente

```bash
# Para os containers (mantém volumes)
docker-compose down

# Para e remove volumes (reset total)
docker-compose down -v
```
