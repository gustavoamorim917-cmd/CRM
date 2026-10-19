# SP Imóveis — CRM + Seletor de Imóveis + Disparador WhatsApp + N8N

Aplicação local (Flask) para imobiliárias, com:

- **CRM** visual em colunas (Ativo, Negociando, Fechado, Corretores, Proprietários), notas e histórico por contato;
- **Seletor de imóveis** a partir da planilha exportada do Imobzi, com geração de apresentações HTML/PDF;
- **Disparador de WhatsApp** via WhatsApp Web (Selenium);
- **Integração com N8N** (webhooks e API local);
- **Automações** que baixam relatórios de imóveis e leads do Imobzi.

> Este repositório contém apenas o código. Nenhum banco de dados, planilha, credencial ou dado de cliente está incluído — o app cria um banco vazio no primeiro uso.

## Estrutura

```text
app/sp_integrado/        App Flask (app.py, templates, static, scripts .bat/.ps1)
AUTOMAÇÔES/Imoveis/      Download/unificação do relatório de imóveis do Imobzi
AUTOMAÇÔES/Relatório_Leads/  Download do relatório de leads do Imobzi
Atualização externa/     Coletor de anúncios VivaReal (opcional)
n8n/                     Workflows para importar no N8N
Apresentações/           Saída das apresentações geradas pelo Seletor (vazia)
```

## Requisitos

- Windows 10/11
- Python 3.11 ou 3.12 (marque **Add python.exe to PATH** na instalação)
- Google Chrome atualizado

## Instalação

1. Clone ou baixe este repositório:

   ```powershell
   git clone https://github.com/<seu-usuario>/<seu-repo>.git
   ```

2. Copie o arquivo de configuração de exemplo:

   ```powershell
   cd app\sp_integrado
   copy .env.example .env
   ```

3. Edite o `.env` e preencha o que for usar (todos os campos são opcionais para abrir o app):

   | Variável | Para quê |
   |---|---|
   | `PDF_CONTACT_NAME`, `PDF_CONTACT_WHATSAPP_*` | Seu nome e WhatsApp nas apresentações geradas |
   | `PROPERTY_BASE_URL` | Prefixo do link público de cada imóvel no seu site |
   | `IMOBZI_EMAIL`, `IMOBZI_SENHA`, `IMOBZI_REPORT_URL_IMOVEIS` | Botão "Atualizar" do Seletor (baixa a planilha do Imobzi) |
   | `CRM_PROPERTY_DIR` | Pasta de onde o app carrega a planilha de imóveis mais recente |
   | `CRM_DATA_DIR` | Pasta para o banco/uploads fora do código (recomendado) |
   | `N8N_CRM_WEBHOOK_URL`, `CRM_INTEGRATION_TOKEN` | Integração com o N8N |

4. Dê dois cliques em `app\sp_integrado\INICIAR_APP.bat`.

   Na primeira execução o script instala as dependências (`requirements.txt`) e abre o navegador em `http://127.0.0.1:5003` (ou outra porta livre entre 5000 e 5020, exibida na janela). Mantenha a janela aberta enquanto usa o app.

### Instalação manual (alternativa)

```powershell
cd app\sp_integrado
python -m pip install -r requirements.txt
$env:PORT = "5003"; python app.py
```

## Automações do Imobzi (opcional)

Cada pasta em `AUTOMAÇÔES` tem um `.env.example`. Copie para `.env`, preencha e instale as dependências:

```powershell
cd "AUTOMAÇÔES\Imoveis"
python -m pip install -r requirements.txt
python baixar_e_unificar_relatorios.py
```

O link do relatório (`IMOBZI_REPORT_URL_*`) é específico da sua conta: abra o relatório no Imobzi e copie a URL da barra de endereços.

## N8N (opcional)

Importe `n8n/Promptzeiros CRM Seletor Disparo Integrado.json` no N8N e configure as variáveis descritas em [n8n/README_CRM_INTEGRADO.md](n8n/README_CRM_INTEGRADO.md) e [app/sp_integrado/INTEGRACAO_N8N.md](app/sp_integrado/INTEGRACAO_N8N.md).

Os workflows `Promptzeiros AI Agent` e `Promptzeiros Outbound Disparo` usam Evolution API, OpenAI e Google Sheets: depois de importar, crie/associe suas credenciais no N8N e substitua os marcadores `https://SEU-SERVIDOR-EVOLUTION-API`, `SUA-INSTANCIA` e `COLE_AQUI_O_ID_DA_SUA_PLANILHA`.

## Mais documentação

- [app/sp_integrado/README.md](app/sp_integrado/README.md) — uso do app
- [app/sp_integrado/INSTALAR_OUTRO_PC.md](app/sp_integrado/INSTALAR_OUTRO_PC.md) — instalação em outra máquina
- [LEIA_PRIMEIRO.md](LEIA_PRIMEIRO.md) — atualizar sem perder dados

## Segurança

Nunca faça commit do arquivo `.env`, da pasta `app/sp_integrado/data/` nem de planilhas exportadas — o `.gitignore` já bloqueia esses arquivos.
