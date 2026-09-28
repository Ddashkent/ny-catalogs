import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Отключаем предупреждения SSL
requests.packages.urllib3.disable_warnings()

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Анализ Упаковки 2026",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

# Стабильный CSS: Логотип + Безопасный снег на фоне body
st.markdown(
    """
    <style>
    .stApp { 
        background-color: #f8fafc; 
    }
    
    /* Красно-белый логотип Первый Снег */
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    /* Нежный редкий снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px) translateX(0); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh) translateX(20px); opacity: 0.05; }
    }
    .snowflake {
        position: fixed; top: -10px; color: #93c5fd; font-size: 11px;
        user-select: none; pointer-events: none; z-index: 1;
    }
    .s1 { left: 10%; animation: snowfall 16s linear infinite 0s; }
    .s2 { left: 35%; animation: snowfall 20s linear infinite 3s; }
    .s3 { left: 65%; animation: snowfall 18s linear infinite 1s; }
    .s4 { left: 88%; animation: snowfall 22s linear infinite 5s; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snowflake s1">❄</div><div class="snowflake s2">❅</div>
    <div class="snowflake s3">❆</div><div class="snowflake s4">❄</div>
""",
    unsafe_allow_html=True,
)

st.title(f"📦 Анализ Новогодней Упаковки {TARGET_YEAR}")
st.caption("Приоритет: Поиск официальных PDF/Excel каталогов. Извлечение коробок без презентаций и рекламного мусора.")

# -----------------------------
# БАЗА ЗНАНИЙ И ТОЧНЫЕ АДРЕСА
# -----------------------------

SITE_MAP = {
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "акконд": "akkond.ru",
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
}

# Прямые целевые разделы подарков
DIRECT_GIFT_URLS = {
    "kommunarka.by": [
        "https://www.kommunarka.by/catalog/novogodnie-podarki/",
        "https://kommunarka.by/catalog/novogodnie-podarki/",
        "https://www.kommunarka.by/catalog/",
    ],
    "spartak.by": [
        "https://spartak.by/catalog/novogodnie_podarki/",
        "https://spartak.by/catalog/novogodnie-podarki/",
        "https://spartak.by/catalog/",
    ],
    "akkond.ru": [
        "https://akkond.ru/catalog/novyy_god/",
        "https://akkond.ru/catalog/novogodnie-podarki/",
    ],
    "rubin-2000.ru": [
        "https://rubin-2000.ru/catalog/",
        "https://rubin-2000.ru/catalog/upakovka/",
    ],
    "podarki-reid21.ru": [
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarochnye-nabory-novogodnie-podarki-2027/",
    ],
    "chocolate-academy.ru": [
        "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
        "https://chocolate-academy.ru/catalog/",
    ],
    "lakond.ru": ["https://lakond.ru/products/"],
}

# БЛОКИРОВКА ЮРИДИЧЕСКИХ ФАЙЛОВ И ПРЕЗЕНТАЦИЙ
DOC_BLACKLIST = [
    "презентация", "соглашение", "политика", "конфиденциальности", 
    "договор", "оферта", "вакансии", "реквизиты", "cookies", "устав"
]

DOC_WHITELIST = ["каталог", "прайс", "price", "catalog", "подарки", "упаковка"]

# СЛУЖЕБНЫЕ ИКОНКИ И ЛОГОТИПЫ
JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk"
]

TEXTILE_AND_TOY_JUNK = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    for k, domain in SITE_MAP.items():
        if k in v:
            return domain
    if "." in v and " " not in v:
        return v.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def fix_and_encode_url(base_url: str, src: str) -> str:
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment))

def get_html(url: str):
    if any(bad_path in url.lower() for bad_path in ["/news", "/novosti", "/press", "/blog", "/about"]):
        return None, None
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def find_domain_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    dom = normalize_domain(q_low)
    if dom:
        return dom
    try:
        from duckduckgo_search import DDGS
        query = f'"{company_name}" кондитерская фабрика новогодние подарки упаковка официальный сайт'
        with DDGS() as ddgs:
            res = list(ddgs.text(query, region="ru-ru", max_results=5))
            for r in res:
                link = r.get("href", "")
                if link and not any(bad in link.lower() for bad in ["wikipedia", "vk.com", "youtube", "checko"]):
                    return normalize_domain(link)
    except Exception:
        pass
    return None

# --- ШАГ 1: ПОИСК PDF КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ И ЮР. МУСОРА) ---

def scan_documents(domain: str):
    docs, seen = [], set()
    urls = DIRECT_GIFT_URLS.get(domain, [f"https://{domain}/catalog/", f"https://{domain}"])

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip().lower()
            full_link = fix_and_encode_url(url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                # 1. ЗАБЛОКИРОВАТЬ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if any(bad in combined for bad in DOC_BLACKLIST):
                    continue
                # 2. ТРЕБОВАТЬ СЛОВА КАТАЛОГ ИЛИ ПРАЙС
                if any(good in combined for good in DOC_WHITELIST):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

# --- ШАГ 2: ВЫГРУЗКА ТОЛЬКО ПОДАРКОВ И КОРОБОК ---

def download_product_image(img_url: str):
    """Загружает фото подарка и проверяет геометрию (без баннеров и логотипов)"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size

                # Отсекаем иконки
                if w < 120 or h < 120:
                    return None

                ratio = w / h
                # Подарочные коробки: пропорции от 0.35 до 1.6
                if ratio > 1.65 or ratio < 0.35:
                    return None

                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except Exception:
        pass
    return None

def scan_product_boxes(domain: str):
    urls = DIRECT_GIFT_URLS.get(domain, [f"https://{domain}/catalog/novogodnie_podarki/", f"https://{domain}/catalog/novogodnie-podarki/", f"https://{domain}/catalog/"])

    raw_items = []
    seen_imgs = set()

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Удаляем из поиска новости, статьи, шапку и подвал
        for junk in soup.find_all(["footer", "header", "nav", "aside"], class_=re.compile(r"news|blog|article|partner|brand|footer|header|slider", re.I)):
            junk.decompose()

        cards = soup.find_all(
            lambda t: t.name in ["div", "li", "article", "section"]
            and t.get("class")
            and any(
                c in " ".join(t.get("class")).lower()
                for c in ["product", "catalog-item", "card", "item", "goods", "element", "b-catalog", "catalog-element"]
            )
        )
        if not cards:
            cards = soup.find_all("img")

        for card in cards:
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

            src_low = src.lower()
            if any(bad in src_low for bad in JUNK_IMAGE_WORDS):
                continue

            full_img_url = fix_and_encode_url(url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # 1. ОТСЕКАЕМ НОВОСТИ И ЮР. МУСОР ПО НАЗВАНИЮ
            if any(bad in combined_text for bad in DOC_BLACKLIST):
                continue

            # 2. ОТСЕКАЕМ ТЕКСТИЛЬ, МЯГКИЕ ИГРУШКИ И КОФРЫ
            if any(bad in combined_text for bad in TEXTILE_AND_TOY_JUNK):
                continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img_url not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img_url)
                raw_items.append({"title": title, "weight": weight, "img_url": full_img_url})

    # Загружаем байты фото в многопоточном режиме
    validated = []
    def validate(p):
        info = download_product_image(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_items[:80]) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT (БЕЗОПАСНЫЙ СТАБИЛЬНЫЙ ВЫВОД)
# -----------------------------

company_input = st.text_input(
    "Введите название компании или адрес её сайта:",
    placeholder="Например: Коммунарка, Спартак, Рубин, Акконд, Лаконд, Рэйд 21, spartak.by, rubin-2000.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    domain = find_domain_dynamic(company_input)

    if domain:
        st.success(f"🌐 Официальный сайт подключен: `{domain}`")

        # ШАГ 1: ПОИСК PDF КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ)
        with st.spinner("ШАГ 1: Проверяем наличие PDF/Excel каталогов..."):
            documents = scan_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Скачайте полный официальный файл каталога ниже.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(f"### {icon} {doc['title']}")
                st.write(f"Ссылка: `{doc['url']}`")
                st.link_button("📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ", doc["url"])
                st.markdown("---")
        else:
            # ШАГ 2: ИЗВЛЕЧЕНИЕ ТОЛЬКО НОВОГОДНИХ ПОДАРКОВ И КОРOБОК
            with st.spinner("ШАГ 2: Извлекаем фотографии подарков и коробок из каталога..."):
                products = scan_product_boxes(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено новогодней упаковки и подарков: **{len(products)} шт.**")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products, start=1):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"gift_{i:02d}_{safe_name}.{prod['ext']}", prod["bytes"])

                st.download_button(
                    f"📦 СКАЧАТЬ ВСЕ {len(products)} ПОДАРКОВ В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_gifts_catalog.zip",
                    mime="application/zip",
                )

                st.markdown("---")
                
                # НАБОРНЫЙ СТАБИЛЬНЫЙ ВЫВОД КАРТОЧЕК БЕЗ REACT-ОШИБОК
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.image(prod["bytes"], use_container_width=True)
                        title_str = prod["title"][:55]
                        weight_str = f" | ⚖️ {prod['weight']}" if prod["weight"] else ""
                        st.caption(f"📦 {title_str}{weight_str}")
            else:
                st.error("На сайте в разделе новогодних подарков не удалось найти карточки товаров. Введите адрес напрямую (например, kommunarka.by, spartak.by или rubin-2000.ru).")
    else:
        st.error("Не удалось определить сайт. Введите адрес напрямую (например, kommunarka.by, spartak.by или rubin-2000.ru)")

st.divider()
st.caption(f"Инструмент компании «Первый Снег». Сезон {TARGET_YEAR}.")
