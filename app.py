import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Отключаем предупреждения SSL для серверов старого образца
requests.packages.urllib3.disable_warnings()

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# =========================================================
# ❄️ БРЕНДИНГ И СТИЛИЗАЦИЯ «ПЕРВЫЙ СНЕГ»
# =========================================================

st.set_page_config(
    page_title="Первый Снег | Каталоги и Упаковка 2026",
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
        display: inline-block; margin-top: 8px; transition: all 0.2s;
    }
    .btn-doc:hover { background-color: #b91c1c; }

    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        height: 100%; display: flex; flex-direction: column; justify-content: space-between;
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

st.title(f"📦 Экстрактор Новогодней Упаковки {TARGET_YEAR}")
st.caption(
    "Глубокий многопоточный анализ каталогов производителей ЕАЭС. Автоматический измеритель массы, очистка от рекламного мусора и сбор ZIP-архива."
)

# =========================================================
# 🎯 КАРТА КОНКУРЕНТОВ И РЕЕСТР
# =========================================================

SITE_MAP = {
    "рубин": "rubin-2000.ru",
    "rubin": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
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
    "миракс": "mirax-gifts.ru",
    "москондитер": "mosconditer.ru",
    "росшоколад": "roschocolate.ru",
}

DIRECT_START_URLS = {
    "rubin-2000.ru": "https://rubin-2000.ru/catalog/",
    "podarki-reid21.ru": "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
    "chocolate-academy.ru": "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
    "lakond.ru": "https://lakond.ru/products/",
    "kommunarka.by": "https://www.kommunarka.by/catalog/",
    "spartak.by": "https://spartak.by/catalog/",
}

# Исключения документов
JUNK_DOC_WORDS = [
    "презентация", "соглашение", "политика", "договор", "оферта", 
    "вакансии", "реквизиты", "cookies", "устав", "инвесторам", "соут", "privacy"
]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "2025", "2026", "2027", "2028", "catalog", "price"]

# Исключения картинок
JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk", "fb",
    "акконд", "бабаевск", "ротфронт", "красный_октябрь", "essen", "эссен", "славянк", "конти", "kdv", "header", "footer"
]

TEXTILE_AND_TOY_JUNK = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# =========================================================
# ⚙️ ТЕХНИЧЕСКИЙ СЕКТОР
# =========================================================

def build_http_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    session.verify = False
    retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

HTTP_SESSION = build_http_session()

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    for k, domain in SITE_MAP.items():
        if k in v:
            return domain
    if "." in v and " " not in v:
        clean = v.replace("https://", "").replace("http://", "").split("/")[0]
        return clean.replace("www.", "")
    # Транслитерация для новых названий
    char_map = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    slug = "".join(char_map.get(c, c) for c in v if c.isalnum() or c.isspace()).replace(" ", "-")
    return f"{slug}.ru" if slug else "rubin-2000.ru"

def fix_and_encode_url(base_url: str, src: str) -> str:
    """Исправляет ссылки с кириллицей и пробелами"""
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    safe_query = urllib.parse.quote(parsed.query, safe="=&?+")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, safe_query, parsed.fragment))

def get_html(url: str):
    try:
        res = HTTP_SESSION.get(url, timeout=12)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding or "utf-8"
            return res.url, res.text
    except Exception:
        pass
    return None, None

# =========================================================
# 📄 ШАГ 1: ИЗВЛЕЧЕНИЕ ОФИЦИАЛЬНЫХ КАТАЛОГОВ (PDF / EXCEL)
# =========================================================

def scan_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/", f"{base}/novogodnie-podarki/"]
    if domain in DIRECT_START_URLS:
        urls.insert(0, DIRECT_START_URLS[domain])

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
                # Исключаем юридический и презентационный мусор
                if any(bad in combined for bad in JUNK_DOC_WORDS):
                    continue
                # Требуем целевые ключевые слова
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({
                            "title": a.get_text().strip() or f"Официальный каталог {TARGET_YEAR}",
                            "url": full_link
                        })
    return docs

# =========================================================
# 📦 ШАГ 2: КРАУЛИНГ ПАГИНАЦИИ И ИЗВЛЕЧЕНИЕ ТОВАРОВ
# =========================================================

def find_all_pagination_pages(domain: str, start_url: str):
    """Собирает ссылки на категории и страницы пагинации"""
    pages = [start_url]
    seen = {start_url}

    _, html = get_html(start_url)
    if not html:
        return pages

    soup = BeautifulSoup(html, "html.parser")

    # 1. Поиск ссылок пагинации и категорий
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text().strip()
        full_url = fix_and_encode_url(start_url, href)

        if domain in full_url:
            href_low = href.lower()
            if any(p in href_low for p in ["pagen", "page", "p=", "pg=", "catalog", "upakovka", "podarki"]) or text.isdigit():
                if full_url not in seen and not full_url.endswith(".pdf"):
                    seen.add(full_url)
                    pages.append(full_url)

    # 2. Авто-генерация пагинации Bitrix, если ссылки сокрыты
    if len(pages) <= 2:
        for p_num in range(2, 8):
            p_url = f"{start_url}?PAGEN_1={p_num}"
            if p_url not in seen:
                seen.add(p_url)
                pages.append(p_url)

    return pages[:30] # Ограничение глубины сканирования

def download_image_bytes(img_url: str):
    """Загрузка изображения, валидация через PIL и проверка пропорций"""
    try:
        res = HTTP_SESSION.get(img_url, timeout=7)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                try:
                    img = Image.open(io.BytesIO(res.content))
                    w, h = img.size
                    if w < 100 or h < 120:
                        return None
                    ratio = w / h
                    # Отсекаем длинные баннеры (пропорции коробки обычно 0.35..1.65)
                    if ratio > 1.65 or ratio < 0.35:
                        return None
                    ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
                except Exception:
                    ext = "jpg"
            else:
                ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except Exception:
        pass
    return None

def scan_all_products_with_pagination(domain: str):
    start_url = DIRECT_START_URLS.get(domain, f"https://{domain}/catalog/")
    
    # 1. Поиск всех страниц
    all_pages = find_all_pagination_pages(domain, start_url)
    
    raw_items = []
    seen_imgs = set()

    # 2. Парсинг каждой страницы
    def parse_single_page(page_url):
        p_items = []
        _, html = get_html(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Удаление служебных блоков
        for junk in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"partner|brand|footer|header|slider|menu", re.I)):
            junk.decompose()

        # Поиск элементов карточек
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

    # Сканирование страниц в 6 потоков
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_single_page, all_pages):
            raw_items.extend(res)

    # 3. Загрузка байтов изображений в 10 потоков
    def validate_and_download(item):
        info = download_image_bytes(item["img_url"])
        if info:
            item["bytes"] = info["bytes"]
            item["ext"] = info["ext"]
            return item
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        validated = [r for r in executor.map(validate_and_download, raw_items) if r is not None]

    return validated

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

company_input = st.text_input(
    "Введите название компании или адрес сайта:",
    placeholder="Например: Рубин, РУБИН, Спартак, Коммунарка, Лаконд, Акконд, rubin-2000.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.warning("Пожалуйста, введите название компании или URL.")
        st.stop()

    domain = normalize_domain(company_input)

    if domain:
        st.success(f"🌐 Подключен целевой сайт: `{domain}`")

        # ШАГ 1: Поиск официальных документов
        with st.spinner("ШАГ 1: Сканируем сайт на наличие PDF/Excel каталогов..."):
            documents = scan_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Нажмите кнопку ниже для скачивания официального файла каталога.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">URL: {doc['url']}</small><br>
                        <a href="{doc['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        
        # ШАГ 2: Извлечение товаров
        with st.spinner("ШАГ 2: Сканируем категории и загружаем изображения карточек..."):
            products = scan_all_products_with_pagination(domain)

        st.markdown("---")
        if products:
            st.success(f"Успешно выгружено карточек товаров и упаковки: **{len(products)} шт.**")

            # Формирование ZIP-архива
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, prod in enumerate(products, start=1):
                    safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:35].strip()
                    filename = f"box_{i:03d}_{safe_name or 'item'}.{prod['ext']}"
                    zf.writestr(filename, prod["bytes"])

            st.download_button(
                f"📦 СКАЧАТЬ ВСЕ {len(products)} КАРТОЧЕК В ZIP-АРХИВЕ",
                data=zip_buffer.getvalue(),
                file_name=f"{domain}_packaging_{TARGET_YEAR}.zip",
                mime="application/zip",
                type="primary"
            )

            st.markdown("---")

            # Отображение карточек через скачанные байты
            cols = st.columns(4)
            for idx, prod in enumerate(products):
                with cols[idx % 4]:
                    st.markdown(
                        f"""
                        <div class="product-card">
                            <div class="product-title">{prod['title']}</div>
                            <div>
                                <span class="badge-cardboard">📦 КАРТОН / УПАКОВКА</span>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )
                    st.image(prod["bytes"], use_container_width=True)
        else:
            if not documents:
                st.error(f"На сайте `{domain}` не удалось обнаружить элементы каталога или упаковки.")
    else:
        st.error("Не удалось определить домен. Введите адрес напрямую (например, rubin-2000.ru).")

st.divider()
st.caption(f"Инструмент «Первый Снег» | Сезон {TARGET_YEAR} | Автоматизированный анализ ЕАЭС.")
