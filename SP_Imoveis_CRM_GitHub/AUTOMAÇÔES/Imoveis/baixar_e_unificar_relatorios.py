"""
Orquestra o download dos DOIS relatórios de Imóveis e depois organiza o
resultado:

    1. Roda "baixar_relatorio_imoveis.py" (período desde 01/01/2012) até
       o fim - cada script faz seu próprio login e fecha o Chrome sozinho.
    2. Roda "baixar_relatorio_imoveis - Copia.py" (período desde
       17/12/2024) até o fim.
    3. Unifica as duas planilhas em uma só: mantém 100% do conteúdo da
       primeira e cola, logo em seguida, o conteúdo da segunda A PARTIR
       DA 3ª LINHA (as duas primeiras linhas dela são descartadas).
    4. Grava o BOM do UTF-8 no início dos arquivos baixados antes de
       unificar - é a marca que avisa ao Excel, sozinho, que o arquivo
       está em UTF-8, para o CSV virar XLSX com os acentos corretos.
    5. Converte a planilha unificada em .xlsx lendo o CSV em UTF-8 - assim
       os acentos saem certos sem depender de nenhum outro programa
       adivinhar a codificação. Requer 'openpyxl'.
    6. Salva SÓ esse .xlsx final (nome com a data do dia, ex.
       "imoveis_270826_unificado.xlsx") direto na pasta fixa
       PASTA_RELATORIOS - não cria mais uma pasta nova a cada execução.
       Se já existir um arquivo do mesmo dia lá, ele é sobrescrito.
    7. Apaga os arquivos intermediários (os 2 CSVs brutos baixados, os
       xlsx "irmãos" que os scripts de download geram e o CSV unificado
       temporário) - só sobra o .xlsx final na pasta de relatórios.

Uso:
    python baixar_e_unificar_relatorios.py

Requisitos: os dois scripts (baixar_relatorio_imoveis.py e
"baixar_relatorio_imoveis - Copia.py") e o .env precisam estar na mesma
pasta que este arquivo.
"""

import csv
import io
import os
import re
import sys
import shutil
import subprocess
from datetime import datetime

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SCRIPT_1 = os.path.join(BASE_DIR, "baixar_relatorio_imoveis.py")
SCRIPT_2 = os.path.join(BASE_DIR, "baixar_relatorio_imoveis - Copia.py")

# Mesma variável usada pelos dois scripts de download - assim localizamos
# os arquivos que eles baixam.
PASTA_DOWNLOAD = os.path.abspath(os.getenv("PASTA_DESTINO", BASE_DIR))
NOME_BASE_ARQUIVO = "imoveis"

# Pasta fixa onde o .xlsx final (com a data no nome) é salvo. Não muda a
# cada execução - roda hoje, roda amanhã, é sempre aqui.
PASTA_RELATORIOS = os.path.abspath(
    os.getenv("CRM_PROPERTY_DIR") or os.path.join(BASE_DIR, "Relatórios de Imóveis")
)

# Extensões que contam como "o relatório baixado". O .xlsx que os scripts
# de download passaram a gerar ao lado do CSV NÃO entra aqui - senão ele
# seria confundido com o relatório novo na hora de detectar o download.
EXTENSOES_TEXTO = (".csv", ".txt")

# --- Conversão automática para Excel ---
# O CSV do Imobzi vem em UTF-8. Quando outro programa abre esse CSV
# achando que é ANSI/Windows-1252, os acentos viram lixo
# ("DescriÃ§Ã£o", "UsuÃ¡rio"...). Para não depender disso, o próprio
# script gera o .xlsx da planilha unificada - no .xlsx a codificação faz
# parte do formato, então acento nunca quebra.
CONVERTER_PARA_XLSX = True       # coloque False para gerar só o CSV
CONVERTER_TIPOS_NO_XLSX = True   # números viram número e datas viram data no Excel



def log(msg):
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


def _listar_arquivos_relatorio():
    """Lista os arquivos 'imoveis_*' (os relatórios baixados) na pasta de download."""
    if not os.path.isdir(PASTA_DOWNLOAD):
        return set()
    return {
        f for f in os.listdir(PASTA_DOWNLOAD)
        if f.lower().startswith(NOME_BASE_ARQUIVO.lower())
        and os.path.splitext(f)[1].lower() in EXTENSOES_TEXTO
    }


def _rodar_script(caminho_script):
    if not os.path.isfile(caminho_script):
        raise FileNotFoundError(f"Não encontrei o script: {caminho_script}")

    log(f"Executando: {os.path.basename(caminho_script)} ...")
    # stdout/stderr do script filho não são capturados - ficam saindo
    # direto no terminal, com os próprios logs com timestamp dele, então
    # dá pra acompanhar o progresso do download em tempo real.
    resultado = subprocess.run([sys.executable, caminho_script], cwd=BASE_DIR)

    if resultado.returncode != 0:
        raise RuntimeError(
            f"'{os.path.basename(caminho_script)}' terminou com erro "
            f"(código {resultado.returncode}). Veja o log acima e a pasta "
            f"'diagnostico' para mais detalhes."
        )
    log(f"{os.path.basename(caminho_script)} concluído.")


def baixar_e_detectar_novo_arquivo(caminho_script):
    """
    Roda um dos scripts de download e descobre qual arquivo novo ele
    baixou, comparando a pasta de download antes/depois - o mesmo
    princípio usado dentro dos próprios scripts para confirmar downloads.
    """
    antes = _listar_arquivos_relatorio()
    _rodar_script(caminho_script)
    depois = _listar_arquivos_relatorio()
    novos = depois - antes

    if not novos:
        raise RuntimeError(
            f"'{os.path.basename(caminho_script)}' terminou sem erro, mas "
            f"não encontrei nenhum arquivo novo '{NOME_BASE_ARQUIVO}_*' na "
            f"pasta de download ({PASTA_DOWNLOAD})."
        )

    if len(novos) > 1:
        # Não devia acontecer (cada script baixa só um arquivo), mas por
        # segurança pega o mais recente em vez de travar.
        log(f"Aviso: mais de um arquivo novo apareceu ({sorted(novos)}), usando o mais recente.")
        nome_escolhido = max(
            novos, key=lambda f: os.path.getmtime(os.path.join(PASTA_DOWNLOAD, f))
        )
    else:
        nome_escolhido = next(iter(novos))

    return os.path.join(PASTA_DOWNLOAD, nome_escolhido)


BOM_UTF8 = b"\xef\xbb\xbf"

# Sequências típicas de texto "duplamente codificado" (mojibake): o
# arquivo é UTF-8 válido, mas o que está gravado nele já é o lixo
# "DescriÃ§Ã£o" em vez de "Descrição" - ou seja, o estrago aconteceu ANTES
# do arquivo chegar aqui, lá na exportação.
_SINAIS_MOJIBAKE = ("Ã", "Â", "â")


def _decodificar(conteudo):
    """
    Transforma os bytes do arquivo em texto, descobrindo a codificação:
    UTF-8 (com ou sem BOM), UTF-16 ou Windows-1252 (cp1252).
    """
    if conteudo.startswith(BOM_UTF8):
        return conteudo[len(BOM_UTF8):].decode("utf-8", errors="replace")
    if conteudo.startswith(b"\xff\xfe") or conteudo.startswith(b"\xfe\xff"):
        return conteudo.decode("utf-16", errors="replace")
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252", errors="replace")


def _reparar_mojibake(texto):
    """
    Conserta texto duplamente codificado ("DescriÃ§Ã£o" -> "Descrição").

    Como isso acontece: em algum ponto da exportação, bytes UTF-8 foram
    lidos como se fossem Windows-1252 e gravados de novo em UTF-8. O
    conserto é o caminho inverso: re-codificar o texto em Windows-1252 e
    decodificar em UTF-8.

    Só aplica se (1) o texto tiver os sinais típicos do problema e (2) o
    caminho inverso funcionar e realmente reduzir esses sinais - senão
    devolve o texto original intacto. Assim, um texto que legitimamente
    use "Ã" nunca é estragado.

    Devolve (texto, consertou?).
    """
    consertou = False

    # Em casos raros o texto passa pelo mesmo estrago mais de uma vez
    # ("DescriÃƒÂ§ÃƒÂ£o") - por isso repete enquanto houver melhora, no
    # máximo 3 rodadas.
    for _ in range(3):
        if not texto or not any(sinal in texto for sinal in _SINAIS_MOJIBAKE):
            break

        antes = sum(texto.count(sinal) for sinal in _SINAIS_MOJIBAKE)
        melhorou = False

        for codificacao in ("cp1252", "latin-1"):
            try:
                corrigido = texto.encode(codificacao).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            depois = sum(corrigido.count(sinal) for sinal in _SINAIS_MOJIBAKE)
            if depois < antes:
                texto = corrigido
                consertou = True
                melhorou = True
                break

        if not melhorou:
            break

    return texto, consertou


def _ler_texto(caminho):
    """
    Lê o arquivo e devolve o texto já limpo: codificação detectada e,
    se for o caso, mojibake consertado.
    """
    with open(caminho, "rb") as arquivo:
        conteudo = arquivo.read()

    texto, consertado = _reparar_mojibake(_decodificar(conteudo))
    if consertado:
        log(
            "Texto estava duplamente codificado ('DescriÃ§Ã£o') - "
            "consertado para a acentuação normal ('Descrição')."
        )
    return texto


def garantir_bom_utf8(caminho):
    """
    Normaliza o arquivo baixado: conteúdo em UTF-8, mojibake consertado e
    BOM (Byte Order Mark) no início.

    O BOM é uma marca invisível de 3 bytes (EF BB BF) que avisa ao Excel
    que o arquivo está em UTF-8. Ele resolve o caso em que o arquivo está
    certo e o leitor erra a codificação - mas NÃO resolve o caso em que o
    texto já foi gravado estragado; por isso o conserto de mojibake acima.

    Só mexe em arquivos de texto (.csv/.txt) - em binários (.xlsx) o BOM
    corromperia o arquivo.
    """
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao not in (".csv", ".txt"):
        log(
            f"'{os.path.basename(caminho)}' não é .csv/.txt "
            f"(formato binário) - BOM não se aplica."
        )
        return caminho

    with open(caminho, "rb") as arquivo:
        original = arquivo.read()

    texto, consertado = _reparar_mojibake(_decodificar(original))
    if consertado:
        log(
            "ATENÇÃO: o arquivo veio do Imobzi com o texto duplamente "
            "codificado ('DescriÃ§Ã£o'). Consertei a acentuação."
        )

    novo = BOM_UTF8 + texto.encode("utf-8")
    if novo == original:
        log("Arquivo já estava em UTF-8 com BOM e com a acentuação correta.")
        return caminho

    with open(caminho, "wb") as arquivo:
        arquivo.write(novo)

    log("Arquivo normalizado: UTF-8 com BOM (acentos corretos para o Excel).")
    return caminho


def _detectar_separador(amostra):
    """
    Descobre qual separador o Imobzi usou no CSV (";", ",", tabulação ou
    "|"). Importa acertar: se lermos um arquivo separado por ";" como se
    fosse ",", tudo cai numa coluna só no Excel.
    """
    separadores = (";", ",", "\t", "|")
    try:
        return csv.Sniffer().sniff(amostra, delimiters="".join(separadores)).delimiter
    except csv.Error:
        contagens = {sep: amostra.count(sep) for sep in separadores}
        melhor = max(contagens, key=contagens.get)
        return melhor if contagens[melhor] else ";"


_RE_DATA = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[\s,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)
_RE_NUMERO_BR = re.compile(r"^-?\d{1,3}(?:\.\d{3})+(?:,\d+)?$|^-?\d+(?:,\d+)?$")


def _converter_valor(texto):
    """
    Converte o texto lido do CSV para o tipo certo no Excel:

      - "27/08/2026" / "27/08/2026 14:30"  -> data/hora de verdade
      - "1.234,56" / "1234" / "R$ 980,00"  -> número de verdade
      - qualquer outra coisa               -> texto, exatamente como veio

    Cuidados para NÃO estragar dado: valores com zero à esquerda (códigos,
    CPF, telefone) e sequências muito longas de dígitos continuam TEXTO -
    se virassem número, o Excel comeria os zeros e arredondaria.
    """
    valor = (texto or "").strip()
    if not valor:
        return None
    if not CONVERTER_TIPOS_NO_XLSX:
        return texto

    achou_data = _RE_DATA.match(valor)
    if achou_data:
        dia, mes, ano, hora, minuto, segundo = achou_data.groups()
        try:
            return datetime(
                int(ano), int(mes), int(dia),
                int(hora or 0), int(minuto or 0), int(segundo or 0),
            )
        except ValueError:
            return texto

    bruto = valor.replace("R$", "").replace("\xa0", " ").strip()
    if _RE_NUMERO_BR.match(bruto):
        parte_inteira = bruto.lstrip("-").split(",")[0].replace(".", "")
        inteiro_puro = "," not in bruto and "." not in bruto

        # Vira número só quando é mesmo uma quantidade ou um valor.
        # Continuam TEXTO:
        #   - zero à esquerda ("0012"): o Excel comeria o zero;
        #   - inteiro longo sem separador (telefone "11999999999", CPF,
        #     CNPJ, id): apareceria como 1,19713E+10 na tela;
        #   - número gigante: perderia precisão.
        if len(parte_inteira) > 1 and parte_inteira.startswith("0"):
            return texto
        if inteiro_puro and len(parte_inteira) > 9:
            return texto
        if len(parte_inteira) > 15:
            return texto
        try:
            numero = float(bruto.replace(".", "").replace(",", "."))
        except ValueError:
            return texto
        if "," not in bruto and numero.is_integer():
            return int(numero)
        return numero

    return texto


def converter_para_xlsx(caminho_csv):
    """
    Gera um .xlsx de verdade a partir do CSV baixado, com os acentos
    corretos - sem depender de nenhum programa externo abrir o CSV.

    O CSV é lido aqui dentro (codificação detectada + mojibake
    consertado) e gravado como .xlsx, formato em que a codificação faz
    parte do arquivo. Assim "Descrição" não tem como virar "DescriÃ§Ã£o".

    O .xlsx é salvo ao lado do CSV, com o mesmo nome.

    Requer: pip install openpyxl
    """
    if not CONVERTER_PARA_XLSX:
        return None

    extensao = os.path.splitext(caminho_csv)[1].lower()
    if extensao not in (".csv", ".txt"):
        log(
            f"'{os.path.basename(caminho_csv)}' não é .csv/.txt - "
            f"conversão para .xlsx não se aplica."
        )
        return None

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        log(
            "AVISO: a biblioteca 'openpyxl' não está instalada, então NÃO "
            "gerei o .xlsx. Rode 'pip install openpyxl' e execute de novo "
            "(o CSV já foi baixado normalmente)."
        )
        return None

    caminho_xlsx = os.path.splitext(caminho_csv)[0] + ".xlsx"
    log(f"Convertendo para Excel: {os.path.basename(caminho_xlsx)} ...")

    texto = _ler_texto(caminho_csv)
    separador = _detectar_separador(texto[:16384])

    planilha = Workbook()
    aba = planilha.active
    aba.title = "Relatório"

    larguras = {}
    total_linhas = 0

    for linha in csv.reader(io.StringIO(texto, newline=""), delimiter=separador):
        total_linhas += 1
        aba.append([_converter_valor(celula) for celula in linha])

        # Formatos: data no padrão brasileiro (senão o Excel mostra no
        # americano) e dinheiro como moeda quando o CSV trazia "R$".
        for indice, celula in enumerate(aba[aba.max_row], start=1):
            bruto = linha[indice - 1] if indice - 1 < len(linha) else ""
            if isinstance(celula.value, datetime):
                celula.number_format = (
                    "DD/MM/YYYY HH:MM"
                    if (celula.value.hour or celula.value.minute)
                    else "DD/MM/YYYY"
                )
            elif isinstance(celula.value, (int, float)) and "R$" in (bruto or ""):
                celula.number_format = "R$ #,##0.00"

        # Largura das colunas estimada pelas primeiras linhas (não precisa
        # varrer o arquivo inteiro só para isso).
        if total_linhas <= 300:
            for indice, celula in enumerate(linha, start=1):
                larguras[indice] = min(60, max(larguras.get(indice, 10), len(celula) + 2))

    if total_linhas == 0:
        log("AVISO: o CSV estava vazio - .xlsx não foi gerado.")
        return None

    # Cabeçalho em negrito, congelado, com filtro - só conveniência.
    for celula in aba[1]:
        celula.font = Font(bold=True)
    aba.freeze_panes = "A2"
    if aba.max_row > 1:
        aba.auto_filter.ref = aba.dimensions
    for indice, largura in larguras.items():
        aba.column_dimensions[get_column_letter(indice)].width = largura

    planilha.save(caminho_xlsx)
    log(f"Excel gerado com sucesso ({total_linhas} linhas): {caminho_xlsx}")
    return caminho_xlsx


def unir_planilhas(caminho1, caminho2, caminho_unificado):
    """
    Une duas planilhas em uma só: mantém TODO o conteúdo da primeira e
    cola, logo em seguida, o conteúdo da segunda a partir da 3ª linha
    (pula as duas primeiras linhas dela).

    Cola linha a linha, sem interpretar o conteúdo como CSV de verdade -
    assim funciona independente do separador que o Imobzi usar, sem risco
    de bagunçar aspas/vírgulas ao tentar reformatar o conteúdo.

    Os dois arquivos são lidos por `_ler_texto`, que já resolve a
    codificação e conserta mojibake - então as duas metades entram no
    arquivo final na mesma codificação e com os acentos certos. O
    resultado é gravado em UTF-8 com BOM.
    """
    conteudo1 = _ler_texto(caminho1)
    conteudo2 = _ler_texto(caminho2)

    resto2 = "".join(conteudo2.splitlines(keepends=True)[2:])

    # Garante que existe uma quebra de linha entre o fim do conteúdo da
    # primeira planilha e o início do conteúdo colado da segunda.
    if conteudo1 and not conteudo1.endswith(("\n", "\r")):
        conteudo1 += "\r\n"

    with open(caminho_unificado, "wb") as saida:
        saida.write(BOM_UTF8)
        saida.write((conteudo1 + resto2).encode("utf-8"))


def main():
    log("=== Etapa 1/2: baixando o primeiro relatório (desde 01/01/2012) ===")
    caminho_1 = baixar_e_detectar_novo_arquivo(SCRIPT_1)
    log(f"Primeiro relatório baixado: {caminho_1}")

    log("=== Etapa 2/2: baixando o segundo relatório (desde 17/12/2024) ===")
    caminho_2 = baixar_e_detectar_novo_arquivo(SCRIPT_2)
    log(f"Segundo relatório baixado: {caminho_2}")

    carimbo_dia = datetime.now().strftime("%d%m%y")

    # Arquivos intermediários que serão apagados no final - só o .xlsx
    # unificado, lá na frente, sobrevive (na pasta de relatórios).
    arquivos_temporarios = [
        caminho_1,
        caminho_2,
        os.path.splitext(caminho_1)[0] + ".xlsx",  # xlsx "irmão" do 1º relatório
        os.path.splitext(caminho_2)[0] + ".xlsx",  # xlsx "irmão" do 2º relatório
    ]

    # --- BOM do UTF-8 nos dois arquivos baixados (normaliza no lugar) ---
    garantir_bom_utf8(caminho_1)
    garantir_bom_utf8(caminho_2)

    # --- Unifica as duas planilhas (arquivo temporário, apagado no fim) ---
    extensao_1 = os.path.splitext(caminho_1)[1].lower()
    extensao_2 = os.path.splitext(caminho_2)[1].lower()
    if extensao_1 not in (".csv", ".txt") or extensao_2 not in (".csv", ".txt"):
        # Não deveria acontecer: a detecção de download só reconhece
        # .csv/.txt como "relatório novo" (ver EXTENSOES_TEXTO) - mas
        # melhor travar aqui do que gerar um xlsx incompleto.
        raise RuntimeError(
            "Pelo menos um dos arquivos baixados não é .csv/.txt - não dá "
            "para unificar nem gerar o .xlsx final."
        )

    nome_unificado_csv = f"{NOME_BASE_ARQUIVO}_{carimbo_dia}_unificado.csv"
    caminho_unificado_csv = os.path.join(PASTA_DOWNLOAD, nome_unificado_csv)
    unir_planilhas(caminho_1, caminho_2, caminho_unificado_csv)
    log(f"Planilha unificada (temporária): {caminho_unificado_csv}")
    arquivos_temporarios.append(caminho_unificado_csv)

    # --- Gera o .xlsx unificado e move pra pasta fixa de relatórios ---
    caminho_xlsx_temp = converter_para_xlsx(caminho_unificado_csv)
    if not caminho_xlsx_temp:
        raise RuntimeError(
            "Não foi possível gerar o .xlsx unificado (veja os avisos acima - "
            "provavelmente falta instalar 'openpyxl')."
        )

    os.makedirs(PASTA_RELATORIOS, exist_ok=True)
    nome_final = f"{NOME_BASE_ARQUIVO}_{carimbo_dia}_unificado.xlsx"
    destino_final = os.path.join(PASTA_RELATORIOS, nome_final)
    if os.path.exists(destino_final):
        os.remove(destino_final)  # já rodou hoje - substitui pelo mais novo
    shutil.move(caminho_xlsx_temp, destino_final)
    log(f"Relatório final salvo em: {destino_final}")

    # --- Limpeza: apaga os arquivos intermediários ---
    for arquivo in arquivos_temporarios:
        if arquivo and os.path.isfile(arquivo):
            os.remove(arquivo)
            log(f"Removido (temporário): {arquivo}")

    log("Concluído com sucesso!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERRO: {e}")
        sys.exit(1)
