import os
import re
import time
import random
from urllib.parse import urljoin, urlsplit, unquote
from typing import List, Dict, Tuple, Optional

import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidSessionIdException


# ===================== CONFIG GERAL =====================
# Planilha com os links das imobiliarias (1 link por linha). Defina VIVAREAL_PLANILHA_LINKS
# no ambiente ou coloque "Link das Imobiliarias.xlsx" ao lado deste script.
PLANILHA_LINKS = os.environ.get("VIVAREAL_PLANILHA_LINKS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Link das Imobiliarias.xlsx"
)

COLUNA_LINKS_NOME = None
COLUNA_LINKS_INDICE = 1

HEADLESS = False
MAX_PAGES = None          # None = até acabar o botão
MAX_SESSIONS = 2          # mantém seu protocolo (Sessão 1 + Sessão 2)
BASE_URL = "https://www.vivareal.com.br"

STREET_INCLUDE = None

PAUSA_ENTRE_CHROMES = 0.4
RETRIES_POR_LINK = 2
TIMEOUT_BODY = 25

# Ritmo menor
PAUSA_ENTRE_PAGINAS_MIN = 1.0
PAUSA_ENTRE_PAGINAS_MAX = 3.0
PAUSA_ENTRE_LINKS_MIN = 5.0
PAUSA_ENTRE_LINKS_MAX = 10.0

# Scroll até estabilizar
SCROLL_PAUSE = 0.90
SCROLL_STABLE_ROUNDS = 3
SCROLL_HARD_LIMIT = 30

OUTPUT_BASENAME = "VIVAREAL"
OUTPUT_SHEET = "dados"

# Opcional: se definida, a planilha final e salva NESSA pasta em vez de ao
# lado da planilha de links (PLANILHA_LINKS). Usado pelo app (botao
# "Atualizar" da Seleção Externa) para garantir que o resultado sempre cai
# em "Atualização externa" - rodando o script direto pelo terminal, sem
# essa variavel definida, o comportamento continua o de sempre (salva ao
# lado de PLANILHA_LINKS).
PASTA_SAIDA_OVERRIDE = os.environ.get("VIVAREAL_PASTA_SAIDA", "").strip()
# =======================================================


# ===================== ENRIQUECIMENTO (ID, m², status, valor) =====================
RE_ID     = re.compile(r"-id-(\d+)(?=(?:/|\?|$))", re.I)
RE_AREA   = re.compile(r"^\d{2,7}(?:m2|m²)$", re.I)
RE_STATUS = re.compile(r"^(aluguel|venda|temporada)$", re.I)
RE_VALOR  = re.compile(r"^(?:RS|R\$)\s?\d[\d\.\,]*$", re.I)

NORMALIZAR_VALOR_BRL = False
PADRONIZAR_M2 = False

def extrair_id(url: str) -> Optional[str]:
    if isinstance(url, str):
        m = RE_ID.search(url)
        return m.group(1) if m else None
    return None

def normalizar_valor(valor: str) -> str:
    if not isinstance(valor, str):
        return valor
    txt = valor.replace(" ", "").upper()
    if txt.startswith("RS"):
        txt = "R$" + txt[2:]
    elif not txt.startswith("R$"):
        return valor
    numeros = txt[2:]
    if "," not in numeros:
        numeros = f"{numeros},00"
    parte, centavos = numeros.rsplit(",", 1)
    parte = parte.replace(".", "")
    parte_rev = "".join(reversed(parte))
    grupos = [parte_rev[i:i+3] for i in range(0, len(parte_rev), 3)]
    parte = ".".join("".join(reversed(g)) for g in grupos[::-1])
    return f"R$ {parte},{centavos.zfill(2)}"

def extrair_campos_do_slug(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(url, str) or not url.strip():
        return None, None, None
    path = unquote(urlsplit(url).path or "")
    if not path:
        return None, None, None
    slug_antes_id = path.split("-id-")[0]
    tokens = [t.strip() for t in slug_antes_id.split("-") if t.strip()]
    area = status = valor = None
    for t in reversed(tokens):
        t_clean = t.strip()
        if area is None and RE_AREA.match(t_clean):
            area = t_clean.lower()
            continue
        if status is None and RE_STATUS.match(t_clean):
            status = t_clean.lower()
            continue
        if valor is None and RE_VALOR.match(t_clean):
            valor = re.sub(r"\s+", "", t_clean)
            if NORMALIZAR_VALOR_BRL:
                valor = normalizar_valor(valor)
            continue
        if area and status and valor:
            break
    if area and PADRONIZAR_M2:
        area = area.replace("m2", "m²")
    return area, status, valor
# ===============================================================================


# ===================== HELPERS DE RITMO =====================
def pausa_paginas():
    time.sleep(random.uniform(PAUSA_ENTRE_PAGINAS_MIN, PAUSA_ENTRE_PAGINAS_MAX))

def pausa_links():
    time.sleep(random.uniform(PAUSA_ENTRE_LINKS_MIN, PAUSA_ENTRE_LINKS_MAX))
# ===============================================================================


# ===================== CRAWLER =====================
def build_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception:
        pass
    return driver

def close_banners(driver):
    candidates = [
        (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
        (By.XPATH, "//button[contains(., 'Aceitar')]"),
        (By.XPATH, "//button[contains(., 'Entendi')]"),
        (By.XPATH, "//button[contains(., 'OK')]"),
        (By.XPATH, "//button[contains(., 'Fechar')]"),
    ]
    time.sleep(0.7)
    for by, sel in candidates:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
            el.click()
            time.sleep(0.2)
        except Exception:
            pass

def is_blocked(driver) -> bool:
    """Só detecta e para; não tenta contornar."""
    try:
        src = (driver.page_source or "").lower()
        return ("you have been blocked" in src) or ("sorry, you have been blocked" in src)
    except Exception:
        return False

def wait_for_results(driver, timeout=25):
    """
    Espera algum indicativo de listagem carregada (não depende de rua).
    """
    selectors = [
        "a[href*='/imovel/']",
        "a[data-cy='property-card-link']",
        "div[data-cy*='cardProperty']",
        "article",
    ]
    WebDriverWait(driver, timeout).until(lambda d: any(d.find_elements(By.CSS_SELECTOR, s) for s in selectors))

def scroll_until_stable(driver):
    """
    Scroll até estabilizar a contagem de cards (menos risco de perder anúncio por lazy-load).
    """
    last_count = -1
    stable = 0
    for _ in range(SCROLL_HARD_LIMIT):
        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/imovel/'], a[data-cy='property-card-link']")
        count = len(cards)

        if count == last_count and count > 0:
            stable += 1
            if stable >= SCROLL_STABLE_ROUNDS:
                return
        else:
            stable = 0
            last_count = count

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE)

def absolute_url(href: str) -> str:
    if not href:
        return ""
    return urljoin(BASE_URL, href)

def get_links_and_addresses_on_page(driver) -> List[Dict[str, str]]:
    """
    Otimizado:
    - Coleta TODOS os links de imóveis na página
    - Endereço vira best-effort (não é pré-requisito)
    """
    scroll_until_stable(driver)

    link_els = driver.find_elements(By.CSS_SELECTOR, "a[href*='/imovel/'], a[data-cy='property-card-link']")
    results: List[Dict[str, str]] = []
    seen_local = set()

    for a in link_els:
        try:
            href = absolute_url(a.get_attribute("href") or "")
            if not href or href in seen_local:
                continue
            seen_local.add(href)

            endereco = ""
            try:
                card = a.find_element(By.XPATH, "ancestor::*[self::article or self::div][1]")
                for sel in [
                    "p[data-cy='rp-cardProperty-street-txt']",
                    "p[data-cy*='street']",
                    "p[data-testid*='street']",
                    "p[data-cy*='address']",
                    "span[data-cy*='address']",
                ]:
                    els = card.find_elements(By.CSS_SELECTOR, sel)
                    if els and (els[0].text or "").strip():
                        endereco = els[0].text.strip()
                        break
            except Exception:
                pass

            # filtro opcional (não descarta anúncio se endereço não existir)
            if STREET_INCLUDE is not None and endereco:
                if endereco not in STREET_INCLUDE:
                    continue

            results.append({"endereco": endereco, "url": href})
        except Exception:
            continue

    return results

def go_to_next_page(driver, timeout=15) -> bool:
    """
    Otimizado para o HTML que você mandou:
    <a aria-label="próxima página" aria-disabled="false" class="olx-core-pagination__icon" ...>

    - Busca aria-label minúsculo
    - Confere aria-disabled
    - Confirma navegação por URL ou staleness de um elemento âncora
    """
    old_url = driver.current_url

    # âncora para staleness (se URL não mudar)
    anchor = None
    try:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/imovel/'], a[data-cy='property-card-link']")
        anchor = anchors[0] if anchors else None
    except Exception:
        anchor = None

    # expõe paginação
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 1200);")
        time.sleep(0.35)
    except Exception:
        pass

    selectors = [
        # ✅ o seu caso real
        (By.CSS_SELECTOR, "a.olx-core-pagination__icon[aria-label='próxima página']"),
        (By.CSS_SELECTOR, "a[aria-label='próxima página']"),
        (By.CSS_SELECTOR, "a[aria-label*='próxima']"),
        (By.CSS_SELECTOR, "a[rel='next']"),
        (By.XPATH, "//a[contains(translate(@aria-label,'PRÓXIMA','próxima'),'próxima')]"),
    ]

    for by, sel in selectors:
        try:
            btn = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, sel)))

            aria_disabled = (btn.get_attribute("aria-disabled") or "").lower() == "true"
            cls = (btn.get_attribute("class") or "").lower()
            disabled = aria_disabled or ("disabled" in cls)
            if disabled:
                continue

            btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.25)
            btn.click()

            changed = False
            try:
                WebDriverWait(driver, timeout).until(lambda d: d.current_url != old_url)
                changed = True
            except Exception:
                if anchor is not None:
                    try:
                        WebDriverWait(driver, timeout).until(EC.staleness_of(anchor))
                        changed = True
                    except Exception:
                        pass

            if not changed:
                continue

            WebDriverWait(driver, TIMEOUT_BODY).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            close_banners(driver)

            if is_blocked(driver):
                print("[BLOQUEADO] detectado após trocar de página. Parando este link.")
                return False

            wait_for_results(driver, timeout=TIMEOUT_BODY)
            return True

        except Exception:
            continue

    return False

def scrape_current_session(driver, all_rows: List[Dict[str, str]], seen: set, max_pages: Optional[int] = None) -> int:
    page = 1
    total_added = 0

    while True:
        print(f"Página {page}: coletando…")

        if is_blocked(driver):
            print("[BLOQUEADO] detectado. Parando este link.")
            break

        wait_for_results(driver, timeout=TIMEOUT_BODY)
        rows = get_links_and_addresses_on_page(driver)

        novos = 0
        for r in rows:
            url = r.get("url")
            if url and url not in seen:
                seen.add(url)
                all_rows.append(r)
                novos += 1

        total_added += novos
        print(f"  +{novos} (acumulado {len(all_rows)})")

        if max_pages is not None and page >= max_pages:
            break

        pausa_paginas()

        if not go_to_next_page(driver):
            break

        page += 1

    return total_added

def switch_to_rent_and_search(driver) -> bool:
    """
    Mantive sua lógica. Só deixei a espera mais robusta:
    - depois do click, espera "resultado", não rua.
    """
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.2)

        try:
            rent_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-cy='rp-rent-tab']"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", rent_tab)
            time.sleep(0.2)
            rent_tab.click()
            time.sleep(0.3)
        except Exception:
            pass

        search_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-cy='rp-search-btn']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", search_btn)
        time.sleep(0.2)
        search_btn.click()

        wait_for_results(driver, timeout=TIMEOUT_BODY)
        time.sleep(0.3)
        return True

    except Exception as e:
        print("Não abriu nova sessão (Alugar -> Buscar Imóveis). Motivo:", e)
        return False
# ==========================================================


# ===================== ORQUESTRAÇÃO (um Chrome NOVO por link) =====================
def processar_link_base(start_url: str, all_rows: List[Dict[str, str]], seen: set) -> None:
    tentativas = 0
    while tentativas <= RETRIES_POR_LINK:
        tentativas += 1
        driver = None
        try:
            print(f"\n>>> Iniciando: {start_url} (tentativa {tentativas})")
            driver = build_driver(headless=HEADLESS)
            driver.get(start_url)
            WebDriverWait(driver, TIMEOUT_BODY).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            close_banners(driver)

            if is_blocked(driver):
                print("[BLOQUEADO] detectado ao abrir link base. Pulando.")
                return

            # Sessão 1
            print("Sessão 1…")
            scrape_current_session(driver, all_rows, seen, max_pages=MAX_PAGES)

            # Sessões adicionais
            sessions_done = 1
            while sessions_done < MAX_SESSIONS:
                print("Nova sessão (Alugar -> Buscar Imóveis)…")
                if not switch_to_rent_and_search(driver):
                    break
                sessions_done += 1
                scrape_current_session(driver, all_rows, seen, max_pages=MAX_PAGES)

            return

        except (InvalidSessionIdException, WebDriverException, TimeoutException) as e:
            print(f"[WARN] Falha no link base: {e}")
            if tentativas > RETRIES_POR_LINK:
                print("[WARN] Limite de tentativas atingido; seguindo para o próximo link.")
                return

        except Exception as e:
            print(f"[WARN] Erro inesperado: {e}")
            if tentativas > RETRIES_POR_LINK:
                return

        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

            time.sleep(PAUSA_ENTRE_CHROMES)
            pausa_links()

def scrape_for_start_urls(start_urls: List[str]) -> List[Dict[str, str]]:
    all_rows: List[Dict[str, str]] = []
    seen: set = set()
    for idx, url in enumerate(start_urls, start=1):
        if not isinstance(url, str) or not url.strip():
            continue
        print(f"\n=== [{idx}/{len(start_urls)}] {url}")
        processar_link_base(url, all_rows, seen)
    return all_rows
# ==========================================================


# ===================== I/O: leitura de links e salvamento =====================
def detectar_coluna_links(df: pd.DataFrame) -> pd.Series:
    if COLUNA_LINKS_NOME and COLUNA_LINKS_NOME in df.columns:
        return df[COLUNA_LINKS_NOME]
    candidatos = [c for c in df.columns if str(c).strip().lower() in {"link", "links", "url", "urls"}]
    if candidatos:
        return df[candidatos[0]]
    if df.shape[1] >= 2:
        return df.iloc[:, COLUNA_LINKS_INDICE]
    raise ValueError("Não foi possível identificar a coluna de links (mínimo 2 colunas necessárias).")

def proximo_nome_disponivel(pasta: str, base: str = OUTPUT_BASENAME, ext: str = ".xlsx") -> str:
    saida = os.path.join(pasta, base + ext)
    i = 0
    while os.path.exists(saida):
        i += 1
        saida = os.path.join(pasta, f"{base}_{i}{ext}")
    return saida

def salvar_planilha_unica_enriquecida(rows: List[Dict[str, str]], caminho_saida: str) -> None:
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=["endereco", "url"])

    ids, areas, statuses, valores = [], [], [], []
    for u in df["url"].fillna(""):
        ids.append(extrair_id(u))
        a, s, v = extrair_campos_do_slug(u)
        areas.append(a)
        statuses.append(s)
        valores.append(v)

    df["ID"] = ids
    df["m²"] = areas
    df["status"] = statuses
    df["valor"] = valores

    with pd.ExcelWriter(caminho_saida, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=OUTPUT_SHEET)

    print(f"\n✅ Planilha criada: {caminho_saida}")
    print(f"   Registros: {len(df)}")
# ==========================================================


# ===================== MAIN =====================
def main():
    if not os.path.exists(PLANILHA_LINKS):
        raise FileNotFoundError(f"Não encontrei a planilha: {PLANILHA_LINKS}")

    df_links = pd.read_excel(PLANILHA_LINKS)
    serie_links = detectar_coluna_links(df_links)
    start_urls = [str(u).strip() for u in serie_links.tolist() if isinstance(u, str) and u.strip()]
    if not start_urls:
        raise ValueError("Nenhum link válido encontrado na planilha de entrada.")

    print(f"Total de URLs base: {len(start_urls)}")

    rows = scrape_for_start_urls(start_urls)

    pasta_saida = PASTA_SAIDA_OVERRIDE or os.path.dirname(os.path.abspath(PLANILHA_LINKS))
    caminho_saida = proximo_nome_disponivel(pasta_saida, base=OUTPUT_BASENAME, ext=".xlsx")
    salvar_planilha_unica_enriquecida(rows, caminho_saida)

if __name__ == "__main__":
    main()
