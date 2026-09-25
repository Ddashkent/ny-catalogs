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

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

# Брендинг и мягкий невидимый снег
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.3; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #93c5fd; font-size: 11px; pointer-events: none; z-index: 0; }
    .f1 { left: 10%; animation: snowfall 22s linear infinite 0s; }
    .f2 { left: 45%; animation: snowfall 26s linear infinite 4s; }
    .f3 { left: 80%; animation: snowfall 24s linear infinite 2s; }

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
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 4px;
        display: inline-block; margin-bottom: 5px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")
st.caption("Автоматическая фильтрация: Логотипы фабрик, баннеры сайта, мягкие игрушки и юридические файлы исключены.")

# -----------------------------
# ЖЕСТКИЕ СНАЙПЕРСКИЕ ФИЛЬТРЫ
# -----------------------------

# БЛОКИРОВКА ДОКУМЕНТОВ-МУСОРА
DOC_BLACKLIST = [
    "презентац", "соглашени", "политик", "конфиденциальн", "персональн", 
    "договор", "оферт", "устав", "реквизит", "ваканси", "privacy", "agreement"
]
DOC_WHITELIST = ["каталог", "прайс", "price", "catalog", "подарки", "упаковка"]

# БЛОКИРОВКА ЛОГОТИПОВ ФАБРИК, БАННЕРОВ И ТЕКСТИЛЯ
IMAGE_BLACKLIST = [
    # Логотипы брендов и фабрик конфет (то, что было на скрине)
    "logo", "brand", "partner", "proizvod", "фабрик", "акконд", "бабаевск", 
    "ротфронт", "рот фронт", "красный_октябрь", "красный октябрь", "essen", 
    "эссен", "славянк", "конти", "марс", "kdv", "кдв", "побед", "поместье",
    # Декор сайта и баннеры
    "banner", "slider", "slide", "bg-", "background", "header", "footer", 
    "decor", "hero", "icon", "avatar", "social", "payment", "delivery",
    # Текстиль и игрушки
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок"
]

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

SITE_ROUTES = {
    "rubin-2000.ru": "https://rubin-2000.ru/catalog/",
    "podarki-reid21.ru": "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
    "chocolate-academy.ru": "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
    "lakond.ru": "https://lakond.ru/products/",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ФУНКЦИИ ПОИСКА
# -----------------------------

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    for k in SITE_MAP:
        if k in v: return SITE_MAP[k]
    if "." in v and " " not in v:
        return v.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def scan_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/", f"{base}/podarki/"]
    if domain in SITE_ROUTES: urls.insert(0, SITE_ROUTES[domain])

    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        
        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a['href']).lower()
            text = a.get_text().strip().lower()
            full_link = urllib.parse.urljoin(url, a['href'])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                # 1. ЖЕСТКО БЛОКИРУЕМ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if any(bad in combined for bad in DOC_BLACKLIST): continue
                # 2. ТРЕБУЕМ КАТАЛОГ ИЛИ ПРАЙС
                if any(good in combined for good in DOC_WHITELIST):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

def download_and_filter_box(img_url: str):
    """Качает картинку и отсеивает логотипы фабрик и длинные баннеры"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=5, verify=False)
        if res.status_code == 200 and len(res.content) > 3500:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                
                # Отсекаем мелкие логотипы конфет и иконки сайта
                if w < 160 or h < 160: return None
                
                ratio = w / h
                # Логотипы и длинные баннеры обычно очень широкие (ratio > 1.5) или узкие.
                # Настоящие коробки с подарками находятся в пределах 0.5...1.45
                if ratio > 1.48 or ratio < 0.45: return None

            return {"bytes": res.content, "ext": "jpg"}
    except: pass
    return None

def scan_product_boxes(domain: str):
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/", f"{base}/podarki/"]
    if domain in SITE_ROUTES: urls.insert(0, SITE_ROUTES[domain])

    raw_items = []
    seen = set()

    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")

        # Игнорируем блоки партнеров, подвала и шапки!
        for junk_block in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"partner|brand|footer|header|slider", re.I)):
            junk_block.decompose()

        # Ищем ИСКЛЮЧИТЕЛЬНО карточки товаров
        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|catalog-item|card|goods-item", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue

            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src: continue

            # ПРОВЕРКА ПО БАН-ЛИСТУ ЛОГОТИПОВ И БАННЕРОВ
            src_low = src.lower()
            if any(bad in src_low for bad in IMAGE_BLACKLIST): continue

            full_img = urllib.parse.urljoin(url, src)
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Отсекаем логотипы фабрик и текстиль по тексту рядом
            if any(bad in combined_text for bad in IMAGE_BLACKLIST): continue

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:50]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img not in seen and len(title) > 2:
                seen.add(full_img)
                raw_items.append({"title": title, "weight": weight, "img_url": full_img})

    # Фильтруем картинки по качеству и геометрии
    validated = []
    def validate(p):
        info = download_and_filter_box(p["img_url"])
        if info:
            p["bytes"] = info["bytes"]
            p["ext"] = info["ext"]
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_items[:60]) if r]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input("Введите название компании или адрес сайта:", placeholder="Рубин, Рэйд 21, Лаконд, Акконд, chocolate-academy.ru...")

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip(): st.stop()

    domain = normalize_domain(company_input)

    if domain:
        st.success(f"🌐 Официальный сайт найден: `{domain}`")

        with st.spinner("ШАГ 1: Сканируем сайт на наличие PDF/Excel каталогов..."):
            documents = scan_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Скачайте полный официальный файл каталога ниже.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">Ссылка: {doc['url']}</small><br>
                        <a href="{doc['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """, unsafe_allow_html=True)
        else:
            with st.spinner("ШАГ 2: Извлекаем фотографии картонных коробок (без логотипов фабрик и баннеров)..."):
                products = scan_product_boxes(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено картонных коробок и наборов: **{len(products)} шт.**")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"box_{i+1:02d}_{safe_name}.{prod['ext']}", prod["bytes"])

                st.download_button(f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP", zip_buffer.getvalue(), f"{domain}_boxes.zip", "application/zip")

                st.markdown("---")
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                <span class="badge-cardboard">📦 КАРТОН / УПАКОВКА</span>
                                {f'<br><span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """, unsafe_allow_html=True)
                        st.image(prod["bytes"], use_container_width=True)
            else:
                st.error("На сайте не удалось выгрузить коробки.")
    else:
        st.error("Не удалось найти сайт. Введите адрес напрямую (например, rubin-2000.ru)")

st.divider()
st.caption(f"Инструмент компании «Первый Снег». Сезон {TARGET_YEAR}. Логотипы партнеров, декоративные коллажи и юр. файлы отфильтрованы.")
