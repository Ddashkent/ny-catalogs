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
    page_title="Первый Снег | Универсальный Экстрактор",
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

st.title(f"📦 Экстрактор Новогодней Упаковки {TARGET_YEAR}")
st.caption("Универсальный инструмент: находит официальный сайт любой компании, выгружает PDF каталоги или фото коробок без мусора.")

# -----------------------------
# СПИСКИ ФИЛЬТРАЦИИ И БАЗА
# -----------------------------

SITE_MAP = {
    "рубин": "rubin-2000.ru",
    "акконд": "akkond.ru",
    "спартак": "spartak.by",
    "эссен": "essen-produkshn.ru",
    "essen": "essen-produkshn.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "дилявер": "dilaver.ru",
    "баян сулу": "bayansulu.kz",
    "рэйд": "podarki-reid21.ru",
}

DOC_BLACKLIST = ["презентация", "соглашение", "политика", "договор", "оферта", "вакансии", "реквизиты", "cookies"]
DOC_WHITELIST = ["каталог", "прайс", "price", "catalog", "подарки", "упаковка"]

# СТРОГИЙ ЧЕРНЫЙ СПИСОК ЛОГОТИПОВ И МЯГКОЙ УПАКОВКИ
JUNK_IMAGE_WORDS = [
    "logo", "brand", "partner", "proizvod", "фабрик", "акконд", "бабаевск", "ротфронт", 
    "essen", "эссен", "славянк", "конти", "марс", "kdv", "побед", "banner", "slider", 
    "bg-", "social", "avatar", "payment", "delivery", "vk", "текстиль", "мягкая", 
    "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    # 1. Сначала ищем в нашей карте
    for k, domain in SITE_MAP.items():
        if k in v: return domain
    # 2. Если введена ссылка
    if "." in v and " " not in v:
        return v.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def find_domain_dynamic(company_name: str) -> str:
    """Универсальный поиск домена, если его нет в списке"""
    try:
        from duckduckgo_search import DDGS
        query = f'"{company_name}" официальный сайт кондитерская фабрика новогодние подарки'
        with DDGS() as ddgs:
            res = list(ddgs.text(query, region="ru-ru", max_results=3))
            if res:
                link = res[0]['href']
                if not any(bad in link for bad in ["wikipedia", "vk.com", "checko", "list-org"]):
                    parsed = urllib.parse.urlparse(link)
                    return parsed.netloc.replace("www.", "")
    except: pass
    return None

def fix_and_encode_url(base_url: str, src: str) -> str:
    src = src.strip()
    if src.startswith("//"): src = "https:" + src
    full = urllib.parse.urljoin(base_url, src)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(parsed.path)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment))

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

# --- ШАГ 1: ПОИСК PDF КАТАЛОГОВ ---

def scan_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"
    # Опрашиваем главную и основные разделы
    urls = [base, f"{base}/catalog/", f"{base}/podarki/", f"{base}/products/"]

    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip().lower()
            full_link = fix_and_encode_url(url, a["href"])
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                if any(bad in combined for bad in DOC_BLACKLIST): continue
                if any(good in combined for good in DOC_WHITELIST):
                    if full_link not in seen:
                        seen.add(full_link); docs.append({"title": a.get_text().strip() or "Официальный каталог", "url": full_link})
    return docs

# --- ШАГ 2: ВЫГРУЗКА КОРOБОК ---

def download_product_image(img_url: str):
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 130 or h < 130: return None
                ratio = w / h
                if ratio > 1.48 or ratio < 0.4: return None # Блокировка баннеров и логотипов
            return res.content
    except: pass
    return None

def scan_product_boxes(domain: str):
    base = f"https://{domain}"
    # Находим ссылки на каталоги
    target_pages = [base]
    _, html_main = get_html(base)
    if html_main:
        soup_main = BeautifulSoup(html_main, "html.parser")
        for a in soup_main.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text(" ", strip=True).lower()
            if any(kw in href or kw in text for kw in ["catalog", "podark", "produk", "упаков", "нг"]):
                full_cat = fix_and_encode_url(base, a['href'])
                if domain in full_cat and not any(bad in full_cat for bad in ["/news", "/about"]):
                    if full_cat not in target_pages: target_pages.append(full_cat)

    raw_items, seen_imgs = [], set()

    def parse_page(url):
        _, html = get_html(url)
        if not html: return
        p_soup = BeautifulSoup(html, "html.parser")
        # Удаляем из поиска подвал и бренды
        for junk in p_soup.find_all(["footer", "header", "nav", "aside"], class_=re.compile(r"partner|brand|footer|slider", re.I)):
            junk.decompose()

        cards = p_soup.find_all(["div", "li", "article"], class_=re.compile(r"product|catalog-item|card|item", re.I))
        if not cards: cards = p_soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in JUNK_IMAGE_WORDS): continue
            
            full_img = fix_and_encode_url(url, src)
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            if any(bad in (text + " " + (img.get("alt") or "")).lower() for bad in JUNK_IMAGE_WORDS): continue

            if full_img not in seen_imgs:
                seen_imgs.add(full_img)
                weight = WEIGHT_REGEX.search(text)
                title = img.get("alt") or img.get("title") or text[:50]
                raw_items.append({"title": title.strip(), "weight": weight.group(1) if weight else None, "url": full_img})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(parse_page, target_pages[:10])

    validated = []
    def validate(p):
        b = download_product_image(p["url"])
        if b: p["bytes"] = b; return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        validated = [r for r in executor.map(validate, raw_items[:80]) if r is not None]
    return validated

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

company_input = st.text_input("Введите название компании или её сайт:", placeholder="Эссен, Рубин, Акконд, Лаконд, rubin-2000.ru...")

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if company_input:
        domain = normalize_domain(company_input)
        if not domain:
            with st.spinner("Динамически определяем сайт..."):
                domain = find_domain_dynamic(company_input)
        
        if domain:
            st.success(f"🌐 Официальный сайт найден: `{domain}`")
            with st.spinner("ШАГ 1: Поиск PDF..."):
                docs = scan_documents(domain)
            
            if docs:
                st.success(f"🎉 НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ!")
                for d in docs:
                    st.markdown(f'<div class="doc-card"><b>📄 {d["title"]}</b><br><a href="{d["url"]}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ФАЙЛ</a></div>', unsafe_allow_html=True)
            else:
                with st.spinner("ШАГ 2: Извлекаем карточки товаров из каталога сайта..."):
                    products = scan_product_boxes(domain)
                if products:
                    st.success(f"Найдено коробок и подарков: **{len(products)} шт.**")
                    zip_buf = io.BytesIO()
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for i, prod in enumerate(products): zf.writestr(f"box_{i+1:02d}.jpg", prod["bytes"])
                    st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_boxes.zip", "application/zip")
                    st.markdown("---")
                    cols = st.columns(4)
                    for idx, prod in enumerate(products):
                        with cols[idx % 4]:
                            st.markdown(f'<div class="product-card"><div class="product-title">{prod["title"][:60]}</div><span class="badge-cardboard">📦 КАРТОН</span><br><b>{prod["weight"] or ""}</b></div>', unsafe_allow_html=True)
                            st.image(prod["bytes"], use_container_width=True)
                else: st.error("На сайте не удалось выгрузить карточки товаров.")
        else: st.error("Не удалось найти сайт. Введите домен напрямую.")
