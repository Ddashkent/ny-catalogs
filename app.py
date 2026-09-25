import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт Pillow
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(page_title="Первый Снег | Экстрактор Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    /* Логотип ПЕРВЫЙ СНЕГ */
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; font-size: 15px; padding: 10px 20px;
        border-radius: 5px; border: 2px solid white;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
        letter-spacing: 1px;
    }
    
    /* Мягкий снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px) rotate(0deg); opacity: 0; }
        20% { opacity: 0.3; }
        100% { transform: translateY(100vh) rotate(360deg); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #bae6fd; font-size: 10px; pointer-events: none; opacity: 0.2; }
    .f1 { left: 15%; animation: snowfall 25s linear infinite; }
    .f2 { left: 45%; animation: snowfall 30s linear infinite 5s; }
    .f3 { left: 75%; animation: snowfall 28s linear infinite 2s; }

    .doc-card {
        background-color: white; border-left: 6px solid #dc2626;
        padding: 16px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #dc2626; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    .product-card {
        background-color: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 4px;
        display: inline-block; margin-bottom: 5px;
    }
    </style>
    <div class="brand-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")

# -----------------------------
# ЖЕСТКИЕ ПРАВИЛА (КОНСТИТУЦИЯ)
# -----------------------------

# Блокировка мусорных файлов
BAD_DOCS = ["презентация", "соглашение", "политика", "договор", "оферта", "вакансии", "реквизиты"]
# Блокировка не-картона и инфографики
BAD_ITEMS = ["текстиль", "мягкая", "игрушка", "плюш", "рюкзак", "подушка", "мешок", "кофр", "пуф", "состав", "вложение", "список"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ФУНКЦИИ (ОПРЕДЕЛЕНЫ ДО ВЫЗОВА)
# -----------------------------

def normalize_domain(value):
    val = value.strip().lower()
    if "рэйд" in val or "reid" in val: return "podarki-reid21.ru"
    if not val.startswith("http"): val = "https://" + val
    return urllib.parse.urlparse(val).netloc.replace("www.", "")

def find_domain_dynamic(name):
    """Безопасный поиск сайта"""
    if "рэйд" in name.lower(): return "podarki-reid21.ru"
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{name}" кондитерская фабрика официальный сайт', max_results=2))
            if res: return urllib.parse.urlparse(res[0]['href']).netloc.replace("www.", "")
    except: pass
    return name.lower().replace(" ", "") + ".ru"

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def scan_assets(domain):
    """Основной движок сбора данных"""
    base = f"https://{domain}"
    # Глубокие пути для Рэйд-21 и классических сайтов
    paths = ["", "/catalog/", "/podarki/", "/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"]
    urls = [base + p for p in paths]
    
    docs, prods = [], []
    seen = set()

    def parse_page(url):
        p_docs, p_prods = [], []
        _, html = get_html(url)
        if not html: return [], []
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Файлы
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in BAD_DOCS): continue
                if any(good in text or good in href for good in ["каталог", "прайс", "подарки"]):
                    full = urllib.parse.urljoin(url, a['href'])
                    p_docs.append({"title": a.get_text().strip(), "url": full})

        # 2. Картинки карточек
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if not src or any(b in src.lower() for b in ["logo", "icon", "banner", "bg-"]): continue
            
            full_img = urllib.parse.urljoin(url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img)
            
            text_context = (img.get("alt", "") + " " + (img.parent.get_text() if img.parent else "")).lower()
            if any(bad in text_context for bad in BAD_ITEMS): continue
            
            if full_img not in seen:
                seen.add(full_img)
                # Фильтр пропорций (убираем баннеры и составы)
                try:
                    r = requests.get(full_img, timeout=5)
                    if HAS_PIL and r.status_code == 200:
                        img_pil = Image.open(io.BytesIO(r.content))
                        w, h = img_pil.size
                        if 0.4 < (w/h) < 1.6: # Коробка
                            p_prods.append({"title": img.get("alt")[:50] or "Упаковка", "img": r.content})
                except: pass
        return p_docs, p_prods

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(parse_page, urls)
        for d, p in results:
            docs.extend(d)
            prods.extend(p)
            
    return docs, prods

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название фабрики:", placeholder="Например: Рэйд 21 или Рубин")

if st.button("🚀 НАЙТИ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query) if "." in query else find_domain_dynamic(query)
        st.info(f"🌐 Подключено к: `{domain}`")
        
        docs, items = scan_assets(domain)
        
        if docs:
            st.subheader("📄 Найдены каталоги:")
            for d in docs:
                st.markdown(f'<div class="doc-card"><b>{d["title"]}</b><br><a href="{d["url"]}" target="_blank" class="btn-doc">📥 СКАЧАТЬ PDF</a></div>', unsafe_allow_html=True)
        
        if items:
            st.subheader(f"🖼️ Картонная упаковка ({len(items)} шт.)")
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for i, it in enumerate(items): zf.writestr(f"box_{i+1:02d}.jpg", it['img'])
            st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), "cardboard.zip", "application/zip")

            cols = st.columns(4)
            for i, it in enumerate(items):
                with cols[i % 4]:
                    st.markdown('<div class="product-card">', unsafe_allow_html=True)
                    st.image(it['img'], use_container_width=True)
                    st.markdown(f'<span class="badge-cardboard">📦 КАРТОН</span><br><small>{it["title"]}</small></div>', unsafe_allow_html=True)
        else:
            st.error("На сайте не найдено подходящей упаковки. Проверьте название.")
