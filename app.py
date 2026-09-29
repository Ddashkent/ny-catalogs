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

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; font-size: 15px; padding: 10px 20px;
        border-radius: 8px; border: 2px solid white;
        box-shadow: 0 4px 15px rgba(220,38,38,0.4);
        letter-spacing: 1px;
    }
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.3; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #93c5fd; pointer-events: none; z-index: 0; opacity: 0.2; }
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
    <div class="flake" style="left:15%; animation: snowfall 18s linear infinite;">❄</div>
    <div class="flake" style="left:50%; animation: snowfall 22s linear infinite 4s;">❅</div>
    <div class="flake" style="left:85%; animation: snowfall 20s linear infinite 2s;">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Анализ Картонной Упаковки {TARGET_YEAR}")
st.caption("Глубокий сканер: находит новогодние разделы на любом сайте и выгружает всё.")

# -----------------------------
# БАЗА И ФИЛЬТРЫ
# -----------------------------

SITES = {
    "акконд": "akkond.ru", "спартак": "spartak.by", "рубин": "rubin-2000.ru",
    "рэйд": "podarki-reid21.ru", "академия шоколада": "chocolate-academy.ru",
    "коммунарка": "kommunarka.by", "лаконд": "lakond.ru"
}

BAD_FILES = ["презентация", "соглашение", "политика", "договор", "реквизиты", "вакансии"]
BAD_IMAGES = ["logo", "icon", "banner", "slider", "bg-", "social", "vk", "payment", "delivery"]
TEXTILE_JUNK = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "кофр", "пуф"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def normalize_domain(name):
    n = name.lower().strip()
    for k, v in SITES.items():
        if k in n: return v
    if "." in n and " " not in n: return n.replace("https://", "").replace("http://", "").split("/")[0]
    return None

def get_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_all_catalog_links(base_url, domain):
    """Заходит на сайт и находит все ссылки на 'Новый год' и 'Каталог'"""
    final_url, html = get_page(base_url)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    found = {final_url}
    
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        full = urllib.parse.urljoin(final_url, a['href'])
        
        if domain in full:
            # Ищем маркеры каталога или подарков
            if any(kw in href or kw in text for kw in ["подар", "новогод", "нг", "catalog", "katalog", "produk", "лошад", "2026"]):
                # Но не заходим в новости и оплату
                if not any(bad in href or bad in text for bad in ["news", "novosti", "oplata", "dostavka", "about"]):
                    found.add(full)
        if len(found) > 10: break
    return list(found)

def extract_from_pages(urls):
    """Собирает PDF и Картинки со всех найденных страниц сразу"""
    all_docs, all_items = [], []
    seen_files, seen_imgs = set(), set()

    def parse(url):
        p_docs, p_items = [], []
        curr_url, html = get_page(url)
        if not html: return [], []
        
        soup = BeautifulSoup(html, "html.parser")
        # Убираем мусор из кода
        for junk in soup.find_all(re.compile(r'footer|header|partners|slider', re.I)): junk.decompose()

        # 1. Сбор PDF
        for a in soup.find_all("a", href=True):
            href, text = a['href'].lower(), a.get_text().strip().lower()
            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                if any(bad in text or bad in href for bad in BAD_FILES): continue
                full = urllib.parse.urljoin(curr_url, a['href'])
                p_docs.append({"title": a.get_text().strip() or "Файл каталога", "url": full})

        # 2. Сбор Карточек
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in BAD_IMAGES): continue
            
            full_img = urllib.parse.urljoin(curr_url, src)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img) # Качество
            
            text_context = (img.get("alt", "") + " " + (img.parent.get_text() if img.parent else "")).lower()
            if any(bad in text_context for bad in TEXTILE_JUNK + BAD_IMAGES): continue
            
            p_items.append({"title": (img.get("alt") or "Упаковка").strip(), "url": full_img})
        
        return p_docs, p_items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(parse, urls)
        for d, i in results:
            for item in d:
                if item['url'] not in seen_files:
                    seen_files.add(item['url']); all_docs.append(item)
            for item in i:
                if item['url'] not in seen_imgs:
                    seen_imgs.add(item['url']); all_items.append(item)
                    
    return all_docs, all_items

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Название фабрики или сайт:", placeholder="Например: Спартак или rubin-2000.ru")

if st.button("🚀 НАЙТИ ВСЁ", type="primary", use_container_width=True):
    if query:
        domain = normalize_domain(query)
        if domain:
            st.success(f"🌐 Подключено к: `{domain}`")
            
            with st.status("Глубокий поиск разделов и файлов...", expanded=True) as status:
                st.write("🔎 Исследую структуру сайта...")
                target_links = find_all_catalog_links(f"https://{domain}", domain)
                st.write(f"Найдено разделов для проверки: {len(target_links)}")
                
                st.write("📥 Выгружаю данные...")
                docs, items = extract_from_pages(target_links)
                status.update(label="Поиск завершен!", state="complete")

            if docs:
                st.subheader("📄 Официальные файлы (PDF/Excel):")
                for d in docs: st.markdown(f'<div class="doc-card"><b>{d["title"]}</b><br><a href="{d["url"]}" target="_blank">📥 СКАЧАТЬ ФАЙЛ</a></div>', unsafe_allow_html=True)
            
            if items:
                st.subheader(f"🖼️ Картонная упаковка и наборы ({len(items)} шт.)")
                
                # ZIP
                zip_buf = io.BytesIO()
                valid_items = []
                with st.spinner("Загружаю изображения для архива..."):
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for i, it in enumerate(items[:100]):
                            try:
                                r = requests.get(it['url'], timeout=5, verify=False)
                                if r.status_code == 200 and len(r.content) > 4000:
                                    if HAS_PIL:
                                        img_pil = Image.open(io.BytesIO(r.content))
                                        w, h = img_pil.size
                                        if 0.4 < (w/h) < 1.7: # Фильтр коробок
                                            zf.writestr(f"box_{i+1:02d}.jpg", r.content)
                                            it['bytes'] = r.content
                                            valid_items.append(it)
                            except: pass
                
                if valid_items:
                    st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), f"{domain}_boxes.zip", "application/zip")
                    st.markdown("---")
                    cols = st.columns(4)
                    for i, it in enumerate(valid_items[:40]):
                        with cols[i % 4]:
                            st.markdown('<div class="product-card">', unsafe_allow_html=True)
                            st.image(it['bytes'], use_container_width=True)
                            st.markdown(f'<small>{it["title"][:50]}</small></div>', unsafe_allow_html=True)
                else:
                    st.warning("Прямых фото коробок не найдено, проверьте PDF-файлы.")
            
            if not docs and not items:
                st.error("Ничего не найдено. Попробуйте ввести точный домен сайта (например, lakond.ru)")
        else:
            st.error("Сайт не найден. Попробуйте ввести его вручную (например: rubin-2000.ru)")
