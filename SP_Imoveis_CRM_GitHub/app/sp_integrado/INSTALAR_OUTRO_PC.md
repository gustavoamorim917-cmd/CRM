# Instalar em outro PC

Este app roda localmente em Windows com Python 3 e Chrome instalado.

## 1. Copiar o pacote

Descompacte o ZIP em uma pasta simples, por exemplo:

```text
C:\SP_Imoveis_CRM
```

Evite pasta com sincronizacao pesada se possivel. OneDrive funciona, mas uma pasta local costuma dar menos conflito.

## 2. Instalar requisitos

Instale:

- Python 3.11 ou 3.12, marcando `Add python.exe to PATH`.
- Google Chrome atualizado.

O app instala bibliotecas Python automaticamente ao abrir pelo script.

## 3. Rodar o app

Entre na pasta:

```text
app\sp_integrado
```

Execute:

```text
INICIAR_APP.bat
```

O app tenta abrir em:

```text
http://127.0.0.1:5003
```

Se a porta estiver ocupada, o inicializador mostra a URL correta na janela.

## 4. Configurar N8N

Importe no N8N:

```text
n8n\Promptzeiros CRM Seletor Disparo Integrado.json
```

Variaveis recomendadas no ambiente do N8N:

```text
CRM_APP_BASE_URL=http://127.0.0.1:5003
CRM_INTEGRATION_TOKEN=
CRM_MAX_RESULTS=5
CRM_AUTO_START_BLASTER=false
CRM_BLASTER_QR_WAIT=60
CRM_BLASTER_DELAY_MIN=10
CRM_BLASTER_DELAY_MAX=20
```

Se o app abrir em outra porta, ajuste `CRM_APP_BASE_URL`.

## 5. Configurar notificacao CRM -> N8N

Depois de ativar o workflow no N8N, copie a URL do webhook e coloque no arquivo:

```text
app\sp_integrado\.env
```

Exemplo:

```text
CRM_APP_BASE_URL=http://127.0.0.1:5003
N8N_CRM_WEBHOOK_URL=http://127.0.0.1:5678/webhook/crm-lead-automation
CRM_AUTO_START_BLASTER=false
```

Voce pode copiar `.env.example` para `.env`.

## 6. Dados do CRM

O pacote limpo nao deve levar contatos reais. Ao iniciar, o app cria um banco novo em:

```text
app\sp_integrado\data\crm.sqlite3
```

Para migrar contatos reais de uma maquina para outra, copie manualmente esse arquivo depois, sabendo que ele contem nomes, telefones, notas e historico.

Recomendado para nao perder dados em atualizacoes futuras: deixe os dados fora da pasta do app. No `.env`, configure:

```text
CRM_DATA_DIR=C:\SP_Imoveis_CRM_Dados
```

Depois copie seu `crm.sqlite3` antigo para:

```text
C:\SP_Imoveis_CRM_Dados\crm.sqlite3
```

e os uploads para:

```text
C:\SP_Imoveis_CRM_Dados\uploads
```

## 6.1 Atualizar sem perder dados

Nunca substitua a pasta inteira do app por cima da antiga.

Quando receber um pacote novo, rode dentro do app novo:

```powershell
.\ATUALIZAR_SEM_PERDER_DADOS.ps1 -TargetAppPath "C:\SP_Imoveis_CRM\app\sp_integrado" -StopRunning
```

O script:

- faz backup de `crm.sqlite3`, uploads e `.env`;
- atualiza apenas codigo, templates, static e scripts;
- preserva `data` e `.env`;
- mostra onde o backup foi salvo.

## 7. Planilha de imoveis

No primeiro uso, carregue a planilha IMOBIZI pela tela `Seletor`.

Opcionalmente, defina no `.env`:

```text
CRM_PROPERTY_FILE=C:\caminho\para\sua_planilha_imobizi.xlsx
```

## 8. Teste rapido

1. Abra o app.
2. Crie um contato com telefone.
3. Adicione uma nota:

```text
+300
ate 8.000
Guarulhos
```

4. No N8N, execute o workflow com:

```json
{
  "event": "lead_updated",
  "lead_id": 1
}
```

5. O disparador deve receber uma mensagem pronta, sem aparecer `Nome`, `Etapa` ou o nome solto no final.
