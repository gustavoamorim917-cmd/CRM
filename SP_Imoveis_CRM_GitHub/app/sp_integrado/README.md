# SP Imoveis CRM / WhatsApp

Aplicacao local em Flask que integra:

- CRM visual em colunas: Ativo, Negociando, Fechado, Corretores e Proprietarios.
- Historico interno de conversa/notas por contato.
- Abertura rapida do WhatsApp Web por contato.
- Disparador de WhatsApp baseado no app existente.
- Seletor de imoveis baseado na planilha do IMOBIZI.

## Como rodar

No Windows, de dois cliques em:

```text
INICIAR_APP.bat
```

O inicializador escolhe uma porta livre automaticamente e abre o navegador quando o servidor estiver pronto.

Importante: mantenha a janela do inicializador aberta enquanto estiver usando o app. Se ela for fechada, o navegador vai mostrar que `127.0.0.1` recusou a conexao.

Depois acesse:

```text
http://127.0.0.1:5003
```

O inicializador tenta usar a porta 5003. Se ela estiver ocupada, ele procura outra porta livre entre 5000 e 5020.

## Para iniciar sozinho com o Windows

Execute uma vez:

```text
INSTALAR_INICIAR_COM_WINDOWS.bat
```

Depois disso, ao entrar no Windows, o app inicia sozinho em:

```text
http://127.0.0.1:5003
```

Para remover essa inicializacao automatica:

```text
REMOVER_INICIAR_COM_WINDOWS.bat
```

Para parar servidores antigos que tenham ficado presos, execute:

```text
PARAR_APP.bat
```

## Observacao importante

Esta versao organiza conversas e atividades dentro do CRM e abre o WhatsApp Web para contato/envio. Para sincronizar mensagens reais automaticamente dentro do painel, sera necessario conectar uma API oficial do WhatsApp Business/Cloud API ou uma automacao especifica do WhatsApp Web.

## Integracao com N8N

Leia `INTEGRACAO_N8N.md` para importar o workflow integrado, configurar `.env` e testar o fluxo CRM -> N8N -> seletor -> disparo -> CRM.

## Atualizacoes sem perda de dados

Os dados do CRM ficam em `data\crm.sqlite3` ou na pasta definida por `CRM_DATA_DIR`. Antes de atualizar, rode `BACKUP_DADOS_CRM.ps1`.

Para aplicar um pacote novo sem sobrescrever leads, notas e uploads, use:

```powershell
.\ATUALIZAR_SEM_PERDER_DADOS.ps1 -TargetAppPath "C:\caminho\do\app\sp_integrado" -StopRunning
```
