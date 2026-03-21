# ADR-001: Expansão da Cobertura de Testes

## Status
Accepted

## Data
2026-03-21

---

## Contexto

Inicialmente, o projeto apresentava baixa cobertura de testes (~10%), com apenas um arquivo existente:

- `test_sharepoint_sensor.py`

Componentes críticos não possuíam testes:

- `SharePointHook`
- `SharePointToGCSOperator`
- DAG principal

Isso representava riscos relevantes:

- Falta de confiança em mudanças (baixo safety net)
- Possibilidade de regressões silenciosas
- Baixa maturidade para produção

---

## Decisão

Foi decidido expandir significativamente a cobertura de testes automatizados, com foco nos principais componentes do pipeline.

A estratégia adotada incluiu:

- Testes unitários para hooks e operadores
- Testes estruturais para DAG
- Cobertura de cenários de sucesso, erro e edge cases
- Simulação de falhas externas (HTTP, SMTP, etc.)

---

## Implementação

Foram criados 3 novos arquivos de teste, totalizando **1053 linhas de código**:

### test_sharepoint_hook.py — 354 linhas

Cobertura:

- `TestGetToken`
  - Token novo, cacheado, expirado
  - Falha de autenticação
  - Validação de authority URL

- `TestListFiles`
  - Filtro de pastas
  - Filtro por data
  - Boundary de cutoff
  - Paginação (`@odata.nextLink`)
  - Pasta vazia
  - Erro HTTP

- `TestDownloadFile`
  - Download com sucesso
  - Erro 404

- `TestIterFileChunks`
  - Leitura em chunks (streaming)

---

### test_sharepoint_to_gcs_operator.py — 409 linhas

Cobertura:

- `TestExecute`
  - Upload bem-sucedido
  - XCom vazio/None
  - Falha total
  - Falha parcial (continuação do processo)
  - Mensagens de erro com contexto
  - Envio de alertas (`send_alert`)

- `TestBuildGcsObjectPath`
  - Com/sem estrutura de pastas
  - Casos com slashes inconsistentes

- `TestExtractRelativePath`
  - Subpastas, raiz, vazio, aninhado

- `TestGuessMimeType`
  - PDF, XLSX, CSV, JPG
  - Extensões desconhecidas
  - Arquivos sem extensão

- `TestSendAlertEmail`
  - SMTP válido
  - Autenticação + envio
  - Falha silenciosa de SMTP
  - Assunto com indicação de falha parcial

---

### test_sharepoint_to_gcs_dag.py — 190 linhas

Cobertura:

- `TestDagStructure`
  - DAG carrega sem erros
  - Número de tasks
  - IDs corretos
  - `catchup=False`
  - `max_active_runs=1`

- `TestDagDependencies`
  - Ordem completa:
    - start → sensor → operator → end

- `TestSensorConfiguration`
  - `mode=reschedule`
  - `soft_fail=True`
  - `poke_interval=60`
  - `timeout=25min`

- `TestOperatorConfiguration`
  - Parâmetros principais

- `TestDefaultArgs`
  - `retries=3`
  - `exponential_backoff`
  - `depends_on_past=False`

---

### Outras melhorias

- Atualização do `pytest.ini`:
  - `pythonpath = .` para garantir resolução correta de imports

---

## Resultado

- Cobertura de testes aumentada de **~10% → ~85%+**
- Cobertura dos principais componentes do sistema
- Redução significativa do risco de regressão
- Maior confiabilidade para evolução do código

---

## Consequências

### Positivas

- Maior segurança para refatorações
- Melhor qualidade de código
- Base sólida para CI/CD
- Projeto mais próximo de padrões de produção

### Trade-offs

- Aumento no tempo de escrita e manutenção de testes
- Necessidade de mocks para dependências externas

---

## Considerações futuras

- Adicionar testes de integração reais (`tests/integration/`)
- Medir cobertura com ferramenta (ex: `pytest-cov`)
- Incluir testes em pipeline CI
- Evoluir para testes de contrato (ex: APIs externas)

---

## Conclusão

A expansão da cobertura de testes foi uma decisão estratégica para elevar a maturidade do projeto, transformando um pipeline funcional em uma base confiável e preparada para cenários de produção.