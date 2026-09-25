import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА
# -----------------------------

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

# Красно-белый брендинг "Первый Снег" + Медленный снег
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    @keyframes snowfall {
        0% { transform: translateY(-10px) translateX(0); opacity: 0; }
        20% { opacity: 0.5; }
        100% { transform: translateY(100vh) translateX(25px); opacity: 0.05; }
    }
    .snowflake {
        position: fixed; top: -10px; color: #93c5fd; font-size: 11px;
        user-select: none; pointer-events: none; z-index: 1;
    }
    .s1 { left: 10%; animation: snowfall 15s linear infinite 0s; }
    .s2 { left: 30%; animation: snowfall 19s linear infinite 4s; }
    .s3 { left: 50%; animation: snowfall 16s linear infinite 2s; }
    .s4 { left: 70%; animation: snowfall 21s linear infinite 5s; }
    .s5 { left: 90%; animation: snowfall 17s linear infinite 1s; }

    .doc-card {
        background-color: #ffffff; border-left: 6px solid #dc2626;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #dc2626; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    .btn-doc:hover { background-color: #b91c1c; }

    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.03);
    }
    .badge-weight {
        background-color: #dc2626; color: white; font-weight: bold;
        padding: 3px 10px; font-size: 12px; border-radius: 12px;
        display: inline-block; margin-top: 6px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snowflake s1">❄</div><div class="snowflake s2">❅</div>
    <div class="snowflake s3">❆</div><div class="snowflake s4">❄</div><div class="snowflake s5">❅</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Каталогов & Упаковки {TARGET_YEAR}")
st.caption("Глубокий сбор подарочной упаковки (картон, наборы, тубусы). Юридический мусор блокируется.")

# -----------------------------
# ФИЛЬТРЫ МУСОРА
# -----------------------------

REQUIRED_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "2027", "новогод", "catalog", "price"]
JUNK_DOC_WORDS = ["политика", "согласие", "соглашение", "презентация", "реквизиты", "вакансии", "устав", "договор", "оферта", "инвесторам", "cookies"]

JUNK_IMG_WORDS = ["печенье", "батончик", "мармелад", "вафли", "карамель", "драже", "весовые", "штучные", "banner", "slider", "bg-", "logo", "icon"]
CATALOG_URL_WORDS = ["новогод", "подар", "набор", "упаков", "каталог", "catalog", "podarki", "karton", "katalog", "category"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("http"): value = "https://" + value
    return urllib.parse.urlparse(value).netloc.replace("www.", "")

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_domain_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    
    # Спец-обработка для Рэйд-21 (у них под подарки отдельный домен)
    if "рэйд" in q_low or "рейд" in q_low or "raid" in q_low:
        return "podarki-reid21.ru"

    try:
        query = f'"{company_name}" новогодние подарки официальный сайт'
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a['href']).query).get("uddg", [a['href']])[0]
                netloc = normalize_domain(target)
                if netloc and not any(bad in netloc for bad in ["wikipedia", "vk.com", "youtube", "list-org", "checko"]):
                    return netloc
    except: pass
    return None

# --- ШАГ 1: ПОИСК PDF/EXCEL (БЕЗ ПРЕЗЕНТАЦИЙ И ЮР. МУСОРА) ---

def is_valid_catalog_file(title: str, url: str) -> bool:
    combined = (title + " " + url).lower()
    if any(junk in combined for junk in JUNK_DOC_WORDS): return False
    if any(good in combined for good in REQUIRED_DOC_WORDS): return True
    return False

def scan_for_documents(domain: str):
    docs, seen = [], set()
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return docs

    scan_urls = [final_url]
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        full = urllib.parse.urljoin(final_url, a['href'])
        if domain in full and any(cw in full.lower() or cw in a.get_text().lower() for cw in CATALOG_URL_WORDS):
            if full not in scan_urls and len(scan_urls) < 8:
                scan_urls.append(full)

    def check_page_docs(url):
        page_docs = []
        p_url, p_html = get_html(url)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = urllib.parse.unquote(a['href']).lower()
                text = a.get_text().strip()
                full_link = urllib.parse.urljoin(p_url, a['href'])
                
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if is_valid_catalog_file(text, href):
                        page_docs.append({"title": text or "Официальный каталог подарков", "link": full_link})
        return page_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(check_page_docs, scan_urls):
            for d in res:
                if d['link'] not in seen:
                    seen.add(d['link'])
                    docs.append(d)
    return docs

# --- ШАГ 2: ГЛУБОКИЙ СБОР ПОДАРКОВ В КАРТОННОЙ И ДРУГОЙ УПАКОВКЕ ---

def download_product_image(img_url: str):
    """Качает фото и фильтрует баннеры сайта по пропорциям"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=5)
        if res.status_code == 200 and len(res.content) > 3500:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 140 or h < 140: return None
                
                ratio = w / h
                # КОРОБКИ И ПОДАРКИ: от 0.4 до 1.55 (баннеры отсекаются)
                if ratio > 1.6 or ratio < 0.38: return None
                
                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else: ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except: pass
    return None

def scan_products_deep(domain: str):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    category_pages = [final_url]
    
    # 1. ГЛУБОКИЙ ПОИСК: Находим все подкатегории ("Картонная упаковка", "Текстиль", "Наборы")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        full = urllib.parse.urljoin(final_url, href)
        
        if domain in full and any(cw in href.lower() or cw in text for cw in CATALOG_URL_WORDS):
            if full not in category_pages:
                category_pages.append(full)
        if len(category_pages) >= 15: break

    raw_products = []

    # 2. Сканируем каждую категорию и извлекаем товары
    def parse_category_page(p_url):
        _, p_html = get_html(p_url)
        if not p_html: return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        prods = []

        # Контейнеры карточек товаров
        containers = p_soup.find_all(
            lambda t: t.name in ["div", "li", "article", "section"]
            and t.get("class")
            and any(c in " ".join(t.get("class")).lower() for c in ["product", "catalog-item", "card", "item", "goods", "element"])
        )
        if not containers: containers = p_soup.find_all("img")

        for card in containers:
            img = card if card.name == "img" else card.find("img")
            if not img: continue

            src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg-", "social", "avatar"]):
                continue

            full_img = urllib.parse.urljoin(p_url, src)
            text = card.get_text(" ", strip=True) if card.name != "img" else ""

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if len(title) > 2 and not any(junk in title.lower() for junk in JUNK_IMG_WORDS):
                prods.append({"title": title, "weight": weight, "img_url": full_img})
        return prods

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_category_page, category_pages):
            raw_products.extend(res)

    unique_prods, seen = [], set()
    for p in raw_products:
        if p["img_url"] not in seen:
            seen.add(p["img_url"])
            unique_prods.append(p)

    def fetch_img(p):
        img_info = download_product_image(p["img_url"])
        if img_info:
            p["img_bytes"], p["ext"] = img_info["bytes"], img_info["ext"]
            return p
        return None

    validated = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(fetch_img, unique_prods[:80]) if r]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название фабрики или её сайт:",
    placeholder="Например: Рэйд-21, Рубин, Академия Шоколада, podarki-reid21.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip(): st.stop()

    input_str = company_input.strip()
    domain = normalize_domain(input_str) if "." in input_str and " " not in input_str else find_domain_dynamic(input_str)

    if domain:
        st.success(f"🌐 Официальный сайт найден: `{domain}`")

        with st.spinner("ШАГ 1: Сканируем сайт на наличие готовых PDF/Excel каталогов..."):
            documents = scan_for_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Найдено прямое скачивание каталогов. Визуальный обход заменен файлами.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["link"].lower() else "📊 EXCEL / DOC"
                st.markdown(f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">Ссылка: {doc['link']}</small><br>
                        <a href="{doc['link']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """, unsafe_allow_html=True)
        else:
            with st.spinner("ШАГ 2: Захожу во внутренние разделы (Картонная упаковка, Наборы) и извлекаю коробки..."):
                products = scan_products_deep(domain)

            st.markdown("---")
            if products:
                st.success(f"Успешно найдено коробок и подарочных наборов: **{len(products)} шт.**")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"box_{i+1:02d}_{safe_name}.{prod['ext']}", prod["img_bytes"])

                st.download_button(
                    f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_packaging.zip",
                    mime="application/zip",
                )

                st.markdown("---")
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """, unsafe_allow_html=True)
                        st.image(prod["img_bytes"], use_container_width=True)
            else:
                st.error("На сайте не удалось найти упаковку.")
    else:
        st.error("Не удалось найти сайт. Введите домен напрямую (например: podarki-reid21.ru)")

st.divider()
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Автоматический переход во внутренние категории упаковки.")
