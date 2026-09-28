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
    page_title="Первый Снег | Отраслевой Навигатор 2026",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
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
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .badge-weight {
        background-color: #dc2626; color: white; font-weight: bold;
        padding: 3px 10px; font-size: 11px; border-radius: 12px;
        display: inline-block; margin-top: 4px;
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-top: 4px; margin-right: 4px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snowflake s1">❄</div><div class="snowflake s2">❅</div>
    <div class="snowflake s3">❆</div><div class="snowflake s4">❄</div>
""",
    unsafe_allow_html=True,
)

st.title(f"📦 Экстрактор Сладких Подарков & Упаковки {TARGET_YEAR}")
st.caption(
    "Узкоотраслевой поиск: Кондитерские фабрики, фасовщики подарков и оптовики сладостей. Спорт, новости и сторонний бизнес отсекаются."
)

# -----------------------------
# ОТРАСЛЕВЫЕ МАРКЕРЫ И ЧЕРНЫЙ СПИСОК
# -----------------------------

# БЛОКИРОВКА СПОРТА, ФУТБОЛЬНЫХ КЛУБОВ И НЕПРОФИЛЬНЫХ САЙТОВ
SPORTS_AND_NON_FOOD_BLACKLIST = [
    "футбол", "футбольный", "fc", "клуб", "матч", "чемпионат", "стадион", 
    "тренер", "турнир", "лига", "спартакиада", "спорт", "команда", "трансфер",
    "fcsmaprtak", "spartak.com", "sports.ru", "championat", "matchtv"
]

# ОБЯЗАТЕЛЬНЫЕ ОТРAСЛЕВЫЕ МАРКЕРЫ (Сладости, Подарки, Упаковка, Фасовка)
INDUSTRY_WHITE_WORDS = [
    "конфет", "сладост", "кондитерск", "фабрика", "подарк", "упаковк", 
    "фасовк", "шоколад", "набор", "коробк", "тубус", "картон"
]

# БЛОКИРОВКА ПРЕЗЕНТАЦИЙ И ЮРИДИЧЕСКОГО МУСОРА
EXCLUDE_DOC_WORDS = [
    "презентаци", "соглашени", "политик", "конфиденциальн", "персональн", 
    "договор", "оферт", "устав", "реквизит", "ваканси", "privacy", "agreement", "cookies"
]

# ИСКЛЮЧАЕМ ТЕКСТИЛЬ, МЯГКУЮ ИГРУШКУ И БАННЕРЫ
JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk",
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    if "спартак" in v:
        return "spartak.by" # Кондитерская фабрика Спартак (Гомель)
    if "рэйд" in v or "reid" in v:
        return "podarki-reid21.ru"
    if "." in v and " " not in v:
        return v.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def resolve_confectionery_domain(company_name: str) -> str:
    """Узкоотраслевой поиск сайта кондитерских фабрик и фасовщиков"""
    q_low = company_name.lower().strip()
    
    # 1. Точечные проверки известных совпадений
    if "спартак" in q_low:
        return "spartak.by"
    
    direct_dom = normalize_domain(company_name)
    if direct_dom:
        return direct_dom

    # 2. Строгий отраслевой поисковый запрос (исключаем футбол и спорт)
    try:
        from duckduckgo_search import DDGS
        query = f'"{company_name}" (кондитерская фабрика OR "новогодние подарки" OR "упаковка подарков") -футбол -клуб -спорт'
        with DDGS() as ddgs:
            res = list(ddgs.text(query, region="ru-ru", max_results=6))
            for r in res:
                link = r.get("href", "")
                title = r.get("title", "").lower()
                snippet = r.get("body", "").lower()
                
                # Проверка: сайт не должен быть спортивным
                if not any(bad in link.lower() or bad in title or bad in snippet for bad in SPORTS_AND_NON_FOOD_BLACKLIST):
                    # Сайт должен относиться к сладостям или подаркам
                    if any(good in title or good in snippet for good in INDUSTRY_WHITE_WORDS):
                        parsed = urllib.parse.urlparse(link)
                        return parsed.netloc.replace("www.", "")
    except Exception:
        pass

    return None

def fix_and_encode_url(base_url: str, src: str) -> str:
    if not src:
        return None
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment))

def get_html(url: str):
    # Пропускаем спортивные и служебные разделы
    if any(bad in url.lower() for bad in SPORTS_AND_NON_FOOD_BLACKLIST + ["/news", "/blog", "/about"]):
        return None, None
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

# --- ШАГ 1: ПОИСК PDF/EXCEL КАТАЛОГОВ ---

def scan_for_documents(domain: str):
    docs, seen = [], set()
    
    # Прямые продуктовые пути
    urls = [
        f"https://{domain}", 
        f"https://{domain}/catalog/", 
        f"https://{domain}/podarki/", 
        f"https://{domain}/novogodnie-podarki/",
        f"https://{domain}/catalog/novogodnie-podarki/",
        f"https://{domain}/catalog/novyy_god/"
    ]

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
                # БЛОКИРУЕМ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if any(bad in combined for bad in EXCLUDE_DOC_WORDS):
                    continue
                # ТРЕБУЕМ КАТАЛОГ ИЛИ ПРАЙС
                if any(good in combined for good in ["каталог", "прайс", "подарки", "2026", "2025", "catalog", "price"]):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

# --- ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ И УПАКОВКИ ---

def download_and_validate_image(img_url: str):
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 120 or h < 120:
                    return None
                ratio = w / h
                if ratio > 1.65 or ratio < 0.35:
                    return None
                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except Exception:
        pass
    return None

def parse_confectionery_products(domain: str):
    urls = [
        f"https://{domain}/catalog/novogodnie-podarki/",
        f"https://{domain}/catalog/novyy_god/",
        f"https://{domain}/catalog/",
        f"https://{domain}/podarki/",
        f"https://{domain}/products/",
        f"https://{domain}"
    ]

    raw_products = []
    seen_imgs = set()

    for page_url in urls:
        _, html = get_html(page_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Удаляем служебные блоки
        for junk in soup.find_all(["footer", "header", "nav", "aside"], class_=re.compile(r"footer|header|slider|partner|brand", re.I)):
            junk.decompose()

        cards = soup.find_all(
            lambda t: t.name in ["div", "li", "article", "section"]
            and t.get("class")
            and any(
                c in " ".join(t.get("class")).lower()
                for c in ["product", "catalog-item", "card", "item", "goods", "element"]
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

            if any(bad in src.lower() for bad in JUNK_IMAGE_WORDS):
                continue

            full_img_url = fix_and_encode_url(page_url, src)
            if not full_img_url or full_img_url in seen_imgs:
                continue

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Исключаем текстиль, игрушки и футбол
            if any(bad in combined_text for bad in JUNK_IMAGE_WORDS + SPORTS_AND_NON_FOOD_BLACKLIST):
                continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if len(title) > 2:
                seen_imgs.add(full_img_url)
                raw_products.append({"title": title, "weight": weight, "img_url": full_img_url})

    # Многопоточная выкачка
    validated = []
    def validate(p):
        info = download_and_validate_image(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_products[:80]) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название кондитерской фабрики, фасовщика или адрес сайта:",
    placeholder="Например: Спартак, Акконд, Рубин, Академия шоколада, Лаконд, spartak.by...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    input_text = company_input.strip()

    with st.spinner(f"Ищем сайт в сфере сладких подарков и упаковки для '{input_text}'..."):
        domain = resolve_confectionery_domain(input_text)

    if domain:
        st.success(f"🌐 Официальный сайт кондитерской фабрики/поставщика: `{domain}`")

        # ШАГ 1: ПОИСК PDF / EXCEL КАТАЛОГОВ
        with st.spinner("ШАГ 1: Проверяем наличие официальных PDF/Excel каталогов..."):
            documents = scan_for_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Скачайте полный официальный файл каталога ниже.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">Ссылка: {doc['url']}</small><br>
                        <a href="{doc['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            # ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ И УПАКОВКИ
            with st.spinner("ШАГ 2: Прямых PDF нет. Извлекаем карточки подарков и коробок с сайта..."):
                products = parse_confectionery_products(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено карточек упаковки и подарков: **{len(products)} шт.**")

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
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(
                            f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                <span class="badge-cardboard">📦 НОВОГОДНИЙ ПОДАРОК</span>
                                {f'<br><span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.image(prod["bytes"], use_container_width=True)
            else:
                st.error("На сайте в разделе сладких подарков не удалось извлечь карточки товаров.")
    else:
        st.error("Не удалось найти сайт в сфере кондитерских изделий и подарков. Введите адрес напрямую (например, spartak.by)")

st.divider()
st.caption(f"Узкоотраслевой инструмент компании «Первый Снег». Сезон {TARGET_YEAR}. Спорт и непрофильный бизнес отфильтрованы.")
