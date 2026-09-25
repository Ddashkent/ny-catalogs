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
    page_title="Первый Снег | Экстрактор Упаковки",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    
    /* Логотип ПЕРВЫЙ СНЕГ */
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    /* Мягкий невидимый снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px) rotate(0deg); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh) rotate(360deg); opacity: 0; }
    }
    .flake {
        position: fixed; top: -10px; color: #bae6fd; font-size: 10px;
        user-select: none; z-index: 0; pointer-events: none; opacity: 0.2;
    }
    .f1 { left: 15%; animation: snowfall 25s linear infinite; }
    .f2 { left: 45%; animation: snowfall 30s linear infinite 5s; }
    .f3 { left: 75%; animation: snowfall 28s linear infinite 2s; }

    .doc-card {
        background-color: #ffffff; border-left: 6px solid #dc2626;
        padding: 16px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #dc2626; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    
    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-bottom: 5px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""",
    unsafe_allow_html=True,
)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")
st.caption("Автоматический сбор каталогов и карточек подарков. Новости, презентации и текстиль отсекаются.")

# -----------------------------
# БАЗА И ФИЛЬТРЫ
# -----------------------------

SITE_MAP = {
    "акконд": "akkond.ru", "рубин": "rubin-2000.ru", "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru", "донко": "donko.su", "тор": "donko.su", "рэйд": "podarki-reid21.ru",
    "баян сулу": "bayansulu.kz", "конфешн": "confashion.ru", "славянка": "slavyanka.ru"
}

# Прямые ссылки на КАРТОННЫЕ разделы
DIRECT_URLS = {
    "akkond.ru": ["https://akkond.ru/catalog/novyy_god/"],
    "rubin-2000.ru": ["https://rubin-2000.ru/catalog/", "https://rubin-2000.ru/catalog/upakovka/"],
    "podarki-reid21.ru": ["https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"],
    "chocolate-academy.ru": ["https://chocolate-academy.ru/catalog/novogodnie-podarki/"]
}

JUNK_DOCS = ["презентация", "соглашение", "политика", "договор", "оферта", "вакансии", "реквизиты", "cookies"]
JUNK_ITEMS = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф", "состав", "вложение"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def normalize_domain(value):
    val = value.strip().lower()
    for k, v in SITE_MAP.items():
        if k in val: return v
    if "." in val and " " not in val:
        return val.replace("https://", "").replace("http://", "").split("/")[0]
    return "akkond.ru"

def fix_url(base, src):
    if not src: return None
    src = src.strip()
    if src.startswith("//"): src = "https:" + src
    full = urllib.parse.urljoin(base, src)
    p = urllib.parse.urlparse(full)
    return urllib.parse.urlunparse((p.scheme, p.netloc, urllib.parse.quote(p.path), p.params, p.query, p.fragment))

def get_html(url):
    if any(bad in url.lower() for bad in ["/news", "/novosti", "/blog", "/about"]): return None, None
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

# --- ШАГ 1: ПОИСК PDF ---

def scan_docs(domain):
    docs, seen = [], set()
    urls = DIRECT_URLS.get(domain, [f"https://{domain}/catalog/"])
    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in JUNK_DOCS): continue
                if any(good in text or good in href for good in ["каталог", "прайс", "подарки", "2026"]):
                    full = fix_url(url, a['href'])
                    if full not in seen:
                        seen.add(full); docs.append({"title": a.get_text().strip(), "url": full})
    return docs

# --- ШАГ 2: СБОР КАРТОЧЕК ---

def download_img(url):
    try:
        url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", url)
        url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", url)
        res = requests.get(url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 3000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 130 or h < 130 or (w/h) > 1.6 or (w/h) < 0.38: return None
            return res.content
    except: pass
    return None

def scan_products(domain):
    base_urls = DIRECT_URLS.get(domain, [f"https://{domain}/catalog/"])
    all_pages = set(base_urls)
    
    # Пытаемся раскрыть пагинацию
    for b_url in base_urls:
        _, html = get_html(b_url)
        if html:
            # Для Битрикса (Акконд/Рубин) генерируем страницы
            if "akkond" in domain or "rubin" in domain:
                for i in range(2, 6): all_pages.add(f"{b_url}?PAGEN_1={i}")
            # Ищем явные ссылки на страницы
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                if any(p in a['href'].lower() for p in ["page", "pagen", "p="]) or a.get_text().strip().isdigit():
                    all_pages.add(fix_url(b_url, a['href']))

    raw_items = []
    seen_imgs = set()

    def parse_page(url):
        items = []
        _, p_html 
