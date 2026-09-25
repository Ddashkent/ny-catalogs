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
    page_title="Первый Снег | Полный Каталог Упаковки 2026",
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

st.title(f"📦 Полный Экстрактор Упаковки {TARGET_YEAR}")
st.caption(
    "Двухуровневый сканер продукции: находит новогодние разделы внутри меню 'Продукция' и выгружает 100% коробок."
)

# -----------------------------
# БАЗА ЗНАНИЙ И ПРЯМЫЕ ПУТИ
# -----------------------------

SITE_MAP = {
    "акконд": "akkond.ru",
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
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
    "рэйд": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "рот фронт": "uniconf.ru",
    "бабаевский": "uniconf.ru",
}

DIRECT_START_URLS = {
    "akkond.ru": "https://akkond.ru/catalog/novogodnie-podarki/",
    "rubin-2000.ru": "https://rubin-2000.ru/catalog/",
    "podarki-reid21.ru": "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
    "chocolate-academy.ru": "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
    "lakond.ru": "https://lakond.ru/products/",
}

# ЖЕСТКИЙ БЛОК ПРЕЗЕНТАЦИЙ И ЮР. МУСОРА
JUNK_DOC_WORDS = [
    "презентация", "соглашение", "политика", "договор", "оферта", 
    "вакансии", "реквизиты", "cookies", "устав", "инвесторам"
]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "2027", "catalog", "price"]

JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk",
    "бабаевск", "ротфронт", "красный_октябрь", "essen", "эссен", "конти", "kdv"
]

TEXTILE_AND_TOY_JUNK = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок"
]

# Ключевые слова первого уровня (где искать каталоги)
PRODUCT_MENU_WORDS = ["продукц", "catalog", "katalog", "продукты", "ассортимент", "shop", "товары"]

# Ключевые слова целевого сезона/новогоднего раздела
NEW_YEAR_TARGET_WORDS = ["новогод", "подар", "нг", "newyear", "gift", "2026", "2025", "2027", "праздник"]

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
    return "akkond.ru"

def fix_and_encode_url(base_url: str, src: str) -> str:
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment))

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=9, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

# --- ДВУХУРОВНЕВЫЙ ДИНАМИЧЕСКИЙ СКАКАТЕЛЬ ПО МЕНЮ ПРОДУКЦИИ ---

def discover_new_year_categories(domain: str):
    """
    Сканирует 'Продукцию' и находит глубоко спрятанные разделы 'Новый год / Подарки'
    """
    base_url = f"https://{domain}"
    
    # Стартовые точки
    start_urls = [base_url]
    if domain in DIRECT_START_URLS:
        start_urls.insert(0, DIRECT_START_URLS[domain])

    target_category_urls = set(start_urls)

    # 1. Заходим на главную и ищем разделы "Продукция" / "Каталог"
    _, main_html = get_html(base_url)
    if main_html:
        soup_main = BeautifulSoup(main_html, "html.parser")
        
        # Находим ссылки уровня "Продукция"
        product_menu_links = []
        for a in soup_main.find_all("a", href=True):
            href = a["href"].strip().lower()
            text = a.get_text(" ", strip=True).lower()
            full_link = fix_and_encode_url(base_url, a["href"])

            if domain in full_link:
                # Если в ссылке прямо сказано "Новый год" — берем сразу!
                if any(ny in text or ny in href for ny in NEW_YEAR_TARGET_WORDS):
                    target_category_urls.add(full_link)
                # Если ссылка ведет в раздел "Продукция" — заносим для проверки 2-го уровня
                elif any(pm in text or pm in href for cw in PRODUCT_MENU_WORDS for pm in [cw]):
                    if full_link not in product_menu_links and len(product_menu_links) < 5:
                        product_menu_links.append(full_link)

        # 2. Переходим внутрь найденных разделов "Продукция" и ищем подразделы "Новый год"
        for prod_link in product_menu_links:
            _, prod_html = get_html(prod_link)
            if prod_html:
                soup_prod = BeautifulSoup(prod_html, "html.parser")
                for a_sub in soup_prod.find_all("a", href=True):
                    sub_href = a_sub["href"].strip().lower()
                    sub_text = a_sub.get_text(" ", strip=True).lower()
                    full_sub_link = fix_and_encode_url(prod_link, a_sub["href"])

                    if domain in full_sub_link:
                        if any(ny in sub_text or ny in sub_href for ny in NEW_YEAR_TARGET_WORDS):
                            target_category_urls.add(full_sub_link)

    return list(target_category_urls)

# --- ШАГ 1: ПОИСК НАСТОЯЩИХ КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ) ---

def scan_documents(domain: str):
    docs, seen = [], set()
    urls = discover_new_year_categories(domain)

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
                if any(bad in combined for bad in JUNK_DOC_WORDS):
                    continue
                # 2. ТРЕБОВАТЬ СЛОВА КАТАЛОГ ИЛИ ПРАЙС
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

# --- ШАГ 2: СБОР ВСЕХ КАРТОЧЕК С ТАРГЕТНЫХ СТРАНИЦ ---

def find_all_pagination_pages(domain: str, category_urls: list):
    """Находит все страницы пагинации внутри новогодних категорий"""
    all_pages = set(category_urls)

    for cat_url in category_urls:
        _, html = get_html(cat_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text().strip()
            full_url = fix_and_encode_url(cat_url, href)

            if domain in full_url:
                if any(p in href.lower() for p in ["pagen", "page", "p=", "pg="]) or text.isdigit():
                    all_pages.add(full_url)

        # Авто-генерация страниц для Bitrix (если не распознались явные кнопки)
        if "akkond.ru" in domain or "rubin-2000.ru" in domain:
            for p_num in range(2, 6):
                all_pages.add(f"{cat_url}?PAGEN_1={p_num}")

    return list(all_pages)

def download_image_bytes(img_url: str):
    """Качает картинку в высоком качестве и проверяет геометрию"""
    try:
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

def scan_all_products_with_pagination(domain: str):
    # 1. Находим целевые категории "Новый год" (включая путь через "Продукцию")
    category_urls = discover_new_year_categories(domain)
    
    # 2. Раскрываем пагинацию
    all_pages = find_all_pagination_pages(domain, category_urls)
    
    raw_items = []
    seen_imgs = set()

    def parse_single_page(page_url):
        p_items = []
        _, html = get_html(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Исключаем служебные подвалы и шапки
        for junk in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"partner|brand|footer|header|slider", re.I)):
            junk.decompose()

        cards = soup.find_all(
            lambda t: t.name in ["div", "li", "article", "section"]
            and t.get("class")
            and any(
                c in " ".join(t.get("class")).lower()
                for c in ["product", "catalog-item", "card", "item", "goods", "element", "b-catalog"]
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

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            if any(bad in combined_text for bad in JUNK_IMAGE_WORDS + TEXTILE_AND_TOY_JUNK):
                continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img_url not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img_url)
                p_items.append({"title": title, "weight": weight, "img_url": full_img_url})

        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_single_page, all_pages):
            raw_items.extend(res)

    # 3. Скачиваем байты изображений в высоком качестве
    validated = []
    def validate_and_download(p):
        info = download_image_bytes(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        validated = [r for r in executor.map(validate_and_download, raw_items) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название компании или адрес её сайта:",
    placeholder="Например: Акконд, Рубин, Рэйд 21, Лаконд, akkond.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    domain = normalize_domain(company_input)

    if domain:
        st.success(f"🌐 Официальный сайт подключен: `{domain}`")

        # ШАГ 1: ПОИСК НАСТОЯЩИХ PDF КАТАЛОГОВ
        with st.spinner("ШАГ 1: Сканируем сайт на наличие PDF/Excel каталогов..."):
            documents = scan_documents(domain)

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
            # ШАГ 2: АВТО-ОБНАРУЖЕНИЕ РАЗДЕЛОВ "НОВЫЙ ГОД" ВНУТРИ "ПРОДУКЦИИ" И СБОР КАРТОЧЕК
            with st.spinner("ШАГ 2: Анализируем меню 'Продукция', находим новогодний раздел и выгружаем коробки..."):
                products = scan_all_products_with_pagination(domain)

            st.markdown("---")
            if products:
                st.success(f"Успешно обработано карточек новогодней упаковки и подарков: **{len(products)} шт.**")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products, start=1):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"box_{i:02d}_{safe_name}.{prod['ext']}", prod["bytes"])

                st.download_button(
                    f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_boxes_catalog.zip",
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
                                <span class="badge-cardboard">📦 КАРТОН / УПАКОВКА</span>
                                {f'<br><span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.image(prod["bytes"], use_container_width=True)
            else:
                st.error("На сайте не удалось выгрузить карточки товаров.")
    else:
        st.error("Не удалось определить сайт. Введите адрес напрямую (например, akkond.ru)")

st.divider()
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Двухуровневое сканирование разделов 'Продукция'.")
