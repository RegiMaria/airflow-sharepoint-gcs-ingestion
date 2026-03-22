Sua organização bloqueou a criação de chaves JSON por política de segurança. 

Isso é comum em ambientes corporativos. 

Mas tem uma alternativa mais segura e que resolve o problema.

**1.Solução — Workload Identity / Application Default Credentials**

Em vez do arquivo JSON, o **Airflow vai usar as credenciais do próprio ambiente GCP**.

**Opção A** — Você está rodando em máquina pessoal (WSL)
Autentica com sua conta Google diretamente:
bash# 
Instala o gcloud no WSL se não tiver

```curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```
# Faz login
gcloud auth application-default login

# Define o projeto
gcloud config set project airflow-sharepoint-ingest
```
Isso cria um arquivo de credenciais em:
```
~/.config/gcloud/application_default_credentials.json

Depois monta esse arquivo no Docker.

No docker-compose.yml adiciona no volume do x-airflow-common:
```
yamlvolumes:
  - ~/.config/gcloud:/home/airflow/.config/gcloud:ro
```
E adiciona a variável de ambiente:
yamlenvironment:
  GOOGLE_APPLICATION_CREDENTIALS: ""
  GCLOUD_PROJECT: airflow-sharepoint-ingest

**Opção B** — Pede para o admin liberar só para seu projeto
Manda isso para o administrador da organização:

"Preciso criar uma chave JSON para a service account id-airflow-gcs-writer@airflow-sharepoint-ingest.iam.gserviceaccount.com. O tracking number é c6069658134350780."


Se você é a dona da conta, consegue liberar direto. Siga:

No Google Cloud Console
Menu → IAM & Admin → Organization Policies
Na barra de busca digita:
iam.disableServiceAccountKeyCreation
Clica na política → Manage Policy

Na tela de edição
Policy source: Override parent's policy
→ Add rule
Enforcement: Off
→ Save

Depois volta em:
IAM & Admin → Service Accounts
→ id-airflow-gcs-writer@...
→ Keys → Add Key → Create new key → JSON → Download
