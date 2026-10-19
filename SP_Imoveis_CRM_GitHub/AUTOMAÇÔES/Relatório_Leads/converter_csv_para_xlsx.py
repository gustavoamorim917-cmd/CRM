"""
Ferramenta avulsa: DIAGNOSTICA e CONVERTE um CSV já baixado em .xlsx.

Serve para consertar arquivos que você já tem na mão, sem precisar baixar
tudo de novo - e, principalmente, para MOSTRAR onde está o problema de
acentuação ("DescriÃ§Ã£o" em vez de "Descrição").

Uso:
    python converter_csv_para_xlsx.py "C:\\caminho\\imoveis_27082026v1.csv"

Sem informar o arquivo, ele pega o CSV mais recente da pasta onde este
script está:
    python converter_csv_para_xlsx.py

Requisitos:
    pip install openpyxl

O que ele faz:
    1. Mostra um diagnóstico do arquivo: tamanho, primeiros bytes, se tem
       BOM, qual codificação foi detectada, se o texto está duplamente
       codificado (mojibake) e qual separador está sendo usado.
    2. Mostra o cabeçalho ANTES e DEPOIS do conserto, para você conferir
       na hora se a acentuação ficou certa.
    3. Grava o .xlsx ao lado do CSV, com o mesmo nome.

Se, mesmo depois disso, a acentuação continuar errada, copie e cole a
saída deste script - ela diz exatamente em que ponto o texto quebrou.
"""

import csv
import io
import os
import re
import sys
from datetime import datetime

CONVERTER_PARA_XLSX = True       # coloque False para só diagnosticar
CONVERTER_TIPOS_NO_XLSX = True   # números viram número e datas viram data no Excel


def log(msg):
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


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


def _csv_mais_recente(pasta):
    candidatos = [
        os.path.join(pasta, f)
        for f in os.listdir(pasta)
        if os.path.splitext(f)[1].lower() in (".csv", ".txt")
    ]
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)


def diagnosticar(caminho):
    """
    Mostra, em português claro, o estado do arquivo: como ele está
    gravado e onde a acentuação quebrou (se quebrou).
    """
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read()

    print("")
    print("=" * 70)
    print("DIAGNÓSTICO DO ARQUIVO")
    print("=" * 70)
    print(f"Arquivo ...........: {caminho}")
    print(f"Tamanho ...........: {len(bruto):,} bytes".replace(",", "."))
    print(f"Primeiros bytes ...: {bruto[:12].hex(' ')}")

    tem_bom = bruto.startswith(BOM_UTF8)
    print(f"Tem BOM de UTF-8 ..: {'sim (EF BB BF)' if tem_bom else 'não'}")

    miolo = bruto[3:] if tem_bom else bruto
    try:
        miolo.decode("utf-8")
        codificacao = "UTF-8"
    except UnicodeDecodeError:
        codificacao = "NÃO é UTF-8 (provavelmente Windows-1252/ANSI)"
    print(f"Codificação .......: {codificacao}")

    texto_cru = _decodificar(bruto)
    texto_limpo, consertado = _reparar_mojibake(texto_cru)

    primeira_crua = texto_cru.splitlines()[0] if texto_cru.splitlines() else ""
    primeira_limpa = texto_limpo.splitlines()[0] if texto_limpo.splitlines() else ""

    print(f"Separador .........: {_detectar_separador(texto_limpo[:16384])!r}")
    print("")
    print("1ª linha como está gravada no arquivo:")
    print(f"   {primeira_crua[:200]}")

    if consertado:
        print("")
        print(">>> PROBLEMA ENCONTRADO: texto duplamente codificado (mojibake).")
        print(">>> O arquivo saiu do Imobzi já com a acentuação estragada -")
        print(">>> não é o Excel nem a conversão que está errando.")
        print("")
        print("1ª linha DEPOIS do conserto:")
        print(f"   {primeira_limpa[:200]}")
    else:
        marcas = [s for s in _SINAIS_MOJIBAKE if s in texto_cru[:5000]]
        if marcas:
            print("")
            print(">>> O texto tem sinais de acentuação estranha, mas o conserto")
            print(">>> automático não se aplicou (pode ser conteúdo legítimo).")
        else:
            print("")
            print(">>> Acentuação do arquivo está correta na origem.")
    print("=" * 70)
    print("")
    return texto_limpo


def main():
    if len(sys.argv) > 1:
        caminho = os.path.abspath(sys.argv[1])
    else:
        pasta = os.path.dirname(os.path.abspath(__file__))
        caminho = _csv_mais_recente(pasta)
        if not caminho:
            print(
                "Informe o arquivo CSV a converter:\n"
                '   python converter_csv_para_xlsx.py "C:\\caminho\\arquivo.csv"'
            )
            sys.exit(1)
        log(f"Nenhum arquivo informado - usando o CSV mais recente da pasta: {caminho}")

    if not os.path.isfile(caminho):
        print(f"ERRO: não encontrei o arquivo: {caminho}")
        sys.exit(1)

    diagnosticar(caminho)

    # Normaliza o próprio CSV (UTF-8 + BOM + acentuação consertada) e
    # depois gera o .xlsx.
    garantir_bom_utf8(caminho)
    caminho_xlsx = converter_para_xlsx(caminho)

    if caminho_xlsx:
        log("Pronto! Abra o .xlsx gerado e confira a acentuação.")
    else:
        log("O .xlsx não foi gerado - veja a mensagem acima.")


if __name__ == "__main__":
    main()
