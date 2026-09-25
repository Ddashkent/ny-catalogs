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
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Анализ Упаковки 2026",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

# Красно-белый логотип "Первый Снег" + Медленный снег
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

st.title(f"📦 Экстрактор Каталогов & Упаковки {TARGET_YEAR}")
st.caption("Сбор коробок и подарков из разделов 'Каталог подарков' и 'Каталог упаковки'. Презентации и юридический мусор исключены.")

# -----------------------------
# БАЗА ПРЯМЫХ ПУТЕЙ СAЙТОВ
# -----------------------------

SITE_MAP = {
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "униконф": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
}

# Прямые каталожные адреса для идеального сбора
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

# ЧЕРНЫЙ СПИСОК ФАЙЛОВ (Презентации, Соглашения, Юр. документы)
JUNK_DOC_WORDS = [
    "презентация",
    "соглашение",
    "политика",
    "договор",
    "оферта",
    "вакансии",
    "реквизиты",
    "cookies",
    "устав",
]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "catalog", "price"]

# ИСКЛЮЧАЕМ ЛОГОТИПЫ, БАННЕРЫ И ИКОНКИ
JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk"
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
    return "rubin-2000.ru"

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def scan_documents(domain: str):
    """Сканирует только реальные PDF/Excel каталоги (без презентаций)"""
    docs, seen = [], set()
    base = f"https://{domain}"
    
    urls = [base, f"{base}/catalog/"]
    if domain in DIRECT_CATALOG_URLS:
        urls.extend(DIRECT_CATALOG_URLS[domain])

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
                # 2. ТРЕБОВАТЬ СЛОВО "КАТАЛОГ" ИЛИ "ПРАЙС"
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог", "url": full_link})
    return docs

def download_product_image(img_url: str):
    """Качает картинку, повышает качество и отсекает баннеры"""
    try:
        # Убираем ресайзы Битрикса и миниатюры
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                
                # Игнорируем мелкие логотипы конфетных фабрик и иконки
                if w < 130 or h < 130:
                    return None

                ratio = w / h
                # Коробки и подарки: пропорции от 0.38 до 1.6
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
    """Извлекает карточки товаров с изображениями, названием и весом"""
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

        # Находим контейнеры продуктов
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

            # Извлекаем ссылки даже из lazy-load атрибутов (data-src, data-original)
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

            full_img = urllib.parse.urljoin(url, src)

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            
            # Извлекаем вес (например "500 г")
            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            # Извлекаем название товара
            title = img.get("alt") or img.get("title") or text[:65]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img not in seen_imgs and len(title) > 2:
                seen_imgs.add(full_img)
                raw_items.append({"title": title, "weight": weight, "img_url": full_img})

    # Загружаем и валидируем фото
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
    "Введите название компании или адрес её сайта:",
    placeholder="Например: Рубин, Академия Шоколада, Лаконд, Рэйд 21, rubin-2000.ru...",
)

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()

    domain = normalize_domain(company_input)

    if domain:
        st.success(f"🌐 Подключено к сайту: `{domain}`")

        # ШАГ 1: ПОИСК PDF КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ)
        with st.spinner("Проверяем наличие официальных PDF/Excel каталогов..."):
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
            # ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ ИЗ КАТАЛОГА
            with st.spinner("Собираем карточки подарков и упаковки с сайта..."):
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
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Сбор данных прямо из каталога сайта.")
