import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт Pillow для проверки изображений
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Анализ Каталогов & Упаковки",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

# Праздничный стиль + Логотип + Нежный медленный снег
st.markdown(
    """
    <style>
    /* Зимний мягкий фон */
    .stApp { 
        background: linear-gradient(180deg, #f0f7ff 0%, #f8fafc 100%);
    }
    
    /* Фирменный логотип Первый Снег */
    .brand-logo {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
        color: #ffffff !important;
        font-weight: 900;
        font-size: 15px;
        padding: 8px 18px;
        border-radius: 20px;
        box-shadow: 0 4px 12px rgba(2, 132, 199, 0.25);
        display: inline-block;
        letter-spacing: 1px;
    }
    
    /* Анимация падающего мягкого снега */
    @keyframes snowfall {
        0% { transform: translateY(-10px) translateX(0); opacity: 0; }
        20% { opacity: 0.7; }
        100% { transform: translateY(100vh) translateX(30px); opacity: 0.1; }
    }
    .snowflake {
        position: fixed;
        top: -10px;
        color: #7dd3fc;
        font-size: 12px;
        user-select: none;
        pointer-events: none;
        z-index: 1;
    }
    .sf1 { left: 15%; animation: snowfall 14s linear infinite 0s; }
    .sf2 { left: 35%; animation: snowfall 18s linear infinite 3s; }
    .sf3 { left: 55%; animation: snowfall 16s linear infinite 6s; }
    .sf4 { left: 75%; animation: snowfall 20s linear infinite 2s; }
    .sf5 { left: 90%; animation: snowfall 15s linear infinite 5s; }

    /* Карточки файлов */
    .doc-card {
        background-color: #ffffff;
        border-left: 6px solid #10b981;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        position: relative;
        z-index: 10;
    }
    .btn-doc {
        background-color: #10b981;
        color: white !important;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        margin-top: 8px;
    }
    .btn-doc:hover { background-color: #059669; }

    /* Карточки коробок */
    .product-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        position: relative;
        z-index: 10;
    }
    .badge-weight {
        background-color: #0284c7;
        color: white;
        font-weight: bold;
        padding: 3px 10px;
        font-size: 12px;
        border-radius: 12px;
        display: inline-block;
        margin-top: 6px;
    }
    .product-title {
        font-weight: 700;
        font-size: 13px;
        color: #1e293b;
        margin: 8px 0;
        line-height: 1.3;
    }
    </style>
    
    <!-- Снежинки -->
    <div class="snowflake sf1">❄</div>
    <div class="snowflake sf2">❅</div>
    <div class="snowflake sf3">❆</div>
    <div class="snowflake sf4">❄</div>
    <div class="snowflake sf5">❅</div>
    """,
    unsafe_allow_html=True,
)

# Шапка с брендингом
col_title, col_logo = st.columns([4, 1])
with col_title:
    st.title(f"📦 Анализ Каталогов & Упаковки {TARGET_YEAR}")
    st.caption("Приоритетный поиск официальных PDF/Excel каталогов. Автосбор изображений коробок и подарков.")
with col_logo:
    st.markdown("<div style='text-align: right; margin-top: 15px;'><span class='brand-logo'>❄️ ПЕРВЫЙ СНЕГ</span></div>", unsafe_allow_html=True)

# -----------------------------
# БАЗА ЗНАНИЙ
# -----------------------------

KNOWLEDGE_BASE = {
    "академия шоколада": "chocolate-academy.ru",
    "акконд": "akkond.ru",
    "рубин": "rubin-2000.ru",
    "лаконд": "lakond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "абинекс": "abineks.ru",
    "рэйд-21": "raid21.ru",
    "сибпродторг": "sibprodtorg.ru",
    "столичные поставки": "stolichnye.ru",
    "униконф": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "фортуна": "fortuna-podarki.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
    "красный мозырянин": "mozyrconfectionery.by",
}

# ЖЕСТКИЙ БЛОК ЮРИДИЧЕСКОГО МУСОРА ДЛЯ ФАЙЛОВ
EXCLUDE_DOC_KEYWORDS = [
    "политика", "конфиденциальности", "пользовательское", "соглашение", 
    "обработка", "персональных", "данных", "согласие", "вакансии", 
    "реквизиты", "устав", "договор", "оферта", "инвесторам", "cookies"
]

# СЛОВА ДЛЯ ОТСЕИВАНИЯ МЕЛКИХ КОНФЕТ И БАННЕРОВ
JUNK_IMG_WORDS = [
    "печенье", "батончик", "мармелад", "вафли", "карамель", "драже", 
    "весовые", "штучные", "banner", "slider", "bg-", "logo", "icon", "avatar"
]

CATALOG_URL_WORDS = [
    "новогод", "подар", "набор", "упаков", "каталог", "catalog", 
    "katalog", "podarki", "produk", "shop"
]

PROBE_PATHS = [
    "", "/catalog/", "/katalog/", "/podarki/", "/novogodnie-podarki/", 
    "/upakovka/", "/shop/", "/catalog/novogodnie-podarki/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

WEIGHT_REGEX = re.compile(
    r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE
)

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.replace("www.", "")

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def find_domain_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v

    try:
        query = f'"{company_name}" новогодняя упаковка подарки официальный сайт'
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(
                    urllib.parse.urlparse(a["href"]).query
                ).get("uddg", [a["href"]])[0]
                netloc = normalize_domain(target)
                if netloc and not any(
                    bad in netloc
                    for bad in ["wikipedia", "vk.com", "youtube", "list-org", "checko", "pravo"]
                ):
                    return netloc
    except Exception:
        pass
    return None

# --- ШАГ 1: ПОИСК ТОЛЬКО НАСТОЯЩИХ КАТАЛОГОВ (PDF / EXCEL) ---

def scan_for_documents(domain: str):
    docs, seen = [], set()
    base_protocol = f"https://{domain}"
    urls_to_check = [base_protocol + p for p in PROBE_PATHS]

    def check_page_docs(url):
        page_docs = []
        p_url, p_html = get_html(url)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = urllib.parse.unquote(a["href"]).lower()
                text = a.get_text().strip()
                text_low = text.lower()
                full_link = urllib.parse.urljoin(p_url, a["href"])

                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    combined = f"{text_low} {href}"
                    
                    # 1. БЛОКИРУЕМ ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ
                    if any(junk in combined for junk in EXCLUDE_DOC_KEYWORDS):
                        continue

                    # 2. ПОДТВЕРЖДАЕМ, ЧТО ЭТО КАТАЛОГ/ПРАЙС
                    page_docs.append(
                        {
                            "title": text or "Скачать каталог / прайс-лист 2026",
                            "link": full_link,
                        }
                    )
        return page_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(check_page_docs, urls_to_check):
            for d in res:
                if d["link"] not in seen:
                    seen.add(d["link"])
                    docs.append(d)
    return docs

# --- ШАГ 2: ВИЗУАЛЬНЫЙ СБОР КОРOБОК И ПОДАРКОВ ---

def download_product_image(img_url: str):
    """Качает фото и отсеивает узкие баннеры"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=5)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 120 or h < 120:
                    return None

                ratio = w / h
                # Фильтр пропорций: коробки от 0.35 до 2.2. Узкие баннеры отсекаются.
                if ratio > 2.5 or ratio < 0.3:
                    return None

                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except Exception:
        pass
    return None

def scan_products(domain: str):
    base_protocol = f"https://{domain}"
    urls_to_check = [base_protocol + p for p in PROBE_PATHS]

    raw_products = []

    def parse_page_products(p_url):
        _, p_html = get_html(p_url)
        if not p_html:
            return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        prods = []

        # Поиск контейнеров карточек
        containers = p_soup.find_all(
            lambda t: t.name in ["div", "li", "article"]
            and t.get("class")
            and any(
                c in " ".join(t.get("class")).lower()
                for c in ["product", "catalog-item", "card", "item", "goods", "element"]
            )
        )
        if not containers:
            containers = p_soup.find_all("img")

        for card in containers:
            img = card if card.name == "img" else card.find("img")
            if not img:
                continue

            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
            )
            if not src:
                continue

            full_img = urllib.parse.urljoin(p_url, src)
            if any(bad in full_img.lower() for bad in ["logo", "icon", "banner", "bg-", "social", "avatar"]):
                continue

            text = card.get_text(" ", strip=True) if card.name != "img" else ""

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            # Фильтр штучных конфет
            if len(title) > 2 and not any(junk in title.lower() for junk in JUNK_IMG_WORDS):
                prods.append({"title": title, "weight": weight, "img_url": full_img})
        return prods

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_page_products, urls_to_check):
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
        validated = [r for r in executor.map(fetch_img, unique_prods[:60]) if r]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название фабрики или её сайт:",
    placeholder="Например: Рубин, Академия Шоколада, Лаконд, lakond.ru, chocolate-academy.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    input_str = company_input.strip()
    domain = (
        normalize_domain(input_str)
        if "." in input_str and " " not in input_str
        else find_domain_dynamic(input_str)
    )

    if domain:
        st.success(f"🌐 Официальный сайт найден: `{domain}`")

        with st.spinner("ШАГ 1: Проверяем наличие официальных PDF/Excel прайсов..."):
            documents = scan_for_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Поиск карточек отменен, скачайте полный официальный файл ниже.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["link"].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">Ссылка: {doc['link']}</small><br>
                        <a href="{doc['link']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            with st.spinner("ШАГ 2: Прямые файлы не найдены. Извлекаю фотографии коробок с сайта..."):
                products = scan_products(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено подарочной упаковки и наборов: **{len(products)} шт.**")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"box_{i+1:02d}_{safe_name}.{prod['ext']}", prod["img_bytes"])

                st.download_button(
                    f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_boxes.zip",
                    mime="application/zip",
                )

                st.markdown("---")
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(
                            f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.image(prod["img_bytes"], use_container_width=True)
            else:
                st.error("На сайте не удалось автоматически выгрузить файлы или упаковку.")
    else:
        st.error("Не удалось определить сайт. Введите адрес сайта напрямую (например, chocolate-academy.ru)")

st.divider()
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Юридические документы и мусор отсекаются автоматически.")
