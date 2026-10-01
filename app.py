import concurrent.futures
import io
import re
import ssl
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# Отключаем предупреждения об SSL
requests.packages.urllib3.disable_warnings()

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# =========================================================
# ❄️ ДИЗАЙН И БРЕНДИНГ «ПЕРВЫЙ СНЕГ»
# =========================================================

st.set_page_config(
    page_title="Первый Снег | Каталоги Наборов и Упаковки 2026",
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
    }
    .badge-weight {
        background-color: #dc2626; color: white; font-weight: bold;
        padding: 3px 10px; font-size: 11px; border-radius: 12px;
        display: inline-block; margin-top: 4px;
    }
    .badge-box {
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

st.title(f"📦 Поиск Новогодних Наборов и Упаковки {TARGET_YEAR}")
st.caption(
    "Специализированный экстрактор подарков, наборов и упаковки по производителям ЕАЭС. Одиночные конфеты автоматически отсеиваются."
)

# =========================================================
# 🛠 СЕТЕВОЙ АДАПТЕР С ПОДДЕРЖКОЙ СТАРОГО SSL (РБ И РК)
# =========================================================

class CustomSSLAdapter(HTTPAdapter):
    """Адаптер для корректного подсоединения к серверам РБ и РК с нетиповым SSL"""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers('DEFAULT:@SECLEVEL=1')
        except Exception:
            pass
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

def build_smart_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    session.verify = False
    adapter = CustomSSLAdapter(max_retries=2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

HTTP_SESSION = build_smart_session()

def smart_fetch(url: str):
    """Загрузка страницы с автоперебором прописных протоколов и префиксов www"""
    urls_to_try = [url]
    
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path.split('/')[0]
    path = parsed.path if parsed.netloc else "/" + "/".join(parsed.path.split('/')[1:])
    
    # Генерируем варианты (HTTPS/HTTP, www/без www)
    clean_netloc = netloc.replace("www.", "")
    urls_to_try.extend([
        f"https://{clean_netloc}{path}",
        f"https://www.{clean_netloc}{path}",
        f"http://{clean_netloc}{path}",
        f"http://www.{clean_netloc}{path}",
    ])
    
    seen = set()
    for target in urls_to_try:
        if target in seen:
            continue
        seen.add(target)
        try:
            res = HTTP_SESSION.get(target, timeout=12)
            if res.status_code == 200 and len(res.text) > 500:
                res.encoding = res.apparent_encoding or "utf-8"
                return res.url, res.text
        except Exception:
            continue
            
    return None, None

# =========================================================
# 🎯 КАРТА САЙТОВ И СЛОВАРЬ ФИЛЬТРАЦИИ
# =========================================================

SITE_MAP = {
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "славянка": "slavyanka.ru",
    "рэйд": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
}

DIRECT_START_URLS = {
    "kommunarka.by": "https://www.kommunarka.by/catalog/novogodnie-podarki/",
    "spartak.by": "https://spartak.by/catalog/novogodnyaya-produktsiya/",
    "rakhat.kz": "https://rakhat.kz/products/novogodnie-podarki/",
    "bayansulu.kz": "https://www.bayansulu.kz/ru/catalog/",
    "rubin-2000.ru": "https://rubin-2000.ru/catalog/",
    "podarki-reid21.ru": "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/",
    "chocolate-academy.ru": "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
}

# 1. ОБЯЗАТЕЛЬНЫЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ НАБОРОВ И УПАКОВКИ
BOX_SET_KEYWORDS = [
    "набор", "подарок", "подарки", "упаковк", "коробк", "туб", "тубус",
    "сундуч", "домик", "книг", "футляр", "баульч", "пакет", "шкатулк",
    "символ", "гофр", "мгк", "картон", "жесть", "сапожок", "ведро", "баул",
    "комплект", "состав подарка", "сладкий подарок"
]

# 2. СЛОВА ОДИНОЧНЫХ КОНФЕТ (УДАЛЯЕМ, ЕСЛИ НЕТ КЛЮЧЕВЫХ СЛОВ НАБОРА/УПАКОВКИ)
SINGLE_CANDY_KEYWORDS = [
    "конфета", "конфеты весовые", "батончик", "шоколадка", "плитка шоколада",
    "драже", "карамелька", "вафля", "вафли", "печенье", "зефир", "ирис",
    "мармелад весовой", "поштучно"
]

JUNK_DOC_WORDS = [
    "презентация", "соглашение", "политика", "договор", "оферта", 
    "вакансии", "реквизиты", "cookies", "устав", "инвесторам", "соут", "privacy"
]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "2025", "2026", "2027", "2028", "catalog", "price"]

JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk", "fb",
    "header", "footer", "menu", "sprite"
]

WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# =========================================================
# ⚙️ ФУНКЦИИ ФИЛЬТРАЦИИ И ПОДГОТОВКИ
# =========================================================

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    for k, domain in SITE_MAP.items():
        if k in v:
            return domain
    if "." in v and " " not in v:
        clean = v.replace("https://", "").replace("http://", "").split("/")[0]
        return clean.replace("www.", "")
    return "kommunarka.by" if "коммун" in v else "rubin-2000.ru"

def fix_and_encode_url(base_url: str, src: str) -> str:
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    safe_query = urllib.parse.quote(parsed.query, safe="=&?+")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, safe_query, parsed.fragment))

def is_box_or_set(title_text: str, context_url: str) -> bool:
    """Жесткая проверка: оставляем ТОЛЬКО наборы, коробки и подарки."""
    combined = f"{title_text} {context_url}".lower()
    
    # Если есть явные признаки одиночной конфеты и НЕТ слов набора/упаковки -> отбрасываем
    has_single_sweet = any(sweet in combined for sweet in SINGLE_CANDY_KEYWORDS)
    has_box_indicator = any(box in combined for box in BOX_SET_KEYWORDS)
    
    if has_single_sweet and not has_box_indicator:
        return False
        
    return has_box_indicator or "podar" in context_url.lower() or "novogod" in context_url.lower()

# =========================================================
# 📄 ШАГ 1: ПОИСК PDF / EXCEL КАТАЛОГОВ
# =========================================================

def scan_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/"]
    if domain in DIRECT_START_URLS:
        urls.insert(0, DIRECT_START_URLS[domain])

    for url in urls:
        _, html = smart_fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip().lower()
            full_link = fix_and_encode_url(url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                if any(bad in combined for bad in JUNK_DOC_WORDS):
                    continue
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({
                            "title": a.get_text().strip() or f"Официальный каталог {TARGET_YEAR}",
                            "url": full_link
                        })
    return docs

# =========================================================
# 📦 ШАГ 2: ИЗВЛЕЧЕНИЕ КАРТОЧЕК НАБОРОВ И УПАКОВКИ
# =========================================================

def find_all_pagination_pages(domain: str, start_url: str):
    pages = [start_url]
    seen = {start_url}

    real_start_url, html = smart_fetch(start_url)
    if not html:
        return pages

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text().strip()
        full_url = fix_and_encode_url(real_start_url, href)

        if domain in full_url:
            href_low = href.lower()
            if any(p in href_low for p in ["pagen", "page", "p=", "pg=", "catalog", "podarki", "novogod"]) or text.isdigit():
                if full_url not in seen and not full_url.endswith(".pdf"):
                    seen.add(full_url)
                    pages.append(full_url)

    if len(pages) <= 2:
        for p_num in range(2, 8):
            p_url = f"{real_start_url}?PAGEN_1={p_num}"
            if p_url not in seen:
                seen.add(p_url)
                pages.append(p_url)

    return pages[:30]

def download_image_bytes(img_url: str):
    try:
        _, content_or_text = smart_fetch(img_url)
        # Если качаем бинарник через requests
        res = HTTP_SESSION.get(img_url, timeout=8)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                try:
                    img = Image.open(io.BytesIO(res.content))
                    w, h = img.size
                    if w < 100 or h < 100:
                        return None
                    ratio = w / h
                    if ratio > 1.85 or ratio < 0.35:
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
    all_pages = find_all_pagination_pages(domain, start_url)
    
    raw_items = []
    seen_imgs = set()

    def parse_single_page(page_url):
        p_items = []
        real_page_url, html = smart_fetch(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        for junk in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"partner|brand|footer|header|slider|menu", re.I)):
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

            full_img_url = fix_and_encode_url(real_page_url or page_url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            title = img.get("alt") or img.get("title") or text[:70]
            title = re.sub(r"\s+", " ", title).strip()

            # ФИЛЬТРАЦИЯ: Оставляем ТОЛЬКО Наборы / Подарки / Упаковку
            if not is_box_or_set(title + " " + text, full_img_url):
                continue

            weight_match = WEIGHT_REGEX.search(text + " " + title)
            weight = weight_match.group(1) if weight_match else None

            if full_img_url not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img_url)
                p_items.append({"title": title, "weight": weight, "img_url": full_img_url})

        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_single_page, all_pages):
            raw_items.extend(res)

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
    placeholder="Например: Коммунарка, Спартак, Рахат, Рубин, Акконд, Лаконд, kommunarka.by...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.warning("Пожалуйста, введите название компании или URL.")
        st.stop()

    domain = normalize_domain(company_input)

    if domain:
        st.success(f"🌐 Целевой домен системы: `{domain}`")

        # ШАГ 1: Поиск официальных PDF каталогов
        with st.spinner("ШАГ 1: Проверка наличия PDF / Excel каталогов..."):
            documents = scan_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">URL: {doc['url']}</small><br>
                        <a href="{doc['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ КАТАЛОГ</a>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        
        # ШАГ 2: Извлечение наборов и упаковки
        with st.spinner("ШАГ 2: Извлечение подарочных наборов и коробок со всех страниц..."):
            products = scan_all_products_with_pagination(domain)

        st.markdown("---")
        if products:
            st.success(f"Успешно выгружено подарочных наборов и вариантов упаковки: **{len(products)} шт.**")

            # Формирование ZIP-архива
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, prod in enumerate(products, start=1):
                    safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:35].strip()
                    filename = f"gift_box_{i:03d}_{safe_name or 'item'}.{prod['ext']}"
                    zf.writestr(filename, prod["bytes"])

            st.download_button(
                f"📦 СКАЧАТЬ ВСЕ {len(products)} НАБОРОВ В ZIP-АРХИВЕ",
                data=zip_buffer.getvalue(),
                file_name=f"{domain}_gift_boxes_{TARGET_YEAR}.zip",
                mime="application/zip",
                type="primary"
            )

            st.markdown("---")

            # Галерея
            cols = st.columns(4)
            for idx, prod in enumerate(products):
                with cols[idx % 4]:
                    st.markdown(
                        f"""
                        <div class="product-card">
                            <div class="product-title">{prod['title']}</div>
                            <div>
                                <span class="badge-box">🎁 НАБОР / УПАКОВКА</span>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )
                    st.image(prod["bytes"], use_container_width=True)
        else:
            if not documents:
                st.error(f"На сайте `{domain}` не удалось обнаружить подарочные наборы или официальные PDF.")
    else:
        st.error("Не удалось определить домен. Введите корректный адрес.")

st.divider()
st.caption(f"Инструмент «Первый Снег» | Сезон {TARGET_YEAR} | Фильтрация одиночных конфет активна.")
