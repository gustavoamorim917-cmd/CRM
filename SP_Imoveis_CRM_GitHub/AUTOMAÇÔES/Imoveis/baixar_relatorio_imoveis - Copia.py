"""
Automação: baixa o relatório "Imóveis - Cadastros" do Imobzi (todos os
usuários, desde a data configurada) e salva o arquivo renomeado no padrão:
imoveis_DDMMAAAAvN.<extensão original>

Requisitos:
    pip install -r requirements.txt

Configuração:
    1. Copie o arquivo ".env.example" para ".env" (mesma pasta deste script).
    2. Preencha IMOBZI_EMAIL e IMOBZI_SENHA no .env com suas credenciais do Imobzi.
    3. (Opcional) Ajuste PASTA_DESTINO no .env se quiser salvar em outro lugar.

Uso:
    python baixar_relatorio_imoveis.py

O script:
    1. Abre o Chrome e faz login em https://my.imobzi.com/#/login
    2. Acessa a URL do relatório configurada em REPORT_URL
    3. Aplica o filtro de período (desde DATA_INICIAL até hoje) e usuário "Todos"
    4. Clica em "Exportar" e aguarda o Imobzi processar o relatório
       (isso é assíncrono: o Imobzi avisa por notificação quando fica pronto)
    5. Assim que aparece uma notificação de relatório pronto, recarrega a
       página (reload) ANTES de clicar em "Baixar" - garante que o link
       clicado é do relatório que acabamos de pedir, e não de uma
       notificação antiga que já estava na tela - e confirma pelo disco
       que o download realmente começou antes de seguir
    6. Aguarda o arquivo terminar de baixar direto na pasta de destino
    7. Renomeia o arquivo baixado para imoveis_DDMMAAAAvN.<extensão>
    8. Acrescenta o BOM do UTF-8 no início do arquivo baixado, para o
       Excel reconhecer a codificação sozinho e converter o CSV em XLSX
       com os acentos corretos
    9. Converte o CSV em .xlsx (mesmo nome, ao lado do CSV) lendo o
       arquivo em UTF-8 - assim os acentos saem certos sem depender de
       nenhum outro programa adivinhar a codificação. Requer 'openpyxl'.
"""

import csv
import io
import os
import re
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
    TEM_WEBDRIVER_MANAGER = True
except ImportError:
    TEM_WEBDRIVER_MANAGER = False


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

LOGIN_URL = "https://my.imobzi.com/#/login"
# Link do relatorio da SUA conta Imobzi (copie da barra de enderecos).
REPORT_URL = os.getenv("IMOBZI_REPORT_URL_IMOVEIS", "").strip()

EMAIL = os.getenv("IMOBZI_EMAIL")
SENHA = os.getenv("IMOBZI_SENHA")
PASTA_DESTINO = os.getenv("PASTA_DESTINO", BASE_DIR)
DATA_INICIAL = "17/12/2024"  # período: desde essa data até hoje
NOME_BASE_ARQUIVO = "imoveis"

# --- Conversão automática para Excel ---
# O CSV do Imobzi vem em UTF-8. Quando outro programa abre esse CSV
# achando que é ANSI/Windows-1252, os acentos viram lixo
# ("DescriÃ§Ã£o", "UsuÃ¡rio"...). Para não depender disso, o próprio
# script gera um .xlsx pronto ao lado do CSV - no .xlsx a codificação
# faz parte do formato, então acento nunca quebra.
CONVERTER_PARA_XLSX = True       # coloque False para gerar só o CSV
CONVERTER_TIPOS_NO_XLSX = True   # números viram número e datas viram data no Excel


TIMEOUT_PADRAO = 30            # segundos para esperas normais de UI
TIMEOUT_PROCESSAMENTO = 300    # segundos para o Imobzi gerar o relatório (pode ser grande)
TIMEOUT_DOWNLOAD = 180         # segundos para o arquivo terminar de baixar
ESPERA_ANTES_DE_RECARREGAR = 60  # segundos de espera fixa depois da notificação aparecer, antes do reload


def log(msg):
    agora = datetime.now().strftime("%H:%M:%S")
    # flush=True para o log aparecer no terminal na hora, sem ficar
    # "preso" no buffer do Python enquanto o script espera algo na tela.
    print(f"[{agora}] {msg}", flush=True)


def montar_driver(pasta_download):
    os.makedirs(pasta_download, exist_ok=True)

    chrome_options = Options()
    # Descomente a linha abaixo se quiser rodar sem abrir a janela do Chrome:
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-notifications")

    prefs = {
        "download.default_directory": pasta_download,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if TEM_WEBDRIVER_MANAGER:
        service = Service(ChromeDriverManager().install())
    else:
        # Se webdriver-manager não estiver instalado, o Selenium tentará
        # usar um "chromedriver" já disponível no PATH do sistema.
        service = Service()

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def fazer_login(driver, wait):
    log("Abrindo página de login...")
    driver.get(LOGIN_URL)

    campo_email = wait.until(EC.presence_of_element_located((By.ID, "email")))
    campo_senha = driver.find_element(By.ID, "password")

    campo_email.clear()
    campo_email.send_keys(EMAIL)
    campo_senha.clear()
    campo_senha.send_keys(SENHA)

    log("Enviando login...")

    # O botão "ENTRAR" só fica habilitado depois que o Angular processa os
    # eventos de input dos campos - por isso esperamos ele ficar clicável
    # em vez de confiar só no Enter (o Enter pode não disparar o submit
    # se o formulário ainda não tiver sido validado no momento do envio).
    botao_entrar = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[@type='submit' and normalize-space()='ENTRAR']")
    ))
    clicar_com_retentativa(driver, botao_entrar)

    try:
        # Aguarda sair da tela de login (URL muda de #/login para outra rota)
        wait.until(lambda d: "/login" not in d.current_url)
    except TimeoutException:
        # Fallback: se o clique no botão não disparou o submit por algum
        # motivo, tenta novamente e depois tenta Enter no campo de senha.
        log("Login não confirmou de primeira, tentando novamente...")
        clicar_com_retentativa(driver, botao_entrar)
        try:
            wait.until(lambda d: "/login" not in d.current_url)
        except TimeoutException:
            campo_senha = driver.find_element(By.ID, "password")
            campo_senha.send_keys(Keys.RETURN)
            wait.until(lambda d: "/login" not in d.current_url)

    log("Login efetuado.")


def abrir_relatorio(driver, wait):
    log("Abrindo relatório de Imóveis...")
    driver.get(REPORT_URL)

    # Espera a tabela do relatório carregar (texto "Total de imóveis")
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//*[contains(text(),'Total de im')]")
    ))
    log("Relatório carregado.")


def clicar_com_retentativa(driver, elemento, tentativas=3):
    for i in range(tentativas):
        try:
            elemento.click()
            return
        except (ElementClickInterceptedException, StaleElementReferenceException):
            time.sleep(1)
    # Última tentativa via JS, caso algo esteja sobrepondo o elemento
    driver.execute_script("arguments[0].click();", elemento)


def _definir_data_inicial(driver, wait):
    """
    Define a data inicial do filtro.

    Descoberta confirmada inspecionando o app ao vivo: o campo "Data
    inicial" já vem, por padrão, com o texto do período atual (ex.: "sáb,
    01/08/2026") totalmente selecionado assim que ele recebe o
    clique/foco - é um comportamento nativo do app, não precisa de Ctrl+A
    nem de Backspace para limpar. Basta clicar no campo e digitar a data
    nova por cima: o texto selecionado é substituído direto. Isso é bem
    mais confiável do que o Backspace caractere-a-caractere usado antes
    (que dependia de acertar o tamanho exato do valor existente e falhava
    às vezes, deixando o campo com o valor antigo).

    Depois de digitar, o mini-calendário abaixo do campo já pula
    automaticamente para o mês/ano digitado - só falta clicar no dia.

    Clicar em outro lugar da tela não estava fechando o calendário de
    forma confiável - então, em vez disso, o campo recebe um Tab pra
    tirar o foco, o que fecha o calendário (ele só fica aberto enquanto o
    campo está focado).

    Existem DOIS calendários no DOM ao mesmo tempo (um para "Data inicial"
    e outro para "Data final"), então a busca do dia é escopada para o
    calendário que aparece logo depois do campo "Data inicial" no DOM -
    senão o clique pode cair, por engano, no calendário da data final.
    """
    dia, mes, ano = DATA_INICIAL.split("/")

    dia_xpath = (
        "(//input[@placeholder='Data inicial']"
        "/following::div[contains(@class,'calendar-container')])[1]"
        "//div[contains(@class,'cal-in-month')]"
        f"//span[contains(@class,'cal-day-number') and normalize-space()='{int(dia)}']"
    )

    log("  -> procurando o campo 'Data inicial'...")
    campo_data_inicial = wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "input[placeholder='Data inicial']")
    ))

    for tentativa in range(1, 4):
        log(f"  -> clicando no campo e digitando a data (tentativa {tentativa})...")
        clicar_com_retentativa(driver, campo_data_inicial)
        # O clique seleciona o texto existente inteiro - digitar substitui.
        campo_data_inicial.send_keys(DATA_INICIAL)

        valor_atual = campo_data_inicial.get_attribute("value") or ""

        # Trocado: agora aperta Tab em vez de clicar em algum título, pra
        # tirar o foco do campo e fechar o calendário.
        log("  -> apertando Tab para sair do campo e fechar o calendário...")
        campo_data_inicial.send_keys(Keys.TAB)
        time.sleep(0.5)

        if DATA_INICIAL in valor_atual:
            break
        log(f"  -> campo ficou com '{valor_atual}' em vez de '{DATA_INICIAL}', tentando de novo...")
    else:
        raise RuntimeError(
            f"Não consegui digitar a data no campo 'Data inicial' "
            f"(ficou com '{valor_atual}' após 3 tentativas)."
        )

    # O Tab (feito no loop acima) já deve ter fechado o calendário. Ainda
    # assim, tenta clicar no dia certo caso o calendário tenha ficado
    # aberto - com espera curta, porque se ele já fechou não tem sentido
    # esperar o TIMEOUT_PADRAO inteiro.
    log("  -> procurando o dia no calendário (caso ainda esteja aberto)...")
    try:
        dia_1 = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, dia_xpath)))
        log("  -> dia encontrado, clicando...")
        clicar_com_retentativa(driver, dia_1)
        time.sleep(0.5)
    except TimeoutException:
        log("  -> calendário já estava fechado, seguindo.")

    log("Data inicial definida, seguindo para o filtro de usuário...")


def _selecionar_usuario_todos(driver, wait):
    """
    Fecha o calendário (apertando Tab para tirar o foco do campo de data)
    e depois seleciona "Todos" no filtro de Usuário, clicando primeiro no
    valor atual mostrado (ex.: "Fulano de Tal") para abrir a lista de
    opções.

    Cada etapa tem log próprio para dar pra acompanhar visualmente no
    terminal se o clique realmente surtiu efeito (abriu a lista, mudou o
    texto etc.), já que esses menus do Imobzi às vezes "engolem" o
    primeiro clique.
    """
    # --- 1) Fecha o calendário apertando Tab no elemento focado ---
    # Trocado: agora aperta Tab em vez de clicar em algum título. Usa o
    # elemento que estiver focado no momento, já que essa função não tem
    # referência direta ao campo de data.
    log("  -> apertando Tab para fechar o calendário...")
    driver.switch_to.active_element.send_keys(Keys.TAB)
    time.sleep(0.5)
    log("  -> calendário fechado.")

    # --- 2) Clica no valor atual do usuário (ex.: "Fulano de Tal") para abrir a lista ---
    valor_atual_usuario_xpath = "//h2[normalize-space()='Usuário']/following::div[contains(@class,'combobox')][1]"
    todos_xpath = "//*[normalize-space(text())='Todos']"

    combobox_usuario = wait.until(EC.element_to_be_clickable((By.XPATH, valor_atual_usuario_xpath)))
    log(f"  -> usuário atual no filtro: '{combobox_usuario.text.strip()}'. Clicando para abrir a lista...")

    opcao_todos = None
    for tentativa in range(1, 4):
        clicar_com_retentativa(driver, combobox_usuario)
        try:
            opcao_todos = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, todos_xpath))
            )
            log(f"  -> lista de usuários abriu na tentativa {tentativa}.")
            break
        except TimeoutException:
            log(f"  -> tentativa {tentativa}: lista de usuários não abriu, clicando de novo em '{combobox_usuario.text.strip()}'...")
            continue

    if opcao_todos is None:
        raise RuntimeError("Não consegui abrir a lista de usuários para selecionar 'Todos'.")

    # --- 3) Clica em "Todos" e confere se o combobox realmente mudou ---
    for tentativa in range(1, 4):
        log(f"  -> clicando em 'Todos' (tentativa {tentativa})...")
        clicar_com_retentativa(driver, opcao_todos)
        time.sleep(0.6)
        texto_combobox = combobox_usuario.text.strip()
        if texto_combobox == "Todos":
            log("  -> usuário confirmado como 'Todos'.")
            break
        log(f"  -> combobox de usuário ainda mostra '{texto_combobox}', tentando de novo...")
    else:
        raise RuntimeError("Não consegui confirmar a seleção de 'Todos' no filtro de usuário.")


def aplicar_filtro_periodo_total(driver, wait):
    log("Abrindo painel de filtro...")
    botao_filtro = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//page-reports-view//button[.//i[normalize-space()='filter_list']]")
    ))
    clicar_com_retentativa(driver, botao_filtro)

    # --- Data inicial ---
    log(f"Definindo data inicial ({DATA_INICIAL})...")
    _definir_data_inicial(driver, wait)

    # A data final já vem preenchida com a data de hoje por padrão - não precisa mexer.

    # --- Usuário: Todos ---
    log("Definindo usuário como 'Todos'...")
    _selecionar_usuario_todos(driver, wait)

    # --- Aplicar filtro (botão de confirmação "done" ✅, id="button-save") ---
    log("Confirmando filtro (ícone ✅)...")

    def _painel_esta_aberto(d):
        try:
            classes = d.find_element(By.CSS_SELECTOR, ".filter-wrapper").get_attribute("class") or ""
            return "show" in classes.split()
        except Exception:
            # Se o painel nem existe mais no DOM, também consideramos "fechado".
            return False

    aplicado = False
    for tentativa in range(1, 4):
        # O botão tem id fixo (button-save) - mais confiável que procurar
        # pelo ícone "done" dentro dele.
        botao_aplicar = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "#button-save")
        ))
        clicar_com_retentativa(driver, botao_aplicar)

        try:
            # O painel "Filtrar" não some do DOM ao fechar, ele só perde a
            # classe "show" (desliza para fora da tela) - por isso checamos
            # a classe em vez de esperar o elemento "desaparecer".
            WebDriverWait(driver, 6).until(lambda d: not _painel_esta_aberto(d))
            aplicado = True
            break
        except TimeoutException:
            log(f"Tentativa {tentativa}: painel de filtro não fechou, clicando de novo em ✅...")
            continue

    if not aplicado:
        raise RuntimeError("Não foi possível confirmar o filtro (ícone ✅ / done).")

    # Aguarda o relatório recarregar com o novo filtro: espera o texto do
    # bloco "Total de imóveis" parar de mudar (a tabela pode levar alguns
    # segundos para atualizar a contagem depois que o filtro é aplicado).
    _esperar_total_imoveis_estabilizar(driver)
    log(f"Filtro aplicado (desde {DATA_INICIAL}, todos os usuários). Total de imóveis: {_texto_total_imoveis(driver)}")


def _texto_total_imoveis(driver):
    try:
        elemento = driver.find_element(By.XPATH, "//*[contains(text(),'Total de im')]/..")
        return elemento.text.strip()
    except Exception:
        return None


def _esperar_total_imoveis_estabilizar(driver, timeout=60, intervalo=1.5, estavel_por=3):
    """
    Espera o número de "Total de imóveis" parar de mudar por alguns ciclos
    seguidos - sinal de que a tabela terminou de recarregar com o filtro novo.
    """
    inicio = time.time()
    leituras_iguais = 0
    ultimo_valor = None

    while time.time() - inicio < timeout:
        valor_atual = _texto_total_imoveis(driver)
        if valor_atual and valor_atual == ultimo_valor:
            leituras_iguais += 1
            if leituras_iguais >= estavel_por:
                return
        else:
            leituras_iguais = 0
        ultimo_valor = valor_atual
        time.sleep(intervalo)

    log("Aviso: não deu para confirmar que a contagem de imóveis estabilizou, seguindo mesmo assim.")


def exportar_relatorio(driver, wait):
    """
    Confirmado ao vivo: o menu "⋮" (more_vert) também sofre do mesmo
    comportamento visto em outros menus do app - o primeiro clique às
    vezes não abre o menu, precisa de um segundo. Por isso a checagem
    rápida (o item "Exportar" ficou clicável?) com curta retentativa,
    tanto para abrir o menu quanto para de fato clicar em "Exportar".
    """
    log("Solicitando exportação do relatório...")
    botao_menu_xpath = "//page-reports-view//button[.//i[normalize-space()='more_vert']]"
    exportar_xpath = "//*[normalize-space(text())='Exportar']"

    opcao_exportar = None
    for tentativa in range(1, 4):
        botao_menu = wait.until(EC.element_to_be_clickable((By.XPATH, botao_menu_xpath)))
        clicar_com_retentativa(driver, botao_menu)
        try:
            opcao_exportar = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, exportar_xpath))
            )
            break
        except TimeoutException:
            log(f"Tentativa {tentativa}: menu de opções não abriu, clicando de novo...")
            continue

    if opcao_exportar is None:
        raise RuntimeError("Não consegui abrir o menu de opções para exportar o relatório.")

    # Confere se o toast de confirmação apareceu (texto padrão do Imobzi ao
    # iniciar a exportação) - se não apareceu, o clique em "Exportar" pode
    # não ter "pegado" e clicamos de novo.
    for tentativa in range(1, 4):
        clicar_com_retentativa(driver, opcao_exportar)
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'relatório é processado')]")
            ))
            log("Exportação solicitada. O Imobzi está processando o relatório em segundo plano...")
            return
        except TimeoutException:
            log(f"Tentativa {tentativa}: clique em 'Exportar' não confirmou, tentando de novo...")
            continue

    raise RuntimeError("Não consegui confirmar a solicitação de exportação do relatório.")


def _download_comecou(pasta_download, arquivos_antes, timeout=15):
    """
    Verifica se um arquivo NOVO começou a aparecer na pasta de download
    (incluindo arquivos parciais ".crdownload"/".tmp") dentro de um tempo
    curto. É a forma mais confiável de saber se um clique em "Baixar"
    realmente disparou um download de verdade - checar se abriu uma
    aba/janela nova do navegador não é confiável, porque a aba que o
    Imobzi abre pra baixar se fecha sozinha rápido demais pro Selenium
    conseguir flagrar de forma consistente.
    """
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            arquivos_agora = set(os.listdir(pasta_download))
        except FileNotFoundError:
            arquivos_agora = set()
        if arquivos_agora - arquivos_antes:
            return True
        time.sleep(0.5)
    return False


def _fechar_painel_notificacoes(driver):
    """
    Fecha o painel de notificações clicando no "X" do cabeçalho. Esse
    painel é, na verdade, um MODAL do Ionic com um fundo (backdrop) que
    cobre a página inteira - se ficar aberto, pode atrapalhar qualquer
    interação seguinte com a página. Melhor esforço: se não achar/fechar,
    não trava o script, só loga um aviso.
    """
    try:
        botao_fechar = driver.find_element(
            By.XPATH,
            "//notification//button[.//i[normalize-space()='close']]"
            " | //button[.//i[normalize-space()='close']]",
        )
        clicar_com_retentativa(driver, botao_fechar)
        time.sleep(0.5)
    except Exception:
        pass


def esperar_relatorio_pronto_e_baixar(driver, wait, pasta_download, arquivos_antes):
    """
    O Imobzi processa o relatório de forma assíncrona e avisa através do
    sino de notificações, com um link "Baixar". Este passo fica
    verificando as notificações até o relatório ficar pronto e então
    clica em "Baixar" - de um jeito à prova de falhas:

    1. Fica checando periodicamente (a cada ~5s) se já existe algum link
       "Baixar" no sino de notificações - é só um sinal de "provavelmente
       pronto", ainda não confiamos cegamente nele.
    2. Assim que aparecer, esperamos ESPERA_ANTES_DE_RECARREGAR (60s) e só
       então damos um RELOAD (F5) na página ANTES de clicar em "Baixar".
       A espera dá uma folga pro Imobzi terminar de propagar o arquivo
       novo no backend, e o reload garante que a lista de notificações
       seja recarregada do zero direto do backend - trazendo o estado
       mais atual possível - em vez de continuar olhando pro DOM antigo,
       que pode estar desatualizado em relação ao que o Imobzi já
       processou. Assim, o link "Baixar" que aparece no TOPO da lista
       (mais recente) é garantidamente o do relatório que acabamos de
       pedir por último.
    3. Clica no link "Baixar" mais recente e CONFIRMA, olhando a pasta de
       destino no disco, que um arquivo novo realmente começou a ser
       baixado (`_download_comecou`) - se não começar em alguns segundos,
       assumimos que era uma notificação obsoleta/expirada e tentamos de
       novo (reload + reabrir painel + clicar de novo), sem travar o
       script.
    4. Fecha o painel de notificações (modal com fundo que cobre a tela)
       antes de retornar, pra não deixar nada bloqueando os passos
       seguintes.

    Tudo isso dentro do timeout total TIMEOUT_PROCESSAMENTO - se não
    conseguir confirmar um download de verdade nesse tempo, levanta um
    erro claro em vez de ficar preso pra sempre.
    """
    log("Aguardando o Imobzi terminar de processar o relatório (isso pode levar 1 a 3 minutos)...")

    inicio = time.time()

    while time.time() - inicio < TIMEOUT_PROCESSAMENTO:
        try:
            # --- 1) Só verifica (sem clicar em "Baixar" ainda) se já tem notificação pronta ---
            botao_notificacoes = driver.find_element(
                By.XPATH, "//button[@aria-label='Notificações' or .//i[normalize-space()='notifications']]"
            )
            clicar_com_retentativa(driver, botao_notificacoes)
            time.sleep(1)

            tem_notificacao_pronta = bool(
                driver.find_elements(By.XPATH, "//b[normalize-space()='Baixar']")
            )
            _fechar_painel_notificacoes(driver)

            if not tem_notificacao_pronta:
                time.sleep(5)
                continue

            # --- 2) RELOAD antes de baixar: garante que o link que vamos clicar ---
            # reflete o estado mais atual do backend, não um DOM que já
            # estava aberto (e potencialmente desatualizado) desde antes
            # de pedirmos a exportação.
            log(
                f"Notificação de relatório pronto encontrada. Aguardando "
                f"{ESPERA_ANTES_DE_RECARREGAR}s antes de recarregar a página "
                f"(dá tempo do Imobzi terminar de propagar o arquivo novo no backend)..."
            )
            time.sleep(ESPERA_ANTES_DE_RECARREGAR)

            log("Recarregando a página antes de baixar...")
            driver.refresh()
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(),'Total de im')]")
            ))

            botao_notificacoes = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[@aria-label='Notificações' or .//i[normalize-space()='notifications']]")
            ))
            clicar_com_retentativa(driver, botao_notificacoes)
            time.sleep(1)

            links_baixar = driver.find_elements(By.XPATH, "//b[normalize-space()='Baixar']")
            if not links_baixar:
                # Reload pode ter demorado a atualizar a lista - tenta de
                # novo no próximo ciclo do loop em vez de assumir que
                # sumiu de vez.
                log("Aviso: depois do reload a notificação não apareceu ainda, tentando de novo...")
                _fechar_painel_notificacoes(driver)
                time.sleep(3)
                continue

            log("Relatório pronto! Clicando em 'Baixar'...")
            clicar_com_retentativa(driver, links_baixar[0])

            # --- 3) Confirma pelo disco que o download começou de verdade ---
            if not _download_comecou(pasta_download, arquivos_antes):
                log(
                    "Aviso: cliquei em 'Baixar' mas nenhum arquivo novo apareceu "
                    "na pasta de download (provável notificação obsoleta). "
                    "Tentando de novo..."
                )
                _fechar_painel_notificacoes(driver)
                time.sleep(3)
                continue

            log("Download iniciado!")
            # --- 4) Fecha o painel/modal antes de seguir ---
            _fechar_painel_notificacoes(driver)
            return

        except Exception:
            pass

        time.sleep(5)

    raise TimeoutException(
        "O relatório não ficou pronto (ou não consegui confirmar um "
        "download de verdade) dentro do tempo esperado. Verifique "
        "manualmente as notificações no Imobzi."
    )


def esperar_download_terminar(pasta_download, arquivos_antes, timeout=TIMEOUT_DOWNLOAD):
    log("Aguardando o arquivo terminar de baixar...")
    inicio = time.time()
    while time.time() - inicio < timeout:
        arquivos_agora = set(os.listdir(pasta_download))
        novos = arquivos_agora - arquivos_antes
        novos_completos = [
            f for f in novos
            if not f.endswith(".crdownload") and not f.endswith(".tmp")
        ]
        if novos_completos:
            # Confirma que o tamanho do arquivo parou de crescer
            caminho = os.path.join(pasta_download, novos_completos[0])
            tamanho1 = os.path.getsize(caminho)
            time.sleep(2)
            tamanho2 = os.path.getsize(caminho)
            if tamanho1 == tamanho2:
                return caminho
        time.sleep(2)

    raise TimeoutException("O download não terminou dentro do tempo esperado.")


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


def proximo_nome_disponivel(pasta_destino, data_str, extensao):
    versao = 1
    while True:
        nome = f"{NOME_BASE_ARQUIVO}_{data_str}v{versao}{extensao}"
        caminho = os.path.join(pasta_destino, nome)
        if not os.path.exists(caminho):
            return caminho
        versao += 1


def renomear_arquivo(caminho_baixado, pasta_destino):
    extensao = os.path.splitext(caminho_baixado)[1]
    data_str = datetime.now().strftime("%d%m%Y")
    destino = proximo_nome_disponivel(pasta_destino, data_str, extensao)
    os.makedirs(pasta_destino, exist_ok=True)
    os.replace(caminho_baixado, destino)
    log(f"Arquivo salvo como: {destino}")

    # Marca o arquivo como UTF-8 para o Excel (ver garantir_bom_utf8).
    garantir_bom_utf8(destino)

    return destino


def main():
    if not REPORT_URL:
        print("ERRO: defina IMOBZI_REPORT_URL_IMOVEIS no arquivo .env (link do relatorio no Imobzi).")
        sys.exit(1)
    if not EMAIL or not SENHA:
        print(
            "ERRO: defina IMOBZI_EMAIL e IMOBZI_SENHA no arquivo .env "
            "(copie o .env.example e preencha)."
        )
        sys.exit(1)

    pasta_download = os.path.abspath(PASTA_DESTINO)

    driver = montar_driver(pasta_download)
    wait = WebDriverWait(driver, TIMEOUT_PADRAO)

    try:
        arquivos_antes = set(os.listdir(pasta_download)) if os.path.isdir(pasta_download) else set()

        fazer_login(driver, wait)
        abrir_relatorio(driver, wait)
        aplicar_filtro_periodo_total(driver, wait)
        exportar_relatorio(driver, wait)
        esperar_relatorio_pronto_e_baixar(driver, wait, pasta_download, arquivos_antes)

        caminho_baixado = esperar_download_terminar(pasta_download, arquivos_antes)
        caminho_final = renomear_arquivo(caminho_baixado, pasta_download)

        # Gera o .xlsx pronto ao lado do CSV, com os acentos corretos.
        converter_para_xlsx(caminho_final)

        log("Concluído com sucesso!")
    except Exception:
        salvar_diagnostico(driver, pasta_download)
        raise
    finally:
        driver.quit()


def salvar_diagnostico(driver, pasta_download):
    """
    Se algo der errado, salva um print da tela e o HTML da página no
    momento do erro - ajuda muito a descobrir o que travou sem precisar
    reproduzir o problema ao vivo.
    """
    try:
        pasta_diag = os.path.join(pasta_download, "diagnostico")
        os.makedirs(pasta_diag, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")

        caminho_print = os.path.join(pasta_diag, f"erro_{carimbo}.png")
        caminho_html = os.path.join(pasta_diag, f"erro_{carimbo}.html")

        driver.save_screenshot(caminho_print)
        with open(caminho_html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        log(f"Diagnóstico salvo em: {caminho_print}")
        log(f"HTML da página no momento do erro salvo em: {caminho_html}")
    except Exception as e:
        log(f"Não foi possível salvar o diagnóstico do erro: {e}")


if __name__ == "__main__":
    main()
