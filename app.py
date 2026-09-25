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
    page_title="Первый Снег | Только Картонная Упаковка",
    page_icon="📦",
    layout="wide",
)

TARGET_YEAR = 2026

# БРЕНДИНГ И НЕЖНЫЙ СНЕГ
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
    .s1 { left: 15%; animation: snowfall 18s linear infinite 0s; }
    .s2 { left: 40%; animation: snowfall 22s linear infinite 4s; }
    .s3 { left: 70%; animation: snowfall 20s linear infinite 2s; }

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
    
    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 4px 10px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-bottom: 8px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snowflake s1">❄</div><div class="snowflake s2">❅</div><div class="snowflake s3">❆</div>
""",
    unsafe_allow_html=True,
)

st.title(f"📦 Экстрактор Картонной Упаковки {TARGET_YEAR}")
st.caption("Автоматический фильтр: Текстиль, Мягкие игрушки, Кофры и Инфографика (составы) полностью исключены.")

# -----------------------------
# ЖЕСТКАЯ БИЗНЕС-ЛОГИКА (КОНСТИТУЦИЯ)
# -----------------------------

# Прямые ссылки на КАРТОННЫЕ разделы для известных сайтов
STRICT_ROUTES = {
    "podarki-reid21.ru": ["/product-category/podarki-v-kartonnoj-upakovke/"],
    "rubin-2000.ru": ["/catalog/"],
    "chocolate-academy.ru": ["/catalog/novogodnie-podarki/"],
}

# ЧЕРНЫЙ СПИСОК: Эти вещи мы НЕ берем никогда
HARD_BLACKLIST = [
    "кофр", "coffer", "складной", "пуф", "состав", "вложение", "список конфет", 
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", 
    "мешок", "оплата", "доставка", "акции", "инвесторам", "политика", "соглашение"
]

# БЕЛЫЙ СПИСОК МАТЕРИАЛОВ (Приоритет)
CARDBOARD_MARKERS = ["картон", "мгк", "тубус", "хром", "ерзац", "чемодан", "книга", "шкатулка", "пачка", "коробка"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "рэйд" in value or "reid21" in value: return "podarki-reid21.ru"
    if not value.startswith("http"): value = "https://" + value
    return urllib.parse.urlparse(value).netloc.replace("www.", "")

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

# --- ШАГ 1: ПОИСК PDF КАТАЛОГОВ (БЕЗ МУСОРА) ---

def scan_for_documents(domain: str):
    docs, seen = [], set()
    base_url = f"https://{domain}"
    
    # Проверяем главную и спец-разделы
    check_urls = [base_url]
    if domain in STRICT_ROUTES:
        check_urls.extend([base_url + p for p in STRICT_ROUTES[domain]])

    def check_page(url):
        found = []
        _, html = get_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href, text = a['href'].lower(), a.get_text().strip().lower()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                    # Фильтруем презентации и соглашения
                    if any(bad in text or bad in href for bad in ["политика", "соглашение", "презентация", "договор"]): continue
                    if any(good in text or good in href for good in ["каталог", "прайс", "подарки"]):
                        full = urllib.parse.urljoin(url, a['href'])
                        found.append({"title": a.get_text().strip(), "url": full})
        return found

    for url in check_urls:
        for d in check_page(url):
            if d['url'] not in seen:
                seen.add(d['url']); docs.append(d)
    return docs

# --- ШАГ 2: СБОР ТОЛЬКО КАРТОННЫХ КОРОБОК ---

def download_and_filter_image(img_url: str):
    """Отсекает баннеры и проверяет пропорции коробки"""
    try:
        res = requests.get(img_url, headers=HEADERS, timeout=5)
        if res.status_code == 200 and len(res.content) > 4000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 150 or h < 150: return None
                ratio = w / h
                # Картонные коробки имеют пропорции от 0.4 до 1.5. Баннеры > 1.8.
                if ratio > 1.6 or ratio < 0.4: return None
            return res.content
    except: pass
    return None

def scan_cardboard_only(domain: str):
    base_url = f"https://{domain}"
    target_pages = [base_url]
    if domain in STRICT_ROUTES:
        target_pages = [base_url + p for p in STRICT_ROUTES[domain]]

    products = []
    seen_imgs = set()

    def parse_page(url):
        items = []
        _, html = get_html(url)
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        
        # WooCommerce/Bitrix контейнеры
        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg-", "vk"]): continue
            
            full_img = urllib.parse.urljoin(url, src)
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            
            # ЖЕСТКАЯ ФИЛЬТРАЦИЯ: Убираем Кофры, Текстиль и Составы
            combined = (text + " " + (img.get("alt") or "")).lower()
            if any(bad in combined for bad in HARD_BLACKLIST): continue
            
            weight = WEIGHT_REGEX.search(text)
            weight_val = weight.group(1) if weight else None
            
            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img not in seen_imgs and len(title) > 3:
                seen_imgs.add(full_img)
                items.append({"title": title, "weight": weight_val, "img": full_img})
        return items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(parse_page, target_pages): products.extend(res)

    # Финальная валидация картинок
    final_prods = []
    def validate(p):
        img_bytes = download_and_filter_image(p['img'])
        if img_bytes:
            p['bytes'] = img_bytes
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        final_prods = [r for r in executor.map(validate, products[:80]) if r]
    
    return final_prods

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название компании или сайт:", placeholder="Рэйд-21, Рубин, Академия Шоколада...")

if st.button("🚀 НАЙТИ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query)
        st.success(f"🌐 Работаем с официальным источником: `{domain}`")
        
        with st.spinner("ШАГ 1: Поиск официальных PDF каталогов..."):
            docs = scan_for_documents(domain)
        
        if docs:
            st.success(f"✅ НАЙДЕНЫ КАТАЛОГИ/ПРАЙСЫ ({len(docs)} шт.)")
            for d in docs:
                st.markdown(f'<div class="doc-card"><b>📄 {d["title"]}</b><br><a href="{d["url"]}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ФАЙЛ</a></div>', unsafe_allow_html=True)
        else:
            with st.spinner("ШАГ 2: Прямых файлов нет. Извлекаю только картонные коробки с сайта..."):
                items = scan_cardboard_only(domain)
            
            if items:
                st.success(f"Найдено оригинальной картонной упаковки: **{len(items)} шт.**")
                
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, it in enumerate(items):
                        zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
                st.download_button("📥 СКАЧАТЬ ВСЕ КОРОБКИ В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")

                st.markdown("---")
                cols = st.columns(4)
                for i, it in enumerate(items):
                    with cols[i % 4]:
                        st.markdown('<div class="product-card">', unsafe_allow_html=True)
                        st.image(it['bytes'], use_container_width=True)
                        st.markdown(f'<span class="badge-cardboard">📦 КАРТОН</span><br><b>{it["title"][:50]}</b><br><small>{it["weight"] or ""}</small></div>', unsafe_allow_html=True)
            else:
                st.error("На сайте не удалось найти картонную упаковку. Попробуйте уточнить название.")
