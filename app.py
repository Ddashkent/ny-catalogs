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

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 22px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
        letter-spacing: 1px;
    }
    
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
        padding: 4px 10px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-bottom: 8px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")
st.caption("Автоматический фильтр: Текстиль, Кофры, Логотипы конфетных фабрик и Презентации исключены.")

# -----------------------------
# КОНСТИТУЦИЯ ФИЛЬТРАЦИИ
# -----------------------------

# БЛОКИРОВКА ПРЕЗЕНТАЦИЙ И ЮРИДИЧЕСКОГО МУСОРА
DOC_BLACKLIST = ["презентаци", "соглашени", "политик", "договор", "оферт", "реквизит", "ваканси", "устав"]

# БЛОКИРОВКА ЛОГОТИПОВ, БАННЕРОВ И ТЕКСТИЛЯ
JUNK_ITEMS = [
    "logo", "brand", "partner", "proizvod", "партнер", "бренд", "производ",
    "акконд", "akkond", "бабаевск", "ротфронт", "красный октябрь", "essen", "эссен", "кдв", "kdv",
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "мешок", "подушка", "рюкзак", "кофр", "пуф",
    "banner", "slider", "bg-", "hero", "icon"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ЛОГИКА
# -----------------------------

def normalize_domain(name):
    n = name.lower().strip()
    # Жесткая карта
    mapping = {"рубин": "rubin-2000.ru", "акконд": "akkond.ru", "спартак": "spartak.by", "рэйд": "podarki-reid21.ru", "академия": "chocolate-academy.ru"}
    for k, v in mapping.items():
        if k in n: return v
    if "." in n and " " not in n: return n.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def fix_url(base, src):
    if not src: return None
    src = src.strip()
    if src.startswith("//"): src = "https:" + src
    full = urllib.parse.urljoin(base, src)
    p = urllib.parse.urlparse(full)
    return urllib.parse.urlunparse((p.scheme, p.netloc, urllib.parse.quote(p.path), p.params, p.query, p.fragment))

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

# ШАГ 1: ПОИСК PDF
def scan_docs(domain):
    docs, seen = [], set()
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/", f"{base}/podarki/"]
    if domain == "podarki-reid21.ru": urls.insert(0, "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/")
    
    for url in urls:
        _, html = get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in DOC_BLACKLIST): continue
                if any(good in text or good in href for good in ["каталог", "прайс", "подарки", "2026"]):
                    full = fix_url(url, a['href'])
                    if full not in seen:
                        seen.add(full); docs.append({"title": a.get_text().strip(), "url": full})
    return docs

# ШАГ 2: СБОР КАРТОЧЕК
def scan_products(domain):
    base = f"https://{domain}"
    urls = [base, f"{base}/catalog/", f"{base}/podarki/"]
    if domain == "podarki-reid21.ru": urls.insert(0, "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/")
    
    raw_prods, seen_imgs = [], set()

    def parse_page(url):
        _, html = get_html(url)
        if not html: return
        soup = BeautifulSoup(html, "html.parser")
        
        # УДАЛЯЕМ БЛОКИ ПАРТНЕРОВ И БРЕНДОВ ИЗ HTML
        for junk in soup.find_all(re.compile(r'footer|header|partners|brands|vendor|client|slider', re.I)):
            junk.decompose()

        # Ищем карточки товаров
        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card|goods", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src: continue
            
            # ФИЛЬТР ЛОГОТИПОВ ПО ССЫЛКЕ
            if any(bad in src.lower() for bad in JUNK_ITEMS): continue
            
            full_img = fix_url(url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img)
            
            text = (card.get_text(" ", strip=True) if card.name != "img" else "") + " " + (img.get("alt") or "")
            if any(bad in text.lower() for bad in JUNK_ITEMS): continue

            if full_img not in seen_imgs:
                seen_imgs.add(full_img)
                weight = WEIGHT_REGEX.search(text)
                raw_prods.append({"title": img.get("alt") or text[:50], "weight": weight.group(1) if weight else None, "url": full_img})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(parse_page, urls)

    # Валидация картинок (пропорции)
    final = []
    def download(p):
        try:
            r = requests.get(p['url'], timeout=5, verify=False)
            if r.status_code == 200 and len(r.content) > 4000:
                if HAS_PIL:
                    img_p = Image.open(io.BytesIO(r.content))
                    w, h = img_p.size
                    if w < 160 or h < 160 or (w/h) > 1.55 or (w/h) < 0.4: return None
                p['bytes'] = r.content; return p
        except: pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        final = [r for r in executor.map(download, raw_prods[:100]) if r]
    return final

# --- ИНТЕРФЕЙС ---
query = st.text_input("Название фабрики:", placeholder="Рубин, Рэйд 21, Акконд...")

if st.button("🚀 НАЙТИ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query)
        if domain:
            st.info(f"🌐 Подключено к источнику: `{domain}`")
            docs = scan_docs(domain)
            if docs:
                st.subheader("📄 Найдены каталоги:")
                for d in docs: st.markdown(f'<div class="doc-card"><b>{d["title"]}</b><br><a href="{d["url"]}" target="_blank" class="btn-doc">📥 СКАЧАТЬ PDF</a></div>', unsafe_allow_html=True)
            
            items = scan_product_boxes(domain) if not docs else [] # Если нашли PDF, картинки не грузим
            if not docs:
                items = scan_products(domain)
                if items:
                    st.success(f"Найдено коробок: **{len(items)} шт.**")
                    zip_buf = io.BytesIO()
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for i, it in enumerate(items): zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
                    st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")
                    
                    cols = st.columns(4)
                    for i, it in enumerate(items):
                        with cols[i % 4]:
                            st.markdown('<div class="product-card">', unsafe_allow_html=True)
                            st.image(it['bytes'], use_container_width=True)
                            st.markdown(f'<span class="badge-cardboard">📦 КАРТОН</span><br><b>{it["title"][:50]}</b><br><small>{it["weight"] or ""}</small></div>', unsafe_allow_html=True)
                else: st.error("Коробки не найдены. Проверьте название.")
