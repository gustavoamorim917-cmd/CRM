# Workflow CRM Integrado

Arquivo novo para importar no N8N:

```text
Promptzeiros CRM Seletor Disparo Integrado.json
```

Ele substitui, para este fluxo local, o modelo antigo baseado em Google Sheets. Os arquivos antigos foram preservados.

## Variaveis recomendadas no ambiente do N8N

```text
CRM_APP_BASE_URL=http://127.0.0.1:5003
CRM_INTEGRATION_TOKEN=
CRM_MAX_RESULTS=5
CRM_AUTO_START_BLASTER=false
CRM_BLASTER_QR_WAIT=60
CRM_BLASTER_DELAY_MIN=10
CRM_BLASTER_DELAY_MAX=20
```

Se `CRM_AUTO_START_BLASTER=false`, o N8N prepara a fila no app e registra o status. Se for `true`, o app tenta iniciar o Selenium/WhatsApp Web.

## Entrada do Webhook

```json
{
  "event": "lead_updated",
  "lead_id": 123
}
```

O app pode enviar esse payload automaticamente usando `N8N_CRM_WEBHOOK_URL`.

## Diagnostico

No N8N, use `Executions` para abrir a execucao com erro e ver qual node falhou. Este workflow registra falhas de demanda, busca sem opcoes e duplicidade de volta no CRM pelo endpoint `automation-log`.

## Credenciais

Este workflow integrado conversa com o app local por HTTP e usa variaveis de ambiente. Workflows antigos que chamam OpenAI, Evolution API ou Google Sheets podem precisar reanexar credenciais depois de importar/atualizar no N8N, pois o N8N remove credenciais em importacoes por seguranca.
