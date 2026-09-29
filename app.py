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
    
    /* Логотип ПЕРВЫЙ СНЕГ */
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid white;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    /* Нежный редкий снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.3; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #bae6fd; font-size: 10px; pointer-events: none; opacity: 0.2; }
    .f1 { left: 15%; animation: snowfall 22s linear infinite; }
    .f2 { left: 50%; animation: snowfall 26s linear infinite 4s; }
    .f3 { left: 80%; animation: snowfall 24s linear infinite 2s; }

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
st.caption("Глубокий сканер: находит новогодние разделы на любом сайте и выгружает 100% коробок без юридического мусора.")

# -----------------------------
# ЖЕСТКИЕ СНАЙПЕРСКИЕ ФИЛЬТРЫ
# -----------------------------

# КОРНЕВОЙ БАН-ЛИСТ ДЛЯ PDF (Убирает любые формы слов "политика", "соглашение", "презентация")
DOC_STEM_BLACKLIST = [
    "политик", "соглаш", "согласи", "конфиденц", "персон", "обработк", 
    "презентац", "договор", "оферт", "реквизит", "ваканс", "устав", "cookie", "куки"
]

# ОБЯЗАТЕЛЬНЫЕ СЛОВА ДЛЯ КАТАЛОГА (Файл принимается ТОЛЬКО если есть одно из них)
DOC_WHITELIST = ["каталог", "прайс", "подарки", "2026", "2025", "2027", "catalog", "price", "ассортимент"]

# БЛОКИРОВКА МЯГКИХ ИГРУШЕК, ТЕКСТИЛЯ И СЛУЖЕБНЫХ КАРТИНOК
BAD_IMAGES = ["logo", "icon", "banner", "slider", "bg-", "social", "vk", "payment", "delivery", "avatar"]
TEXTILE_JUNK = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф"]

SITES = {
    "акконд": "akkond.ru", "спартак": "spartak.by", "рубин": "rubin-2000.ru",
    "рэйд": "podarki-reid21.ru", "академия шоколада": "chocolate-academy.ru",
    "коммунарка": "kommunarka.by", "лаконд": "lakond.ru", "баян сулу": "bayansulu.kz"
}

# Прямые целевые пути
TARGET_PATHS = {
    "akkond.ru": ["https://akkond.ru/catalog/novyy_god/", "https://akkond.ru/catalog/novogodnie-podarki/"],
    "spartak.by": ["https://spartak.by/catalog/novogodnie_podarki/"],
    "rubin-2000.ru": ["https://rubin-2000.ru/catalog/"],
    "podarki-reid21.ru": ["https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"],
    "chocolate-academy.ru": ["https://chocolate-academy.ru/catalog/novogodnie-podarki/"]
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(name):
    n = name.lower().strip()
    for k, v in SITES.items():
        if k in n: return v
    if "." in n and " " not in n: return n.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def encode_safe_url(base, src):
    if not src: return None
    src = src.strip()
    if src.startswith("//"): src = "https:" + src
    full = urllib.parse.urljoin(base, src)
    p = urllib.parse.urlparse(full)
    return urllib.parse.urlunparse((p.scheme, p.netloc, urllib.parse.quote(p.path), p.params, p.query, p.fragment))

def get_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_all_catalog_links(domain):
    """Ищет новогодние категории сайта"""
    if domain in TARGET_PATHS:
        return TARGET_PATHS[domain]
        
    base_url = f"https://{domain}"
    final_url, html = get_page(base_url)
    if not html: return [base_url]
    
    soup = BeautifulSoup(html, "html.parser")
    found = {final_url}
    
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        full = encode_safe_url(final_url, a['href'])
        
        if full and domain in full:
            if any(kw in href or kw in text for kw in ["подар", "новогод", "нг", "catalog", "katalog", "produk", "2026"]):
                if not any(bad in href or bad in text for bad in ["news", "novosti", "oplata", "dostavka", "about"]):
                    found.add(full)
        if len(found) > 10: break
    return list(found)

# --- ШАГ 1: ПОИСК ТОЛЬКО НАСТОЯЩИХ PDF КАТАЛОГОВ ---

def scan_for_documents(domain):
    docs, seen = [], set()
    urls = find_all_catalog_links(domain)

    for url in urls:
        _, html = get_page(url)
        if not html: continue
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a['href']).lower()
            text = a.get_text().strip().lower()
            full_link = encode_safe_url(url, a['href'])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                
                # 1. СТРОГИЙ БЛОК ЮР. МУСОРА (Политика, Соглашение, Презентация)
                if any(stem in combined for stem in DOC_STEM_BLACKLIST):
                    continue
                
                # 2. ОБЯЗАТЕЛЬНОЕ НАЛИЧИЕ СЛОВА "КАТАЛОГ" ИЛИ "ПРАЙС"
                if any(good in combined for good in DOC_WHITELIST):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный каталог 2026", "url": full_link})
    return docs

# --- ШАГ 2: СБОР ВСЕХ КАРТОЧЕК С КАРТИНКАМИ ---

def download_product_bytes(img_url):
    """Качает фото, удаляет ресайзы Битрикса и проверяет геометрию коробки"""
    try:
        # Повышаем качество: убираем миниатюры Битрикса
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

        res = requests.get(img_url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200 and len(res.content) > 2500:
            if HAS_PIL:
                img_pil = Image.open(io.BytesIO(res.content))
                w, h = img_pil.size
                if w < 100 or h < 100: return None
                ratio = w / h
                # Картонные коробки: пропорции от 0.35 до 1.65 (все длинные баннеры отсекаются)
                if ratio > 1.7 or ratio < 0.35: return None
            return res.content
    except: pass
    return None

def scan_product_cards(domain):
    urls = find_all_catalog_links(domain)
    
    # Добавляем пагинацию Битрикса (?PAGEN_1=2, ?PAGEN_1=3...)
    expanded_urls = set(urls)
    for u in urls:
        if "akkond.ru" in domain or "rubin-2000.ru" in domain:
            for p_num in range(2, 6):
                expanded_urls.add(f"{u}?PAGEN_1={p_num}")
    
    raw_items = []
    seen_imgs = set()

    def parse_single_page(url):
        p_items = []
        _, html = get_page(url)
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        
        # Удаляем шапку и подвал
        for junk in soup.find_all(["footer", "header", "nav"], class_=re.compile(r"footer|header|partners|slider", re.I)):
            junk.decompose()

        cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|item|card|goods", re.I))
        if not cards: cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            
            src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("src")
            if not src or any(bad in src.lower() for bad in BAD_IMAGES): continue
            
            full_img = encode_safe_url(url, src)
            if not full_img or full_img in seen_imgs: continue

            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (text + " " + (img.get("alt") or "")).lower()

            # Исключаем текстиль, игрушки и юр. мусор
            if any(bad in combined_text for bad in TEXTILE_JUNK + DOC_STEM_BLACKLIST): continue

            weight = WEIGHT_REGEX.search(text)
            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if len(title) > 2:
                seen_imgs.add(full_img)
                p_items.append({
                    "title": title,
                    "weight": weight.group(1) if weight else None,
                    "url": full_img
                })
        return p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(parse_single_page, list(expanded_urls)):
            raw_items.extend(res)

    # Скачиваем байты изображений (Гарантирует запуск!)
    validated = []
    def validate(p):
        b = download_product_bytes(p["url"])
        if b:
            p["bytes"] = b
            return p
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(validate, raw_items) if r is not None]

    return validated

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название фабрики (Акконд, Рубин, Спартак, Лаконд...):", placeholder="Например: Акконд")

if st.button("🚀 НАЙТИ ВСЕ КАТАЛОГИ И КОРОБКИ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query)
        if domain:
            st.success(f"🌐 Подключено к источнику: `{domain}`")
            
            with st.status("Сканирую сайт и проверяю файлы...", expanded=True) as status:
                st.write("ШАГ 1: Поиск официальных PDF каталогов...")
                docs = scan_for_documents(domain)
                
                st.write("ШАГ 2: Выгрузка карточек товаров и коробок...")
                items = scan_product_cards(domain)
                status.update(label="Поиск успешно завершен!", state="complete")

            # ВЫВОД 1: PDF ФАЙЛЫ (ЕСЛИ ЕСТЬ НАСТОЯЩИЕ)
            if docs:
                st.subheader("📄 Официальные каталоги (PDF/Excel):")
                for d in docs:
                    st.markdown(f'''
                        <div class="doc-card">
                            <b>📕 {d["title"]}</b><br>
                            <a href="{d["url"]}" target="_blank" style="background:#dc2626;color:white;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;margin-top:6px;">📥 СКАЧАТЬ ФАЙЛ</a>
                        </div>
                    ''', unsafe_allow_html=True)

            # ВЫВОД 2: КАРТОЧКИ С ФОТОГРАФИЯМИ
            if items:
                st.subheader(f"🖼️ Картонная упаковка и подарки ({len(items)} шт.)")
                
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for i, it in enumerate(items):
                        zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
                        
                st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО В ZIP-АРХИВЕ", zip_buf.getvalue(), f"{domain}_catalog.zip", "application/zip")
                st.markdown("---")

                cols = st.columns(4)
                for i, it in enumerate(items):
                    with cols[i % 4]:
                        st.markdown('<div class="product-card">', unsafe_allow_html=True)
                        st.image(it['bytes'], use_container_width=True)
                        title_str = it['title'][:55]
                        weight_str = f" | ⚖️ {it['weight']}" if it['weight'] else ""
                        st.markdown(f'<div style="font-size:12px;font-weight:bold;margin-top:5px;color:#1e293b;">{title_str}{weight_str}</div></div>', unsafe_allow_html=True)
            else:
                if not docs:
                    st.error("На сайте не удалось найти карточки товаров. Введите прямой домен (например, lakond.ru)")
        else:
            st.error("Не удалось найти сайт. Введите адрес вручную (например: rubin-2000.ru)")
