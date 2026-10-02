import concurrent.futures
import io
import re
import urllib.parse
import zipfile
import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Отключаем мусорные уведомления
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройки производительности
MAX_PAGES = 60
THREADS = 15

# Реестр проверенных сайтов
REGISTRY = {
    "рэйд 21": "https://podarki-reid21.ru",
    "солбигтрейд": "https://конфета.бел",
    "абинекс": "https://podarok-k.ru",
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru"
}

# Ключевые слова для поиска упаковки
TARGET_KEYWORDS = ['набор', 'подарок', 'коробк', 'туб', 'тубус', 'сундуч', 'домик', 'книг', 'футляр', 'шкатулк', 'баул', 'картон', 'мгк', 'гофр', 'переплет', '2025', '2026', '2027']
# Мусорные фильтры
JUNK_FILES = ['logo', 'icon', 'social', 'banner', 'truck', 'visa', 'cart', 'header', 'footer', 'arrow', 'bg-', 'counter', 'yametrika']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# =========================================================
# ⚙️ ПРОФЕССИОНАЛЬНАЯ СЕТЕВАЯ СЕССИЯ
# =========================================================

def get_robust_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retries = Retry(total=3, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20))
    return s

SESSION = get_robust_session()

def fix_url(base, src):
    if not src: return ""
    src = src.strip()
    if src.startswith('//'): src = 'https:' + src
    try:
        full = urllib.parse.urljoin(base, src)
        p = urllib.parse.urlparse(full)
        host = p.netloc.encode('idna').decode('ascii')
        return urllib.parse.urlunparse(p._replace(netloc=host))
    except: return src

# =========================================================
# 🖼 СИСТЕМА ГАРАНТИРОВАННОГО СКАЧИВАНИЯ КАРТИНОК
# =========================================================

def download_and_fix_image(img_url, referer):
    """Качает картинку, маскируясь под внутренний переход сайта"""
    try:
        headers = dict(HEADERS)
        headers['Referer'] = referer
        
        r = SESSION.get(img_url, headers=headers, timeout=10, stream=True)
        if r.status_code != 200: return None
        
        content = r.content
        if len(content) < 3500: return None # Слишком маленькое - мусор

        # Проверка через PIL (валидация графики)
        img_bin = io.BytesIO(content)
        with Image.open(img_bin) as img:
            fmt = img.format.lower()
            if fmt == 'jpeg': fmt = 'jpg'
            # Отсекаем баннеры по пропорциям
            w, h = img.size
            if w < 120 or h < 120: return None
            if not (0.3 < w/h < 3.0): return None
            
            return {'bytes': content, 'ext': fmt}
    except:
        return None

# =========================================================
# 🕷 СКАНЕР ГЛУБОКОГО ОБХОДА
# =========================================================

def scan_page(url, base_domain):
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200: return [], [], []
        soup = BeautifulSoup(r.text, 'lxml')
    except: return [], [], []

    pdfs, imgs, nav = [], [], []

    # 1. Собираем навигацию (глубокий обход)
    for a in soup.find_all('a', href=True):
        href = fix_url(url, a['href']).split('#')[0]
        if base_domain in href:
            txt = a.get_text().lower()
            if any(w in txt or w in href.lower() for w in ['catalog', 'podarki', 'novogod', 'upakovka', 'page', 'pagen', 'p=']):
                nav.append(href)

    # 2. Собираем PDF
    for a in soup.find_all('a', href=True):
        h = fix_url(url, a['href'])
        if h.lower().split('?')[0].endswith('.pdf'):
            txt = a.get_text().strip()
            if any(w in (txt+h).lower() for w in ['каталог', 'подар', '202']):
                pdfs.append({'name': txt or "Каталог PDF", 'url': h})

    # 3. Собираем Картинки (сетка товаров)
    for img in soup.find_all(['img', 'source']):
        # Проверяем все атрибуты, включая теги товаров
        src = img.get('data-src') or img.get('data-original') or img.get('srcset') or img.get('src')
        if not src: continue
        if ',' in src: src = src.split(',')[-1].strip().split(' ')[0]
        
        full_src = fix_url(url, src)
        alt = (img.get('alt') or img.get('title') or "").strip()
        
        # Фильтр тематики
        blob = (full_src + " " + alt).lower()
        if any(j in blob for j in JUNK_FILES): continue
        if any(w in blob for w in TARGET_KEYWORDS):
            imgs.append({'name': alt or "Новогодний набор", 'url': full_src, 'referer': url})

    return pdfs, imgs, nav

def deep_crawl(start_url):
    domain = urllib.parse.urlparse(start_url).netloc
    visited = set()
    to_visit = {start_url}
    
    all_pdfs, all_imgs = [], []
    count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as ex:
        while to_visit and count < MAX_PAGES:
            batch = list(to_visit - visited)[:15]
            if not batch: break
            for u in batch: visited.add(u)
            
            futures = {ex.submit(scan_page, u, domain): u for u in batch}
            for f in concurrent.futures.as_completed(futures):
                count += 1
                try:
                    p, i, n = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
                    for link in n:
                        if link not in visited: to_visit.add(link)
                except: continue
                
    # Уникализация
    final_pdfs = list({v['url']:v for v in all_pdfs}.values())
    final_imgs = list({v['url']:v for v in all_imgs}.values())
    return final_pdfs, final_imgs, count

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Первый Снег | PRO", layout="wide", page_icon="❄️")
st.title("❄️ Профессиональный Экстрактор: Картон / МГК / Тубы 2027")

if 'data' not in st.session_state:
    st.session_state.data = None

query = st.text_input("Введите название компании (Рэйд 21, СолБигТрейд, Абинекс, Коммунарка...):")

if query:
    site = REGISTRY.get(query.lower().strip()) or f"https://{query.replace(' ', '-')}.ru"
    
    if st.button("🚀 НАЧАТЬ ГЛУБОКИЙ СБОР"):
        with st.spinner(f"Идет поиск на сайте {site}..."):
            pdfs, imgs, pages = deep_crawl(site)
            st.session_state.data = {'pdfs': pdfs, 'imgs': imgs, 'site': site}
            st.success(f"Анализ завершен! Найдено товаров: {len(imgs)}")

if st.session_state.data:
    pdfs = st.session_state.data['pdfs']
    imgs = st.session_state.data['imgs']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📄 PDF Каталоги")
        for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
        if not pdfs: st.write("Не найдены.")

    with col2:
        st.subheader(f"📦 Продукция ({len(imgs)} шт.)")
        if imgs:
            # Кнопка скачивания ZIP
            if st.button("📦 СФОРМИРОВАТЬ АРХИВ КАРТИНOK"):
                with st.spinner("Загрузка и проверка каждой картинки..."):
                    zip_io = io.BytesIO()
                    images_count = 0
                    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                            # Качаем картинки
                            img_futures = [ex.submit(download_and_fix_image, im['url'], im['referer']) for im in imgs[:400]]
                            for idx, f in enumerate(concurrent.futures.as_completed(img_futures)):
                                res = f.result()
                                if res:
                                    images_count += 1
                                    name = f"gift_{images_count:03d}.{res['ext']}"
                                    zf.writestr(name, res['bytes'])
                    
                    if images_count > 0:
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({images_count} шт.)", zip_io.getvalue(), "catalog_packaging.zip", "application/zip")
                    else:
                        st.error("Не удалось скачать ни одной картинки (возможно, защита сайта).")

            # Сетка превью
            st.write("---")
            g = st.columns(3)
            for i, im in enumerate(imgs[:12]):
                g[i%3].image(im['url'], use_container_width=True)

st.divider()
st.caption("Первый Снег PRO © 2025. Система гарантированного скачивания контента.")
