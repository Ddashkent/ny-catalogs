import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Отключаем предупреждения SSL для стабильности
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

# Дизайн: Красно-белый логотип "Первый Снег" + Медленный нежный снег
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

st.title(f"📦 Анализ Каталогов & Упаковки {TARGET_YEAR}")
st.caption(
    "Приоритетный поиск официальных PDF/Excel прайсов. Извлечение оригинальных коробок и подарков без рекламных баннеров и юр. мусора."
)

# -----------------------------
# БАЗА ЗНАНИЙ (БЕЗ ПРИВЯЗКИ К РЕГИСТРУ)
# -----------------------------

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
    "баянсулу": "bayansulu.kz",
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "рейд": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "саратовская кф": "confashion.ru",
    "тореро": "torero.ru",
    "абинекс": "abineks.ru",
    "рэйд-21": "podarki-reid21.ru",
    "сибпродторг": "sibprodtorg.ru",
    "столичные поставки": "stolichnye.ru",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "рот фронт": "uniconf.ru",
    "бабаевский": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "фортуна": "fortuna-podarki.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
    "красный мозырянин": "mozyrconfectionery.by",
}

# ПРЯМЫЕ ССЫЛКИ НА КАТАЛОГИ
DIRECT_CATALOG_URLS = {
    "rubin-2000.ru": [
        "https://rubin-2000.ru/catalog/",
        "https://rubin-2000.ru/catalog/upakovka/",
    ],
    "podarki-reid21.ru": [
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarochnye-nabory-novogodnie-podarki-2027/",
    ],
    "chocolate-academy.ru": ["https://chocolate-academy.ru/catalog/novogodnie-podarki/"],
    "lakond.ru": ["https://lakond.ru/products/"],
}

# ФИЛЬТРЫ МУСОРА
JUNK_DOC_WORDS = [
    "презентация", "соглашение", "политика", "договор", "оферта", 
    "вакансии", "реквизиты", "cookies", "устав", "инвесторам"
]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "2027", "catalog", "price"]

JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk",
    "акконд", "бабаевск", "ротфронт", "красный_октябрь", "essen", "эссен", "славянк", "конти", "марс", "kdv"
]

TEXTILE_AND_TOY_JUNK = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    """Полностью независимая от регистра обработка имен и сайтов"""
    v = value.strip().lower()
    for k, domain in SITE_MAP.items():
        if k in v:
            return domain
    if "." in v and " " not in v:
        return v.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def fix_image_url(base_url: str, src: str) -> str:
    """Корректно собирает URL картинки, включая ссылки вида //static..."""
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    return urllib.parse.urljoin(base_url, src)

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def find_domain_dynamic(company_name: str) -> str:
    """Универсальный поиск сайта"""
    dom = normalize_domain(company_name)
    if dom:
        return dom
    try:
        from duckduckgo_search import DDGS
        query = f'"{company_name}" кондитерская фабрика подарки упаковка официальный сайт'
        with DDGS() as ddgs:
            res = list(ddgs.text(query, region="ru-ru", max_results=4))
            for r in res:
                link = r.get("href", "")
                if link and not any(bad in link for bad in ["wikipedia", "vk.com", "youtube", "checko"]):
                    return normalize_domain(link)
    except Exception:
        pass
    return None

# --- ШАГ 1: ПОИСК ТОЛЬКО КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ И ЮР. МУСОРА) ---

def scan_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/"]
    if domain in DIRECT_CATALOG_URLS:
        urls = DIRECT_CATALOG_URLS[domain] + urls

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip().lower()
            full_link = urllib.parse.urljoin(url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                # 1. ЗАБЛОКИРОВАТЬ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if any(bad in combined for bad in JUNK_DOC_WORDS):
                    continue
                # 2. ТРЕБОВАТЬ СЛОВА КАТАЛОГ / ПРАЙС
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

# --- ШАГ 2: ВЫГРУЗКА КАРТОЧЕК КАТАЛОГА (РУБИН, РЭЙД И ДР.) ---

def download_product_image(img_url: str):
    """Качает фото, удаляет Битрикс-ресайзы и отсеивает баннеры"""
    try:
        # Убираем ресайзы
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size

                # Отсекаем мелкие логотипы конфет и иконки
                if w < 130 or h < 130:
                    return None

                ratio = w / h
                # Коробки и подарки: пропорции от 0.38 до 1.65 (баннеры отсекаются)
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
    base = f"https://{domain}"
    urls = [f"{base}/catalog/", base]
    if domain in DIRECT_CATALOG_URLS:
        urls = DIRECT_CATALOG_URLS[domain] + urls

    raw_items = []
    seen_imgs = set()

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        # Удаляем из поиска подвал, шапку и блоки партнеров
        for junk_block in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"partner|brand|footer|header|slider", re.I)):
            junk_block.decompose()

        # Ищем карточки товаров по типичным CSS-контейнерам
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

            # Извлекаем ссылки даже из Lazy-Load (data-src, data-original)
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

            full_img = fix_image_url(url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Отсекаем текстиль, мягкие игрушки и логотипы
            if any(bad in combined_text for bad in JUNK_IMAGE_WORDS + TEXTILE_AND_TOY_JUNK):
                continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img)
                raw_items.append({"title": title, "weight": weight, "img_url": full_img})

    # Загружаем и валидируем фото в многопоточном режиме
    validated = []
    def validate(p):
        info = download_product_image(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_items[:80]) if r]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название компании или её сайт:",
    placeholder="Например: Рубин, РУБИН, Рэйд 21, Лаконд, Акконд, rubin-2000.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    # Ввод полностью независим от регистра
    domain = find_domain_dynamic(company_input)

    if domain:
        st.success(f"🌐 Подключено к официальному источнику: `{domain}`")

        # ШАГ 1: Поиск официально опубликованных PDF/Excel
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
            # ШАГ 2: Извлечение карточек коробок прямо из каталога сайта
            with st.spinner("ШАГ 2: Извлекаем фотографии коробок и подарков из каталога..."):
                products = scan_product_boxes(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено карточек упаковки и подарков: **{len(products)} шт.**")

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
        st.error("Не удалось определить сайт. Введите адрес напрямую (например, rubin-2000.ru)")

st.divider()
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Презентации и юридические файлы отфильтрованы.")
