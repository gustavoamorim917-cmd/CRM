# Integracao CRM + N8N + Seletor + Disparo

Esta versao deixa o CRM como painel visual/informativo e expoe uma API local para o N8N operar o fluxo:

1. receber evento de lead novo/atualizado;
2. ler lead, notas e mensagens;
3. extrair metragem, valor e regiao;
4. consultar o seletor de imoveis;
5. montar uma mensagem comercial;
6. preparar ou iniciar o disparo;
7. registrar logs/status no CRM.

## Configuracao

Copie `.env.example` para `.env` se quiser configurar a integracao pelo proprio diretorio do app.

Campos principais:

- `CRM_APP_BASE_URL`: URL local do app, normalmente `http://127.0.0.1:5003`. Se o inicializador escolher outra porta, use a URL exibida na janela.
- `CRM_INTEGRATION_TOKEN`: token opcional. Se preenchido, o N8N deve enviar `X-Integration-Token`.
- `N8N_CRM_WEBHOOK_URL`: webhook do workflow N8N para o app notificar lead/mensagem nova.
- `CRM_PROPERTY_FILE`: caminho opcional de uma planilha fixa de imoveis. Se vazio, o app usa a ultima `data/uploads/imoveis_*`.
- `CRM_AUTO_START_BLASTER`: `true` para o N8N iniciar o Selenium automaticamente; `false` para apenas carregar a fila no disparador.

## Workflow N8N

Importe o arquivo:

```text
n8n\Promptzeiros CRM Seletor Disparo Integrado.json
```

Webhook esperado:

```text
POST /webhook/crm-lead-automation
```

Payload minimo:

```json
{
  "event": "lead_updated",
  "lead_id": 3526
}
```

Se `N8N_CRM_WEBHOOK_URL` estiver configurado no app, o CRM chama esse webhook automaticamente ao criar/editar lead ou adicionar mensagem.

## Endpoints Criados

- `GET /api/integration/leads/pending`: lista leads com demanda extraivel e ainda nao processada.
- `GET /api/integration/leads/<id>`: retorna lead, mensagens e demanda extraida.
- `POST /api/integration/leads/<id>/extract`: extrai demanda e grava status `criterios_extraidos`.
- `POST /api/integration/selector/search`: executa busca no seletor e retorna opcoes estruturadas.
- `POST /api/integration/disparo/montar`: monta mensagem comercial.
- `POST /api/integration/disparo/preparar`: carrega a mensagem no modulo de disparos e opcionalmente inicia Selenium.
- `POST /api/integration/leads/<id>/automation-result`: registra resultado final, erro ou disparo feito.
- `POST /api/integration/leads/<id>/automation-log`: registra log operacional avulso.

## Exemplo de Demanda Extraida

Entrada em nota:

```text
+300
ate 8.000
Guarulhos
```

Saida:

```json
{
  "lead_id": "3526",
  "nome": "Joao",
  "telefone": "5511999999999",
  "demanda": {
    "metragem_min": 300,
    "metragem_max": null,
    "valor_min": null,
    "valor_max": 8000,
    "regiao": "Guarulhos"
  },
  "origem": "message:3526",
  "mensagem_original": "+300\nate 8.000\nGuarulhos",
  "demand_hash": "hash_curto"
}
```

## Teste Manual Com Lead Ficticio

1. Inicie o app pelo `INICIAR_APP.bat`.
2. Crie um contato no CRM com telefone.
3. Adicione uma nota no contato:

```text
+300
ate 8.000
Guarulhos
```

4. Chame o endpoint de processamento:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:5003/api/integration/leads/ID_DO_LEAD/process" `
  -ContentType "application/json" `
  -Body '{"auto_start":false}'
```

5. Abra a tela `Disparador`: a planilha de disparo deve aparecer carregada com uma mensagem limpa.

## Duplicidade

Cada demanda gera um `demand_hash` baseado no lead e nos criterios extraidos. Se o mesmo lead tiver a mesma metragem, valor e regiao, o app bloqueia novo preparo/envio, a menos que o payload envie `"force": true`.

## Observacoes

- O envio real via Selenium ainda depende do WhatsApp Web estar operacional no computador.
- Para rodar sem abrir Selenium automaticamente, deixe `CRM_AUTO_START_BLASTER=false`.
- Para envio 100% API, mantenha o preparo/mensagem no app e adicione no N8N um node Evolution/WhatsApp antes de chamar `automation-result` com `status: "disparo_feito"`.
