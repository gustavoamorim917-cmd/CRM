# Automação — Relatório de Imóveis (Imobzi)

Baixa automaticamente o relatório **Imóveis - Cadastros** do Imobzi, desde
uma data configurada até hoje, para todos os usuários. O arquivo baixado é
renomeado como:

```
imoveis_DDMMAAAAvN.<extensão original>
```

Exemplo: `imoveis_25082026v1.csv`.

Se o script rodar mais de uma vez no mesmo dia, a versão sobe
automaticamente (`v1`, `v2`, `v3`...) para não sobrescrever o arquivo
anterior.

## 1. Instalação

Você precisa do Python 3.9+ e do Google Chrome instalados.

```bash
pip install -r requirements.txt
```

O script usa o `webdriver-manager` para baixar automaticamente a versão
correta do ChromeDriver — não é preciso instalar nada manualmente.

## 2. Configuração

1. Copie o arquivo `.env.example` para `.env` (mesma pasta).
2. Abra o `.env` e preencha:
   - `IMOBZI_EMAIL` — seu e-mail de login do Imobzi
   - `IMOBZI_SENHA` — sua senha do Imobzi
   - `IMOBZI_REPORT_URL_IMOVEIS` — link do relatório "Imóveis - Cadastros"
     da sua conta (abra o relatório no Imobzi e copie a URL)
   - `PASTA_DESTINO` — pasta onde o relatório final deve ficar (se vazio,
     usa a pasta deste script)

⚠️ O arquivo `.env` fica só no seu computador e nunca deve ser enviado para
ninguém, pois contém sua senha.

## 3. Uso

```bash
python baixar_relatorio_imoveis.py
```

O Chrome vai abrir sozinho, fazer login, aplicar o filtro (data até hoje,
todos os usuários), pedir a exportação e baixar o arquivo. O download pode
levar de 1 a 3 minutos, pois o Imobzi processa o relatório em segundo plano
antes de disponibilizar o download.

Ao final, o terminal mostra o caminho do arquivo salvo, por exemplo:

```
[10:42:13] Arquivo salvo como: C:\...\AUTOMAÇÔES\Imoveis\imoveis_25082026v1.csv
[10:42:13] Concluído com sucesso!
```

## 4. Rodar sem abrir a janela do Chrome (opcional)

Abra `baixar_relatorio_imoveis.py` e descomente a linha:

```python
# chrome_options.add_argument("--headless=new")
```

## 5. Baixar os dois períodos e unificar numa planilha só

Existe uma segunda cópia do script, `baixar_relatorio_imoveis - Copia.py`,
igual ao original mas com `DATA_INICIAL = "17/12/2024"` (em vez de
`01/01/2012`). Para rodar os dois períodos em sequência (cada um com seu
próprio login) e já organizar o resultado, use:

```bash
python baixar_e_unificar_relatorios.py
```

Esse script:

1. Roda `baixar_relatorio_imoveis.py` até o fim (baixa o período desde
   01/01/2012).
2. Roda `baixar_relatorio_imoveis - Copia.py` até o fim (baixa o período
   desde 17/12/2024).
3. Move os dois arquivos baixados para uma pasta NOVA, nomeada com a data
   de hoje no formato `ddmmaa` (ex.: `250826`).
4. Cria uma planilha unificada dentro dessa pasta
   (`imoveis_ddmmaa_unificado.csv`): mantém 100% do conteúdo do primeiro
   arquivo e cola, em seguida, o conteúdo do segundo arquivo a partir da
   3ª linha (as duas primeiras linhas dele são descartadas).

Se algum dos dois relatórios for exportado num formato que não seja
`.csv`/`.txt` (por exemplo `.xlsx`), a unificação automática é pulada — os
dois arquivos ainda são movidos para a pasta do dia, só não são unidos.

## Observações técnicas

- O link do relatório vem da variável `IMOBZI_REPORT_URL_IMOVEIS` no `.env`.
  Se o Imobzi gerar um novo link de relatório no futuro, basta atualizá-la.
- O Imobzi exporta o relatório como `.csv`. O script preserva a extensão que
  o Imobzi enviar, então se um dia mudar para `.xlsx` o script continua
  funcionando normalmente.
- O site do Imobzi é uma aplicação dinâmica (Angular/Ionic); os seletores
  usados foram inspecionados manualmente e devem seguir funcionando mesmo
  com pequenas atualizações visuais, mas uma mudança grande de layout pode
  exigir ajustes nos seletores dentro do script.
- A data inicial do filtro está na constante `DATA_INICIAL`, no topo do
  script (`baixar_relatorio_imoveis.py`) — atualmente `"01/01/2012"`. Para
  mudar o período, basta editar essa constante (formato `DD/MM/AAAA`).
