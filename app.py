import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import urllib3
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

# Безопасное отключение предупреждений SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Экстрактор Упаковки 2026",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

# Красно-белый логотип + Нежный медленный снег
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

st.title(f"📦 Анализ Новогодней Упаковки {TARGET_YEAR}")
st.caption("Приоритет: Официальные каталоги PDF/Excel. Автоматический сбор коробок без презентаций, новостей и юр. мусора.")

# -----------------------------
# КАРТА САЙТОВ И ТОЧНЫЕ АДРЕСА
# -----------------------------

SITE_MAP = {
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
    "коммунарка": "kommunarka.by",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "баянсулу": "bayansulu.kz",
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "рейд": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "саратовская кф": "confashion.ru",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
    "победа": "pobeda.market",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "рот фронт": "uniconf.ru",
    "бабаевский": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "фортуна": "fortuna-podarki.ru",
    "красный мозырянин": "mozyrconfectionery.by",
    "эссен": "essen-produkshn.ru",
}

DIRECT_GIFT_URLS = {
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
    "kommunarka.by": [
        "https://www.kommunarka.by/catalog/novogodnie-podarki/",
        "https://www.kommunarka.by/catalog/",
    ],
    "lakond.ru": ["https://lakond.ru/products/"],
}

# ЖЕСТКАЯ БЛОКИРОВКА ПРЕЗЕНТАЦИЙ И ЮРИДИЧЕСКОГО МУСОРА (Сстемминг)
DOC_BLACKLIST = [
    "презентац", "соглашени", "согласи", "политик", "конфиденциальн", 
    "персональн", "обработк", "договор", "оферт", "ваканси", "реквизит", 
    "cookies", "устав", "паспорт", "сертификат", "privacy", "agreement", "policy"
]

DOC_WHITELIST = ["каталог", "прайс", "price", "catalog", "подарки", "упаковка"]

# СЛУЖЕБНЫЕ ИКОНКИ И ЛОГОТИПЫ ПАРТНЕРОВ, КОТОРЫЕ ПРОПУСКАЕМ
FACTORY_LOGOS_AND_JUNK = [
    "logo", "brand", "partner", "proizvod", "партнер", "бренд", "производ",
    "акконд", "akkond", "бабаевск", "babaev", "ротфронт", "rotfront", 
    "красный_октябрь", "redoct", "essen", "эссен", "славянк", "slavyanka", 
    "конти", "konti", "kdv", "кдв", "побед", "марс", "mars",
    "banner", "slider", "slide", "bg-", "background", "header", "footer", 
    "decor", "hero", "icon", "avatar", "social", "payment", "delivery", "vk"
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
    """Безопасный поиск сайта без применения сторонних бибилотек"""
    q_low = company_name.lower().strip()
    dom = normalize_domain(q_low)
    if dom:
        return dom

    try:
        query_enc = urllib.parse.quote(f'"{company_name}" кондитерская фабрика подарки упаковка официальный сайт')
        resp = requests.post("https://html.duckduckgo.com/html/", data={"q": query_enc}, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a["href"]).query).get("uddg", [a["href"]])[0]
                netloc = urllib.parse.urlparse(target).netloc.replace("www.", "")
                if netloc and not any(bad in netloc for bad in ["wikipedia", "vk.com", "youtube", "checko", "list-org"]):
                    return netloc
    except Exception:
        pass

    return None

# --- ШАГ 1: ГЛУБОКИЙ ПОИСК ВСЕХ PDF/EXCEL КАТАЛОГОВ ---

def scan_documents(domain: str):
    docs, seen = [], set()
    base_url = f"https://{domain}"
    
    urls_to_scan = [base_url]
    if domain in DIRECT_GIFT_URLS:
        urls_to_scan.extend(DIRECT_GIFT_URLS[domain])

    _, main_html = get_html(base_url)
    if main_html:
        soup = BeautifulSoup(main_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().lower()
            text = a.get_text().strip().lower()
            
            if any(kw in href or kw in text for kw in ["catalog", "katalog", "download", "skachat", "podarki", "novogod"]):
                full_p = fix_and_encode_url(base_url, a["href"])
                if domain in full_p and full_p not in urls_to_scan and len(urls_to_scan) < 8:
                    urls_to_scan.append(full_p)

    def fetch_page_docs(page_url):
        p_docs = []
        _, page_html = get_html(page_url)
        if not page_html:
            return p_docs

        p_soup = BeautifulSoup(page_html, "html.parser")
        for a in p_soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip()
            title_attr = a.get("title", "").strip()
            full_link = fix_and_encode_url(page_url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {title_attr} {href}".lower()

                # БЛОКИРУЕМ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ ПО КОРНЯМ СЛОВ
                if any(bad in combined for bad in DOC_BLACKLIST_STEMS):
                    continue

                doc_title = text or title_attr or a.parent.get_text().strip() or href.split("/")[-1]
                doc_title = re.sub(r"\s+", " ", doc_title).strip()
                if len(doc_title) > 90:
                    doc_title = doc_title[:90] + "..."

                p_docs.append({"title": doc_title or "Официальный каталог 2026", "url": full_link})
        return p_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(fetch_page_docs, urls_to_scan):
            for d in res:
                if d["url"] not in seen:
                    seen.add(d["url"])
                    docs.append(d)

    return docs

# --- ШАГ 2: ВЫГРУЗКА ТОЛЬКО ПОДАРКОВ И КОРОБОК ---

def download_product_image(img_url: str):
    """Загружает фото подарка и проверяет геометрию (без баннеров и логотипов)"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
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
            if any(bad in src_low for bad in FACTORY_LOGOS_AND_JUNK):
                continue

            full_img_url = fix_and_encode_url(url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Отсекаем юр. мусор, текстиль и мягкие игрушки
            if any(bad in combined_text for bad in DOC_BLACKLIST_STEMS):
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

    validated = []
    def validate(p):
        info = download_product_image(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        validated = [r for r in executor.map(validate, raw_items[:80]) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название компании или адрес её сайта:",
    placeholder="Например: Спартак, Рубин, Акконд, Лаконд, Рэйд 21, Коммунарка, spartak.by...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    domain = find_domain_dynamic(company_input)

    if domain:
        st.success(f"🌐 Официальный сайт подключен: `{domain}`")

        # ШАГ 1: ПОИСК PDF КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ И ПОЛИТИК)
        with st.spinner("ШАГ 1: Ищем ВСЕ официальные PDF/Excel каталоги на сайте..."):
            documents = scan_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕНЫ ОФИЦИАЛЬНЫЕ КАТАЛОГИ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Скачайте официальные каталоги ниже.")
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
            # ШАГ 2: ИЗВЛЕЧЕНИЕ ТОЛЬКО НОВОГОДНИХ ПОДАРКОВ И КОРOБОК
            with st.spinner("ШАГ 2: Прямых PDF нет. Извлекаем фотографии подарков и коробок из каталога..."):
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
                st.error("На сайте не удалось найти карточки товаров. Введите адрес напрямую (например, spartak.by, rubin-2000.ru, akkond.ru)")
    else:
        st.error("Не удалось определить сайт. Введите адрес напрямую (например, spartak.by, rubin-2000.ru, akkond.ru)")

st.divider()
st.caption(f"Инструмент компании «Первый Снег». Сезон {TARGET_YEAR}.")
