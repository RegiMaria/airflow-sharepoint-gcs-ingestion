# ADR-003: Estratégia de Tratamento de Erros

## Status
Accepted

## Data
2026-03-21

---

## Contexto

A implementação inicial utilizava blocos genéricos de tratamento de exceções:

```python
except Exception as exc:  # noqa: BLE001

## Contexto

Esse padrão introduzia problemas críticos no sistema:

- Erros reais eram **silenciosamente suprimidos**
- Dificuldade de diagnóstico (debugging)
- Falta de previsibilidade no comportamento do pipeline
- Possibilidade de mascarar bugs críticos
- Baixa observabilidade em ambiente de produção

Além disso, não havia distinção clara entre:

### Erros esperados (operacionais)

- Falhas de rede
- Arquivos não encontrados
- Problemas de permissão

### Erros inesperados (críticos)

- Bugs de código (`AttributeError`)
- Problemas de memória (`MemoryError`)
- Interrupções do sistema (`KeyboardInterrupt`)

Isso tornava o sistema frágil e difícil de manter.

## Decisão

Adotar uma estratégia explícita e controlada de tratamento de erros baseada nos seguintes princípios:

- Capturar apenas exceções esperadas  
- Propagar erros críticos (fail fast)  
- Garantir visibilidade total de falhas  
- Permitir continuidade controlada em falhas parciais  
- Melhorar logging com contexto  

## Implementação

### 1. Substituição de bare exception

**Antes:**

```python
except Exception:

except (HTTPError, Timeout, Forbidden, NotFound, OSError) as exc:

2. Tratamento por tipo de exceção

### 2. Tratamento por tipo de exceção

| Exceção | Antes | Depois |
|--------|-------|--------|
| `requests.exceptions.HTTPError` (401, 404) | ✔️ Capturada | ✔️ Capturada |
| `requests.exceptions.Timeout` | ✔️ Capturada | ✔️ Capturada |
| `google_exceptions.Forbidden` | ✔️ Capturada | ✔️ Capturada |
| `google_exceptions.NotFound` | ✔️ Capturada | ✔️ Capturada |
| `OSError` | ✔️ Capturada | ✔️ Capturada |
| `MemoryError` | ❌ Engolida silenciosamente | ✔️ Propaga |
| `AttributeError` | ❌ Engolida silenciosamente | ✔️ Propaga |
| `KeyboardInterrupt` | ⚠️ Engolida* | ✔️ Propaga |


Erros que indicam falhas estruturais do sistema não são capturados:

MemoryError
AttributeError
KeyboardInterrupt

Esses erros agora:

Interrompem a execução imediatamente
Tornam falhas visíveis
Evitam estados inconsistentes no pipeline
4. Continuidade controlada (falhas parciais)

Durante o processamento de múltiplos arquivos:

Falhas individuais não interrompem o pipeline inteiro
Arquivos válidos continuam sendo processados

Casos tratados

Falha de download
Falha de upload
Arquivo inválido

Comportamento

Log do erro com contexto (arquivo, operação)
Continuação do loop
Registro de falhas para análise posterior

5. Logging estruturado

Melhorias implementadas:

Inclusão de contexto nas mensagens:

Nome do arquivo
Tipo de operação (download/upload)

Diferenciação entre:
Falha parcial
Falha total

Logs mais úteis para debugging e monitoramento

Resultado
Eliminação de falhas silenciosas
Separação clara entre erros operacionais e críticos

Comportamento previsível do pipeline

Melhor capacidade de diagnóstico

Base preparada para observabilidade futura

Consequências
Positivas

Maior confiabilidade do sistema
Debug mais eficiente
Redução de comportamento inesperado
Melhor alinhamento com boas práticas de engenharia

Trade-offs
Código mais explícito (e ligeiramente mais verboso)
Necessidade de mapear exceções relevantes
Maior esforço inicial de implementação

Considerações futuras
Implementar retry com backoff para erros transitórios (HTTP 429, timeout)
Integrar com ferramentas de observabilidade (logs centralizados, métricas)
Classificar erros por severidade (warning vs error vs critical)
Adicionar alertas automáticos para falhas críticas

Conclusão

A adoção de uma estratégia explícita de tratamento de erros elevou significativamente a robustez do sistema.

A remoção de exceções genéricas e a separação entre erros operacionais e críticos garantem maior previsibilidade, segurança e confiabilidade, tornando o pipeline mais adequado para ambientes de produção.