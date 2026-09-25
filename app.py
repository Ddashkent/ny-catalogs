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

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    /* Логотип ПЕРВЫЙ СНЕГ (Красно-белый) */
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 10px 20px;
        border-radius: 5px; border: 2px solid #ffffff;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
        letter-spacing: 1px;
    }
    
    /* Едва заметный медленный снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px) rotate(0deg); opacity: 0; }
        20% { opacity: 0.3; }
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
        padding: 3px 8px; font-size: 11px; border-radius: 4px;
        display: inline-block; margin-bottom: 5px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="brand-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")
st.caption("Автоматический фильтр: Текстиль, Мягкие игрушки, Кофры и Составы конфет полностью исключены.")

# -----------------------------
# ЖЕСТКИЕ ПРАВИЛА ФИЛЬТРАЦИИ
# -----------------------------

# Исключаем текстиль, игрушки и инфографику
JUNK_ITEMS = [
    "текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", 
    "мешок", "кофр", "пуф", "состав", "вложение", "список", "banner", "slider"
]

# Обязательные маркеры для разделов
CARDBOARD_URLS = ["karton", "upakovka", "box", "catalog", "podarki", "produk", "shop"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ЛОГИКА ПОИСКА И ПАРСИНГА
# -----------------------------

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_site(name):
    # Приоритетные редиректы
    n_low = name.lower()
    if "рэйд" in n_low or "reid" in n_low: return "podarki-reid21.ru"
    if "академия шоколада" in n_low: return "chocolate-academy.ru"
    
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{name}" кондитерская фабрика новогодние подарки официальный сайт', max_results=3))
            if res: return urllib.parse.urlparse(res[0]['href']).netloc.replace("www.", "")
    except: pass
    return None

def scan_for_docs(domain):
    docs, seen = [], set()
    base = f"https://{domain}"
    _, html = get_html(base)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href, text = a['href'].lower(), a.get_text().strip().lower()
        if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
            # Фильтр: убираем Презентации, Соглашения, Политику
            if any(bad in text or bad in href for bad in ["политика", "соглашение", "презентация", "договор", "privacy"]): continue
            if any(good in text or good in href for good in ["каталог", "прайс", "подарки", "2026"]):
                full = urllib.parse.urljoin(base, a['href'])
                if full not in seen:
                    seen.add(full); docs.append({"title": a.get_text().strip(), "url": full})
    return docs

def scan_cardboard(domain):
    base = f"https://{domain}"
    _, html = get_html(base)
    if not html: return []

    # Собираем ссылки на разделы каталога
    soup = BeautifulSoup(html, "html.parser")
    targets = [base]
    for a in soup.find_all("a", href=True):
        href, text = a['href'].lower(), a.get_text().lower()
        full = urllib.parse.urljoin(base, a['href'])
        if domain in full and any(cw in href or cw in text for cw in CARDBOARD_URLS):
            if not any(bad in href or bad in text for bad in ["tekstil", "igrushk", "myagkaya", "dostavka", "oplata"]):
                if full not in targets: targets.append(full)
        if len(targets) > 12: break

    products = []
    seen_imgs = set()

    def parse_page(url):
        p_items = []
        _, p_html = get_html(url)
        if not p_html: return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        
        # Находим блоки карточек товаров
        containers = p_soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card|goods", re.I))
        if not containers: containers = p_soup.find_all("img")

        for card in containers:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            src = img.get("data-src") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg-", "vk"]): continue
            
            full_img = urllib.parse.urljoin(url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img) # Высокое качество
            
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            
            # ЖЕСТКИЙ ФИЛЬТР: Никакого текстиля, кофров и составов сладостей
            combined = (text + " " + (img.get("alt") or "")).lower()
            if any(bad in combined for bad in JUNK_ITEMS): continue
            
            weight = WEIGHT_REGEX.search(text)
            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if full_img not in seen_imgs and len(title) > 3:
                seen_imgs.add(full_img)
                p_items.append({"title": title, "weight": weight.group(1) if weight else None, "img": full_img})
        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(parse_page, targets): products.extend(res)

    # Финальная загрузка и фильтр баннеров (по пропорциям)
    final = []
    def download(p):
        try:
            r = requests.get(p['img'], timeout=5)
            if r.status_code == 200 and len(r.content) > 4000:
                if HAS_PIL:
                    img_pil = Image.open(io.BytesIO(r.content))
                    w, h = img_pil.size
                    if w < 180 or h < 180: return None
                    ratio = w / h
                    if ratio > 1.55 or ratio < 0.4: return None # Убираем баннеры и составы
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

query = st.text_input("Название компании или сайт:", placeholder="Например: Рэйд-21, Рубин, Академия Шоколада...")

if st.button("🚀 НАЙТИ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if query:
        domain = find_site(query) if "." not in query else query.strip().replace("https://", "").replace("http://", "").split("/")[0]
        
        if domain:
            st.info(f"🌐 Подключено к источнику: `{domain}`")
            
            with st.spinner("Проверяю официальные файлы каталогов..."):
                docs = scan_for_docs(domain)
            
            if docs:
                st.subheader("📄 Найдены официальные файлы:")
                for d in docs:
                    st.markdown(f"<div class='doc-card'><b>{d['title']}</b><br><a href='{d['url']}' target='_blank' class='btn-doc'>📥 СКАЧАТЬ КАТАЛОГ</a></div>", unsafe_allow_html=True)
            
            with st.spinner("Сканирую сайт... Выгружаю картонную упаковку..."):
                items = scan_cardboard(domain)
            
            if items:
                st.subheader(f"🖼️ Картонная упаковка и наборы ({len(items)} шт.)")
                
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for i, it in enumerate(items):
                        zf.writestr(f"cardboard_{i+1:02d}.jpg", it['bytes'])
                st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")

                cols = st.columns(4)
                for i, it in enumerate(items):
                    with cols[i % 4]:
                        st.markdown('<div class="product-card">', unsafe_allow_html=True)
                        st.image(it['bytes'], use_container_width=True)
                        st.markdown(f'<span class="badge-cardboard">📦 КАРТОН / МГК</span><br><div class="product-title">{it["title"][:50]}</div><b>{it["weight"] or ""}</b></div>', unsafe_allow_html=True)
            else:
                st.error("На сайте не удалось найти картонную упаковку. Возможно, каталог закрыт.")
