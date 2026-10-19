# SP Imoveis CRM + N8N - Dados Persistentes

Este pacote foi ajustado para nao perder CRM a cada atualizacao.

## Regra principal

Nunca substitua a pasta antiga inteira por cima de uma pasta nova sem backup.

Use sempre:

```powershell
app\sp_integrado\ATUALIZAR_SEM_PERDER_DADOS.ps1 -TargetAppPath "C:\CAMINHO\DO\APP\sp_integrado" -StopRunning
```

Esse script preserva:

- `data\crm.sqlite3`
- `data\uploads`
- `.env`
- backups anteriores

e atualiza apenas:

- `app.py`
- `static`
- `templates`
- scripts
- documentacao
- workflows N8N no pacote

## Instalacao nova

1. Instale Python 3.11/3.12 e Google Chrome.
2. Descompacte o ZIP.
3. Abra:

```text
app\sp_integrado\INICIAR_APP.bat
```

4. Acesse a URL exibida, normalmente:

```text
http://127.0.0.1:5003
```

## Recomendado para producao local

Crie ou edite:

```text
app\sp_integrado\.env
```

e coloque os dados fora da pasta do app:

```text
CRM_DATA_DIR=C:\SP_Imoveis_CRM_Dados
```

Assim os dados sobrevivem mesmo que voce troque a pasta do codigo.

## Backup manual

Antes de qualquer manutencao, rode:

```powershell
app\sp_integrado\BACKUP_DADOS_CRM.ps1
```

O backup zipado fica dentro de `data\backups` ou dentro da pasta definida em `CRM_DATA_DIR`.

## N8N

Importe:

```text
n8n\Promptzeiros CRM Seletor Disparo Integrado.json
```

Configure no N8N:

```text
CRM_APP_BASE_URL=http://127.0.0.1:5003
CRM_AUTO_START_BLASTER=false
```

Se o app abrir em outra porta, ajuste `CRM_APP_BASE_URL`.
