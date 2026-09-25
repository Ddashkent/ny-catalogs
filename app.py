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
# НАСТРОЙКИ ИНТЕРФЕЙСА
# -----------------------------

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f1f5f9; }
    
    /* Официальный логотип "Первый Снег" */
    .brand-header {
        position: fixed; top: 10px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; padding: 10px 20px; border-radius: 10px;
        border: 2px solid white; box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
    }
    
    /* Мягкий снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.5; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .snow { position: fixed; top: -10px; color: #bae6fd; pointer-events: none; z-index: 0; }
    
    .doc-card {
        background: white; border-left: 6px solid #dc2626;
        padding: 15px; border-radius: 10px; margin-bottom: 10px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .product-card {
        background: white; border: 1px solid #e2e8f0;
        padding: 12px; border-radius: 15px; text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px;
    }
    .badge-weight {
        background: #dc2626; color: white; padding: 3px 10px;
        border-radius: 10px; font-size: 12px; font-weight: bold;
    }
    </style>
    
    <div class="brand-header">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snow" style="left:10%; animation: snowfall 12s linear infinite;">❄</div>
    <div class="snow" style="left:40%; animation: snowfall 15s linear infinite 2s;">❅</div>
    <div class="snow" style="left:70%; animation: snowfall 14s linear infinite 4s;">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Упаковки: Сезон {TARGET_YEAR}")
st.caption("Автоматический сбор каталогов и визуальных карточек подарков. Служебные страницы (Оплата/Доставка) отсекаются.")

# -----------------------------
# ПРАВИЛА И ФИЛЬТРЫ
# -----------------------------

# СЛУЖЕБНЫЕ СЛОВА (ТУДА НЕ ЗАХОДИМ)
SERVICE_WORDS = ["оплата", "доставка", "новости", "акции", "контакты", "payment", "delivery", "shipping", "news", "contacts"]

# СЛОВА-МАРКЕРЫ ТОВАРОВ
GIFT_MARKERS = ["каталог", "подарки", "упаковка", "наборы", "produk", "catalog", "shop", "category"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ЛОГИКА
# -----------------------------

def normalize_domain(value):
    val = value.strip().lower()
    if "рэйд" in val or "reid21" in val: return "podarki-reid21.ru"
    if not val.startswith("http"): val = "https://" + val
    return urllib.parse.urlparse(val).netloc.replace("www.", "")

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_site(name):
    # Прямой редирект для известных нам проблемных запросов
    if "рэйд" in name.lower(): return "podarki-reid21.ru"
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{name}" официальный сайт кондитерская фабрика новогодние подарки', max_results=3))
            if res: return normalize_domain(res[0]['href'])
    except: pass
    return None

def scan_for_docs(domain):
    """Ищет PDF/XLS только на целевых страницах"""
    base = f"https://{domain}"
    docs, seen = [], set()
    
    # Сначала проверяем главную
    curr_url, html = get_html(base)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        full = urllib.parse.urljoin(curr_url, a['href'])
        text = a.get_text().lower()
        
        # Фильтр: только файлы и только новогодние
        if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
            if any(good in href or good in text for good in ["каталог", "прайс", "подарки", "2026"]):
                if not any(bad in text or bad in href for bad in SERVICE_WORDS + ["согласие", "политика"]):
                    if full not in seen:
                        seen.add(full)
                        docs.append({"title": a.get_text().strip() or "Каталог подарков", "url": full})
    return docs

def scan_products(domain):
    """Глубокий поиск коробок в категориях товаров"""
    base = f"https://{domain}"
    _, html = get_html(base)
    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    target_pages = [base]
    
    # Собираем ссылки только на разделы магазина/каталога
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        full = urllib.parse.urljoin(base, a['href'])
        
        if domain in full:
            # Игнорируем доставку, оплату и т.д.
            if any(bad in href or bad in text for bad in SERVICE_WORDS): continue
            # Берем только то, что похоже на подарки или категории
            if any(good in href or good in text for good in GIFT_MARKERS):
                if full not in target_pages: target_pages.append(full)
        if len(target_pages) > 10: break

    products = []
    seen_imgs = set()

    def parse_page(url):
        p_items = []
        _, p_html = get_html(url)
        if not p_html: return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        
        # WooCommerce/Bitrix карточки
        cards = p_soup.find_all(["div", "li"], class_=re.compile(r"product|item|card|entry", re.I))
        if not cards: cards = p_soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            
            src = img.get("data-src") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "delivery", "payment"]): continue
            
            full_img = urllib.parse.urljoin(url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img) # Качество
            
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            weight = WEIGHT_REGEX.search(text)
            weight_val = weight.group(1) if weight else None
            
            title = img.get("alt") or img.get("title") or text[:50]
            
            # Если это "Доставка" или "Оплата" - пропускаем
            if any(bad in title.lower() for bad in SERVICE_WORDS): continue
            
            if full_img not in seen_imgs and len(title) > 3:
                seen_imgs.add(full_img)
                p_items.append({"title": title.strip(), "weight": weight_val, "img": full_img})
        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(parse_page, target_pages):
            products.extend(res)
    
    # Финальная загрузка картинок
    final = []
    def download(p):
        try:
            r = requests.get(p['img'], timeout=5)
            if r.status_code == 200:
                if HAS_PIL:
                    img = Image.open(io.BytesIO(r.content))
                    w, h = img.size
                    if w < 200 or h < 200: return None
                    if (w/h) > 1.5: return None # Убираем баннеры
                p['bytes'] = r.content
                return p
        except: pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        final = [item for item in executor.map(download, products[:80]) if item]
    
    return final

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название компании или сайт:", placeholder="Рэйд-21, Рубин, Академия Шоколада...")

if st.button("🚀 НАЙТИ ПОДАРКИ", type="primary"):
    if query:
        domain = normalize_domain(query) if "." in query else find_site(query)
        
        if domain:
            st.success(f"🌐 Работаем с сайтом: `{domain}`")
            
            with st.spinner("Проверка официальных PDF..."):
                docs = scan_for_docs(domain)
            
            if docs:
                st.subheader("📄 Найдены каталоги:")
                for d in docs:
                    st.markdown(f"<div class='doc-card'><b>{d['title']}</b><br><a href='{d['url']}' target='_blank'>📥 СКАЧАТЬ PDF</a></div>", unsafe_allow_html=True)
            
            with st.spinner("Захожу в разделы каталога и выгружаю упаковку..."):
                items = scan_products(domain)
            
            if items:
                st.subheader(f"🖼️ Карточки продукции ({len(items)} шт.):")
                
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for i, it in enumerate(items):
                        zf.writestr(f"item_{i+1:02d}.jpg", it['bytes'])
                st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_items.zip", "application/zip")

                cols = st.columns(4)
                for i, it in enumerate(items):
                    with cols[i % 4]:
                        st.image(it['bytes'], use_container_width=True)
                        st.markdown(f"<div style='text-align:center;'><b>{it['title'][:50]}</b><br><span class='badge-weight'>{it['weight'] or ''}</span></div>", unsafe_allow_html=True)
            else:
                st.warning("Не удалось автоматически найти коробки. Попробуйте ввести домен podarki-reid21.ru напрямую.")
