import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

# Отключаем предупреждения SSL
requests.packages.urllib3.disable_warnings()

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Анализ Упаковки 2026",
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
        padding: 10px 20px; border-radius: 8px; text-decoration: none;
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

# -----------------------------
# РЕЕСТР ПРЯМЫХ ПУТЕЙ (KNOWLEDGE BASE)
# -----------------------------

SITES = {
    "спартак": "spartak.by",
    "акконд": "akkond.ru",
    "рубин": "rubin-2000.ru",
    "коммунарка": "kommunarka.by",
    "лаконд": "lakond.ru",
    "рэйд": "podarki-reid21.ru",
    "академия шоколада": "chocolate-academy.ru",
    "донко": "donko.su",
    "баян сулу": "bayansulu.kz",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
}

# Прямые ссылки на КАТАЛОГИ для 100% точности
TARGET_PATHS = {
    "spartak.by": ["/catalog/novogodnie_podarki/", "/catalog/novogodnie-podarki/"],
    "akkond.ru": ["/catalog/novyy_god/", "/catalog/novogodnie-podarki/"],
    "rubin-2000.ru": ["/catalog/", "/catalog/upakovka/"],
    "kommunarka.by": ["/catalog/novogodnie-podarki/"],
    "podarki-reid21.ru": ["/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"],
    "chocolate-academy.ru": ["/catalog/novogodnie-podarki/"],
}

# Фильтры
JUNK_DOCS = ["презентация", "соглашение", "политика", "договор", "оферта", "вакансии", "реквизиты"]
JUNK_IMAGES = ["logo", "icon", "banner", "slider", "bg-", "social", "avatar", "payment", "delivery", "vk", "хоккей", "кубок", "коллектив"]
TEXTILE_TOYS = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def normalize_domain(name):
    n = name.lower().strip()
    for k, v in SITES.items():
        if k in n: return v
    if "." in n and " " not in n:
        return n.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def get_html(url):
    # Блокировка новостей на уровне URL
    if any(p in url.lower() for p in ["/news", "/novosti", "/blog", "/about"]): return None, None
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def encode_url(base, src):
    if not src: return None
    full = urllib.parse.urljoin(base, src.strip())
    p = urllib.parse.urlparse(full)
    return urllib.parse.urlunparse((p.scheme, p.netloc, urllib.parse.quote(p.path), p.params, p.query, p.fragment))

# --- ШАГ 1: ПОИСК PDF ---
def scan_docs(domain):
    docs, seen = [], set()
    base = f"https://{domain}"
    paths = TARGET_PATHS.get(domain, ["/catalog/", "/podarki/", "/"])
    urls = [base + p for p in paths]
    
    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in JUNK_DOCS): continue
                if any(good in text or good in href for good in ["каталог", "прайс", "подарки", "2026", "2025"]):
                    full = encode_url(url, a['href'])
                    if full not in seen:
                        seen.add(full); docs.append({"title": a.get_text().strip() or "Официальный каталог", "url": full})
    return docs

# --- ШАГ 2: СБОР КАРТОЧЕК ---
def download_img(url):
    try:
        url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", url)
        url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", url)
        res = requests.get(url, headers=HEADERS, timeout=5, verify=False)
        if res.status_code == 200 and len(res.content) > 3500:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 130 or h < 130 or (w/h) > 1.6 or (w/h) < 0.38: return None
            return res.content
    except: pass
    return None

def scan_products(domain):
    base = f"https://{domain}"
    paths = TARGET_PATHS.get(domain, ["/catalog/", "/podarki/", "/"])
    urls = [base + p for p in paths]
    
    raw_prods, seen_imgs = [], set()

    def parse_page(url):
        _, html = get_html(url)
        if not html: return
        soup = BeautifulSoup(html, "html.parser")
        # Вырезаем мусор
        for junk in soup.find_all(re.compile(r'footer|header|partners|brands|slider', re.I)): junk.decompose()
        
        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card|goods", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in JUNK_IMAGES): continue
            
            full_img = encode_url(url, src)
            text = (card.get_text(" ", strip=True) if card.name != "img" else "") + " " + (img.get("alt") or "")
            if any(bad in text.lower() for bad in TEXTILE_TOYS + JUNK_IMAGES): continue

            if full_img and full_img not in seen_imgs:
                seen_imgs.add(full_img)
                weight = WEIGHT_REGEX.search(text)
                raw_prods.append({"title": (img.get("alt") or text[:50]).strip(), "weight": weight.group(1) if weight else None, "url": full_img})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(parse_page, urls)

    validated = []
    def validate(p):
        b = download_img(p['url'])
        if b: p['bytes'] = b; return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_prods[:80]) if r]
    return validated

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название фабрики (Спартак, Рубин, Акконд...) или адрес сайта:", placeholder="Например: Рэйд 21")

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query)
        if domain:
            st.success(f"🌐 Подключено к источнику: `{domain}`")
            
            with st.spinner("ШАГ 1: Ищем официальные PDF..."):
                docs = scan_docs(domain)
            
            if docs:
                st.subheader("📄 Найдены каталоги:")
                for d in docs: st.markdown(f'<div class="doc-card"><b>{d["title"]}</b><br><a href="{d["url"]}" target="_blank" class="btn-doc">📥 СКАЧАТЬ PDF</a></div>', unsafe_allow_html=True)
            
            with st.spinner("ШАГ 2: Выгружаю карточки коробок..."):
                items = scan_products(domain)
                if items:
                    st.success(f"Найдено оригинальных коробок: **{len(items)} шт.**")
                    zip_buf = io.BytesIO()
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for i, it in enumerate(items): zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
                    st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")
                    
                    cols = st.columns(4)
                    for i, it in enumerate(items):
                        with cols[i % 4]:
                            st.image(it['bytes'], use_container_width=True)
                            st.markdown(f'<div class="product-card"><div class="product-title">{it["title"][:50]}</div><span class="badge-cardboard">📦 КАРТОН</span><br><b>{it["weight"] or ""}</b></div>', unsafe_allow_html=True)
                else:
                    if not docs: st.error("Ничего не найдено. Проверьте название или введите прямой домен (например, lakond.ru)")
        else:
            st.error("Не удалось найти сайт автоматически. Введите адрес напрямую (например, rubin-2000.ru)")

st.divider()
st.caption(f"Инструмент коммерческого отдела «Первый Снег». Сезон {TARGET_YEAR}. Оптимизировано для стабильной работы.")
