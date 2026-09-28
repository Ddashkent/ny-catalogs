import concurrent.futures
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

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    /* Красно-белый логотип ПЕРВЫЙ СНЕГ */
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; font-size: 15px; padding: 10px 20px;
        border-radius: 8px; border: 2px solid white;
        box-shadow: 0 4px 15px rgba(220,38,38,0.4);
        letter-spacing: 1px;
    }
    /* Нежный медленный снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #bae6fd; font-size: 12px; pointer-events: none; z-index: 0; }
    
    .doc-card {
        background: white; border-left: 6px solid #dc2626;
        padding: 15px; border-radius: 10px; margin-bottom: 10px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .product-card {
        background: white; border: 1px solid #e2e8f0;
        padding: 10px; border-radius: 12px; text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03); margin-bottom: 20px;
    }
    </style>
    <div class="brand-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake" style="left:10%; animation: snowfall 15s linear infinite;">❄</div>
    <div class="flake" style="left:50%; animation: snowfall 20s linear infinite 3s;">❅</div>
    <div class="flake" style="left:85%; animation: snowfall 18s linear infinite 1s;">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")

# -----------------------------
# БАЗА ПРЯМЫХ ПУТЕЙ (KNOWLEDGE BASE)
# -----------------------------

SITES = {
    "акконд": "akkond.ru",
    "спартак": "spartak.by",
    "рубин": "rubin-2000.ru",
    "рэйд": "podarki-reid21.ru",
    "академия шоколада": "chocolate-academy.ru",
    "коммунарка": "kommunarka.by"
}

# Прямые ссылки на разделы с КАРТОННЫМИ коробками и подарками
TARGET_PATHS = {
    "akkond.ru": ["https://akkond.ru/catalog/novyy_god/"],
    "spartak.by": ["https://spartak.by/catalog/novogodnie_podarki/"],
    "rubin-2000.ru": ["https://rubin-2000.ru/catalog/"],
    "podarki-reid21.ru": ["https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"],
    "chocolate-academy.ru": ["https://chocolate-academy.ru/catalog/novogodnie-podarki/"],
    "kommunarka.by": ["https://www.kommunarka.by/catalog/novogodnie-podarki/"]
}

# Фильтры
BAD_FILES = ["презентация", "соглашение", "политика", "договор", "реквизиты", "вакансии"]
BAD_IMAGES = ["logo", "icon", "banner", "slider", "bg-", "social", "vk", "payment", "delivery", "акконд", "бабаевск", "essen", "эссен", "kdv"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def get_domain(name):
    n = name.lower().strip()
    for k, v in SITES.items():
        if k in n: return v
    if "." in n and " " not in n: return n.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def fetch_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def scan_docs(domain):
    docs, seen = [], set()
    urls = TARGET_PATHS.get(domain, [f"https://{domain}/catalog/"])
    for url in urls:
        _, html = fetch_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in BAD_FILES): continue
                if any(good in text or good in href for good in ["каталог", "прайс", "подарки", "2026"]):
                    full = urllib.parse.urljoin(url, a['href'])
                    if full not in seen:
                        seen.add(full); docs.append({"title": a.get_text().strip(), "url": full})
    return docs

def scan_products(domain):
    urls = TARGET_PATHS.get(domain, [f"https://{domain}/catalog/"])
    all_items, seen_imgs = [], set()

    def parse_page(url):
        _, html = fetch_html(url)
        if not html: return
        soup = BeautifulSoup(html, "html.parser")
        # Удаляем мусор
        for junk in soup.find_all(re.compile(r'footer|header|partners|brands|slider', re.I)): junk.decompose()
        
        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card|goods", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in BAD_IMAGES): continue
            
            full_img = urllib.parse.urljoin(url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img) # Качество
            
            if full_img not in seen_imgs:
                try:
                    r = requests.get(full_img, timeout=5, verify=False)
                    if r.status_code == 200 and len(r.content) > 4000:
                        img_pil = Image.open(io.BytesIO(r.content))
                        w, h = img_pil.size
                        # Фильтр коробки по пропорциям (не баннер)
                        if 0.4 < (w/h) < 1.6:
                            seen_imgs.add(full_img)
                            all_items.append({"title": (img.get("alt") or "Упаковка"), "bytes": r.content})
                except: pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(parse_page, urls)
    return all_items

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название фабрики (Акконд, Рубин, Спартак...):", placeholder="Например: Акконд")

if st.button("🚀 НАЙТИ КАТАЛОГ", type="primary", use_container_width=True):
    if query:
        domain = get_domain(query)
        if domain:
            st.info(f"🌐 Подключено к источнику: `{domain}`")
            
            docs = scan_docs(domain)
            if docs:
                st.subheader("📄 Найдены официальные файлы:")
                for d in docs: st.markdown(f'<div class="doc-card"><b>{d["title"]}</b><br><a href="{d["url"]}" target="_blank" style="background:#dc2626;color:white;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;margin-top:8px;">📥 СКАЧАТЬ PDF</a></div>', unsafe_allow_html=True)
            
            items = scan_products(domain)
            if items:
                st.subheader(f"📦 Картонная упаковка ({len(items)} шт.)")
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for i, it in enumerate(items): zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
                st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_boxes.zip", "application/zip")

                cols = st.columns(4)
                for i, it in enumerate(items):
                    with cols[i % 4]:
                        st.markdown('<div class="product-card">', unsafe_allow_html=True)
                        st.image(it['bytes'], use_container_width=True)
                        st.markdown(f'<div style="font-size:12px;font-weight:bold;margin-top:5px;color:#1e293b;">{it["title"][:50]}</div></div>', unsafe_allow_html=True)
        else:
            st.error("Введите корректное название или домен.")
