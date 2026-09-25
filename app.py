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

# --- ДИЗАЙН: Логотип, мягкий снег и карточки ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    
    /* Логотип компании в углу */
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background: linear-gradient(135deg, #0284c7, #38bdf8);
        color: white; font-weight: 900; font-size: 16px;
        padding: 8px 16px; border-radius: 8px;
        box-shadow: 0 4px 10px rgba(2, 132, 199, 0.3);
        letter-spacing: 1px; text-transform: uppercase;
    }
    
    /* Кастомный медленный снег на фоне */
    @keyframes fall {
        0% { transform: translateY(-20px) rotate(0deg); opacity: 0; }
        20% { opacity: 0.5; }
        100% { transform: translateY(100vh) rotate(360deg); opacity: 0; }
    }
    .flake {
        position: fixed; top: -20px; color: #bae6fd; font-size: 1.2em;
        user-select: none; z-index: 0; pointer-events: none;
    }
    .flake:nth-child(1) { left: 10%; animation: fall 12s linear infinite 0s; }
    .flake:nth-child(2) { left: 30%; animation: fall 15s linear infinite 2s; }
    .flake:nth-child(3) { left: 50%; animation: fall 14s linear infinite 4s; }
    .flake:nth-child(4) { left: 70%; animation: fall 18s linear infinite 1s; }
    .flake:nth-child(5) { left: 90%; animation: fall 13s linear infinite 3s; }
    
    .doc-card {
        background-color: #ffffff; border-left: 6px solid #28a745;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04); position: relative; z-index: 10;
    }
    .btn-doc {
        background-color: #28a745; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    .btn-doc:hover { background-color: #218838; }
    
    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.03);
        position: relative; z-index: 10;
    }
    .badge-weight {
        background-color: #0284c7; color: white; font-weight: bold;
        padding: 3px 10px; font-size: 13px; border-radius: 12px;
        display: inline-block; margin-top: 5px;
    }
    .product-title { font-weight: 700; font-size: 14px; color: #1a202c; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    
    <!-- Нежный снег -->
    <div class="flake">❄</div><div class="flake">❅</div><div class="flake">❆</div>
    <div class="flake">❄</div><div class="flake">❅</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Каталогов & Упаковки {TARGET_YEAR}")
st.caption("Приоритетный поиск официальных PDF/Excel. Автоматический сбор визуалов. Мусор и штучные конфеты отсекаются.")

# -----------------------------
# БАЗА И ЖЕСТКИЕ ФИЛЬТРЫ
# -----------------------------

KNOWLEDGE_BASE = {
    "акконд": "akkond.ru", "рубин": "rubin-2000.ru", "лаконд": "lakond.ru",
    "донко": "donko.su", "тор": "donko.su", "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru", "дедморозов": "dedmorozov.ru", "коммунарка": "kommunarka.by",
    "спартак": "spartak.by", "рахат": "rakhat.kz", "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru", "тореро": "torero.ru", "абинекс": "abineks.ru",
    "рэйд-21": "raid21.ru", "сибпродторг": "sibprodtorg.ru", "столичные поставки": "stolichnye.ru",
    "униконф": "uniconf.ru", "аленка": "podarki.alenka.ru", "фортуна": "fortuna-podarki.ru",
    "победа": "pobeda.market", "славянка": "slavyanka.ru", "красный мозырянин": "mozyrconfectionery.by",
    "академия шоколада": "chocolate-academy.ru"
}

# ЖЕСТКИЕ ПРАВИЛА ДЛЯ ФАЙЛОВ
REQUIRED_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "новогод", "catalog", "price"]
JUNK_DOC_WORDS = ["политика", "согласие", "соглашение", "презентация", "реквизиты", "вакансии", "устав", "договор", "оферта", "инвесторам"]

# ЖЕСТКИЕ ПРАВИЛА ДЛЯ КАРТИНОК И ТОВАРОВ
JUNK_IMG_WORDS = ["печенье", "батончик", "мармелад", "вафли", "карамель", "драже", "весовые", "штучные", "banner", "slider", "bg-", "logo", "icon"]
CATALOG_URL_WORDS = ["новогод", "подар", "набор", "упаков", "каталог", "catalog"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
WEIGHT_REGEX = re.compile(r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("http"): value = "https://" + value
    return urllib.parse.urlparse(value).netloc.replace("www.", "")

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=7, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_domain_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE: return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k: return v
    
    try:
        query = f'"{company_name}" новогодняя упаковка подарки официальный сайт'
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a['href']).query).get("uddg", [a['href']])[0]
                netloc = normalize_domain(target)
                if netloc and not any(bad in netloc for bad in ["wikipedia", "vk.com", "youtube", "list-org", "checko", "pravo"]):
                    return netloc
    except: pass
    return None

# --- ШАГ 1: ПОИСК ДОКУМЕНТОВ ---

def scan_for_documents(domain: str):
    docs, seen = [], set()
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return docs

    scan_urls = [final_url]
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        full = urllib.parse.urljoin(final_url, a['href'])
        if domain in full and any(cw in full.lower() or cw in a.get_text().lower() for cw in CATALOG_URL_WORDS):
            if full not in scan_urls and len(scan_urls) < 6:
                scan_urls.append(full)

    def check_page(url):
        page_docs = []
        p_url, p_html = get_html(url)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = urllib.parse.unquote(a['href']).lower()
                text = a.get_text().strip().lower()
                full_link = urllib.parse.urljoin(p_url, a['href'])
                
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    combined = f"{text} {href}"
                    # 1. ЖЕСТКИЙ БЛОК МУСОРА (Презентации, Соглашения)
                    if any(junk in combined for junk in JUNK_DOC_WORDS): continue
                    # 2. ОБЯЗАТЕЛЬНОЕ НАЛИЧИЕ НУЖНЫХ СЛОВ (Каталог, прайс, подарки)
                    if not any(req in combined for req in REQUIRED_DOC_WORDS): continue
                    
                    page_docs.append({"title": a.get_text().strip() or "Официальный каталог / прайс", "link": full_link})
        return page_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(check_page, scan_urls):
            for d in res:
                if d['link'] not in seen:
                    seen.add(d['link'])
                    docs.append(d)
    return docs

# --- ШАГ 2: ВИЗУАЛЬНЫЙ СБОР ТОВАРОВ ---

def is_candy_or_junk(title, weight):
    """Фильтрует штучные конфеты и печенье"""
    t_low = title.lower()
    if any(junk in t_low for junk in JUNK_IMG_WORDS): return True
    # Если вес меньше 100г - это штучная конфета, а не новогодний подарок
    if weight:
        try:
            num = float(re.sub(r'[^\d\.]', '', weight.replace(',', '.')))
            if num < 100 and ('г' in weight.lower() or 'g' in weight.lower()):
                return True
        except: pass
    return False

def download_product_image(img_url: str):
    """Качает картинку и жестко отсеивает баннеры по пропорциям"""
    try:
        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
        
        res = requests.get(img_url, headers=HEADERS, timeout=5)
        if res.status_code == 200 and len(res.content) > 4000:
            if HAS_PIL:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 150 or h < 150: return None
                
                ratio = w / h
                # КОРОБКИ: от 0.4 (высокие пакеты) до 1.5 (широкие коробки).
                # БАННЕРЫ сайта: обычно ratio > 1.8. Иконки: ratio < 0.3.
                if ratio > 1.6 or ratio < 0.4: return None
                
                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else: ext = "jpg"
            return {"bytes": res.content, "ext": ext}
    except: pass
    return None

def scan_products(domain):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    pages = [final_url]
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if any(cw in href.lower() or cw in a.get_text().lower() for cw in CATALOG_URL_WORDS):
            full = urllib.parse.urljoin(final_url, href)
            if domain in full and full not in pages: pages.append(full)
        if len(pages) >= 8: break

    raw_products = []
    
    def parse_page(p_url):
        _, p_html = get_html(p_url)
        if not p_html: return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        prods = []
        
        # Ищем контейнеры карточек
        containers = p_soup.find_all(lambda t: t.name in ["div", "li", "article"] and t.get("class") and any(c in " ".join(t.get("class")).lower() for c in ["product", "catalog-item", "card", "item"]))
        if not containers: containers = p_soup.find_all("img") # Fallback
        
        for card in containers:
            img = card if card.name == "img" else card.find("img")
            if not img: continue
            
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg", "social"]): continue
            
            full_img = urllib.parse.urljoin(p_url, src)
            text = card.get_text(" ", strip=True) if card.name != "img" else ""
            
            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None
            
            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()
            
            # Фильтр штучных конфет и мусора
            if len(title) > 2 and not is_candy_or_junk(title, weight):
                prods.append({"title": title, "weight": weight, "img_url": full_img})
        return prods

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(parse_page, pages): raw_products.extend(res)

    unique_prods, seen = [], set()
    for p in raw_products:
        if p["img_url"] not in seen:
            seen.add(p["img_url"])
            unique_prods.append(p)

    def fetch_img(p):
        img_info = download_product_image(p["img_url"])
        if img_info:
            p["img_bytes"], p["ext"] = img_info["bytes"], img_info["ext"]
            return p
        return None

    validated = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        validated = [r for r in executor.map(fetch_img, unique_prods[:40]) if r]

    return validated

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input("Введите название фабрики или её сайт:", placeholder="Например: Рубин, Академия Шоколада, lakond.ru...")

if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip(): st.stop()

    input_str = company_input.strip()
    domain = normalize_domain(input_str) if "." in input_str and " " not in input_str else find_domain_dynamic(input_str)

    if domain:
        st.success(f"🌐 Официальный сайт найден: `{domain}`")
        
        with st.spinner("ШАГ 1: Ищем официальные PDF/Excel прайсы..."):
            documents = scan_for_documents(domain)

        if documents:
            st.markdown("---")
            st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
            st.info("💡 Поиск картинок на сайте отменен, скачайте полный официальный файл.")
            for doc in documents:
                icon = "📕 PDF" if ".pdf" in doc["link"].lower() else "📊 EXCEL / DOC"
                st.markdown(f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <a href="{doc['link']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ФАЙЛ</a>
                    </div>
                """, unsafe_allow_html=True)
        else:
            with st.spinner("ШАГ 2: Файлы не найдены. Извлекаю визуальные карточки коробок с сайта..."):
                products = scan_products(domain)

            st.markdown("---")
            if products:
                st.success(f"Найдено подарочной упаковки и наборов: **{len(products)} шт.**")
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, prod in enumerate(products):
                        safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                        zf.writestr(f"box_{i+1:02d}_{safe_name}.{prod['ext']}", prod["img_bytes"])
                
                st.download_button(f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP", zip_buffer.getvalue(), f"{domain}_boxes.zip", "application/zip")
                
                st.markdown("---")
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """, unsafe_allow_html=True)
                        st.image(prod["img_bytes"], use_container_width=True)
            else:
                st.error("На сайте не удалось найти ни файлы, ни упаковку.")
    else:
        st.error("Не удалось найти сайт. Введите домен напрямую (например, rubin-2000.ru)")

st.divider()
st.caption(f"Инструмент «Первый Снег». Сезон {TARGET_YEAR}. Баннеры и штучные конфеты отсекаются автоматически.")
