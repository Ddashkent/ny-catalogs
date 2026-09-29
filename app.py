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
    page_title="Первый Снег | Глобальный Навигатор Упаковки 2026",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

# СТАБИЛЬНЫЙ ДИЗАЙН (БЕЗ РИСКА РЕАКТ-ОШИБОК)
st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    
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

st.title(f"📦 Глобальный Экстрактор Упаковки {TARGET_YEAR}")
st.caption(
    "Глобальный поиск любых компаний. Автоматическое извлечение PDF-каталогов и карточек подарочной упаковки без юр. мусора."
)

# -----------------------------
# ФИЛЬТРЫ И МАРКЕРЫ
# -----------------------------

# БЛОКИРОВКА ПРЕЗЕНТАЦИЙ И ЮРИДИЧЕСКОГО МУСОРА (Стемминг)
DOC_STEM_BLACKLIST = [
    "презентац", "соглашени", "согласи", "политик", "конфиденциальн", 
    "персональн", "обработк", "договор", "оферт", "ваканси", "реквизит", 
    "cookies", "устав", "паспорт", "сертификат", "privacy", "agreement", "policy"
]

DOC_WHITELIST = ["каталог", "прайс", "price", "catalog", "подарки", "упаковка", "ассортимент"]

# СЛУЖЕБНЫЕ ИКОНКИ, БАННЕРЫ И ЛОГОТИПЫ ПАРТНЕРОВ
JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk",
    "партнер", "производ", "brand", "partner"
]

TEXTILE_AND_TOY_JUNK = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф"
]

CATALOG_URL_WORDS = [
    "catalog", "katalog", "podarki", "upakovka", "produk", "shop", "novogod", "present", "подарки", "каталог"
]

JUNK_DOMAINS = [
    "wikipedia.org", "otzovik", "avito", "checko", "list-org", "synapse", 
    "hh.ru", "rabota", "vk.com", "youtube", "instagram", "facebook", "google", "yandex"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ГЛОБАЛЬНЫЙ ДИНАМИЧЕСКИЙ ПОИСК
# -----------------------------

def normalize_domain_from_text(input_text: str) -> str:
    """Извлекает чистый домен из введенного текста или ссылки"""
    s = input_text.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return urllib.parse.urlparse(s).netloc.replace("www.", "")
    if "." in s and " " not in s:
        return s.split("/")[0].replace("www.", "")
    return None

def resolve_domain_globally(company_name: str) -> str:
    """Глобальный поиск официального сайта ЛЮБОЙ компании в сети"""
    # 1. Проверяем, ввели ли сразу адрес
    direct_dom = normalize_domain_from_text(company_name)
    if direct_dom:
        return direct_dom

    # 2. Глобальный динамический поиск через DDG HTML (безопасно и без вылетов)
    try:
        query_enc = urllib.parse.quote(f'"{company_name}" (кондитерская фабрика OR "новогодние подарки" OR "упаковка") официальный сайт')
        resp = requests.post("https://html.duckduckgo.com/html/", data={"q": query_enc}, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a["href"]).query).get("uddg", [a["href"]])[0]
                netloc = urllib.parse.urlparse(target).netloc.replace("www.", "")
                if netloc and not any(bad in netloc for bad in JUNK_DOMAINS):
                    return netloc
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
    if any(bad_path in url.lower() for bad_path in ["/news", "/novosti", "/press", "/blog", "/about"]):
        return None, None
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def discover_all_catalog_pages(domain: str):
    """Находит 100% разделов каталогов на ЛЮБОМ сайте"""
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    catalog_urls = [final_url]
    seen = {final_url}

    # 1. Поиск ссылок в меню
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        full_link = fix_and_encode_url(final_url, href)

        if full_link and domain in full_link:
            if not any(bad in full_link.lower() for bad in ["/news", "/about", "/contacts", "/delivery", "/payment"]):
                if any(kw in full_link.lower() or kw in text for kw in CATALOG_URL_WORDS):
                    clean_link = full_link.split("#")[0]
                    if clean_link not in seen:
                        seen.add(clean_link)
                        catalog_urls.append(clean_link)

    # 2. Стандартные путевые резервы
    standard_paths = [
        "/catalog/", "/katalog/", "/podarki/", "/novogodnie-podarki/", 
        "/catalog/novogodnie-podarki/", "/catalog/novyy_god/", "/products/", "/upakovka/"
    ]
    for path in standard_paths:
        test_url = f"https://{domain}{path}"
        if test_url not in seen:
            catalog_urls.append(test_url)

    return catalog_urls[:12]

# --- ШАГ 1: ГЛУБОКИЙ ПОИСК PDF / EXCEL КАТАЛОГОВ ---

def is_junk_document(text: str, url: str) -> bool:
    combined = f"{text} {url}".lower()
    return any(stem in combined for stem in DOC_STEM_BLACKLIST)

def scan_documents(catalog_urls: list):
    docs = []
    seen = set()

    def scan_page_docs(url):
        page_docs = []
        p_url, html = get_html(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip()
            title_attr = a.get("title", "").strip()
            full_link = fix_and_encode_url(p_url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                # ЗАБЛОКИРОВАТЬ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if is_junk_document(f"{text} {title_attr}", href):
                    continue

                doc_title = text or title_attr or a.parent.get_text().strip() or href.split("/")[-1]
                doc_title = re.sub(r"\s+", " ", doc_title).strip()

                page_docs.append({"title": doc_title or "Официальный каталог", "url": full_link})
        return page_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(scan_page_docs, catalog_urls[:6]):
            for d in res:
                if d["url"] not in seen:
                    seen.add(d["url"])
                    docs.append(d)

    return docs

# --- ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ И КОРOБОК ---

def download_product_image(img_url: str):
    """Загружает фото и проверяет геометрический формат коробок"""
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
                # Подарочные коробки: пропорции от 0.35 до 1.65 (все длинные баннеры отсекаются)
                if ratio > 1.68 or ratio < 0.35:
                    return None

                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except Exception:
        pass
    return None

def scan_product_boxes(catalog_urls: list, domain: str):
    # Добавляем пагинацию Битрикса (?PAGEN_1=2, ?PAGEN_1=3...)
    expanded_urls = set(catalog_urls)
    for u in catalog_urls:
        clean_base = u.split("?")[0]
        expanded_urls.add(f"{clean_base}?SHOWALL_1=1")
        for p_num in range(2, 6):
            expanded_urls.add(f"{clean_base}?PAGEN_1={p_num}")

    raw_items = []
    seen_imgs = set()

    def parse_single_page(page_url):
        p_items = []
        _, html = get_html(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Удаляем из поиска бренды, партнеров, шапку и подвал
        for junk in soup.find_all(
            ["footer", "header", "nav", "aside", "section", "div"],
            class_=re.compile(r"partner|brand|manufactur|vendor|client|footer|header|slider|carousel|banner|logo", re.I)
        ):
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

            src_low = src.lower()
            if any(bad in src_low for bad in JUNK_IMAGE_WORDS):
                continue

            full_img_url = fix_and_encode_url(page_url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Отсекаем юр. мусор, текстиль и мягкие игрушки
            if is_junk_document(combined_text, full_img_url):
                continue
            if any(bad in combined_text for bad in TEXTILE_AND_TOY_JUNK):
                continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img_url not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img_url)
                raw_items.append({"title": title, "weight": weight, "img_url": full_img_url})

        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_single_page, list(expanded_urls)[:12]):
            raw_items.extend(res)

    # Загружаем байты изображений в многопоточном режиме
    validated = []
    def validate(p):
        info = download_product_image(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_items) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название ЛЮБОЙ компании или адрес её сайта:",
    placeholder="Например: Академия Шоколада, Рубин, Акконд, Лаконд, Баян Сулу, chocolate-academy.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    input_text = company_input.strip()

    with st.spinner(f"Глобальный поиск официального сайта для '{input_text}'..."):
        domain = resolve_domain_globally(input_text)

    if domain:
        st.success(f"🌐 Официальный сайт найден и подключен: `{domain}`")

        # Находим все разделы каталогов на сайте
        with st.spinner("Сканируем структуру сайта и разделы каталога..."):
            catalog_urls = discover_catalog_urls(domain)

        # ШАГ 1: ПОИСК PDF / EXCEL КАТАЛОГОВ
        with st.spinner("ШАГ 1: Проверяем наличие PDF/Excel каталогов (без презентаций)..."):
            documents = scan_for_documents(catalog_urls)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Скачайте официальный каталог ниже.")
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
            # ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ И УПАКОВКИ СО ВСЕХ СТРАНИЦ КАТАЛОГА
            with st.spinner("ШАГ 2: Прямых PDF нет. Собираем карточки коробок со всех разделов каталога..."):
                products = scan_product_boxes(catalog_urls, domain)

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
                st.error("На сайте не удалось извлечь карточки товаров. Введите домен компании напрямую (например, chocolate-academy.ru).")
    else:
        st.error("Не удалось определить сайт. Введите адрес напрямую (например, chocolate-academy.ru, rubin-2000.ru, akkond.ru).")

st.divider()
st.caption(f"Универсальный инструмент коммерческого отдела «Первый Снег». Сезон {TARGET_YEAR}.")
