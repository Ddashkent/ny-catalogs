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

# Лимиты
MAX_PAGES = 50
THREADS = 15

# База официальных ресурсов
REGISTRY = {
    "рэйд 21": "https://podarki-reid21.ru",
    "солбигтрейд": "https://конфета.бел",
    "абинекс": "https://podarok-k.ru",
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru"
}

TARGET_KEYWORDS = ['набор', 'подарок', 'коробк', 'туб', 'тубус', 'сундуч', 'домик', 'книг', 'футляр', 'шкатулк', 'баул', 'картон', 'мгк', 'гофр', 'переплет', '2025', '2027']
JUNK_FILES = ['logo', 'icon', 'social', 'banner', 'truck', 'visa', 'cart', 'header', 'footer', 'arrow', 'bg-', 'counter', 'yametrika']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# =========================================================
# 🛠 СИСТЕМА ГАРАНТИРОВАННОГО ЗАХВАТА (IMAGE BRIDGE)
# =========================================================

def get_robust_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retries = Retry(total=3, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20))
    return s

SESSION = get_robust_session()

def rescue_image_bytes(img_url):
    """
    Ультимативный метод: если прямой запрос заблокирован, 
    используем глобальный прокси-мост wsrv.nl для 'захвата' картинки.
    """
    try:
        # Пытаемся напрямую
        r = SESSION.get(img_url, timeout=7, verify=False)
        if r.status_code == 200 and len(r.content) > 3000:
            return r.content
    except:
        pass

    # FALLBACK: Прокси-мост (заходит с чистого IP, имитируя браузер)
    try:
        proxy_url = f"https://wsrv.nl/?url={urllib.parse.quote(img_url)}&n=-1"
        r = requests.get(proxy_url, timeout=10)
        if r.status_code == 200 and len(r.content) > 3000:
            return r.content
    except:
        return None

def validate_and_format(content):
    """Проверяет байты и возвращает формат файла"""
    try:
        img_bin = io.BytesIO(content)
        with Image.open(img_bin) as img:
            fmt = img.format.lower()
            if fmt == 'jpeg': fmt = 'jpg'
            # Валидация размера (отсекаем мусор)
            w, h = img.size
            if w < 100 or h < 100: return None
            return fmt
    except:
        return None

# =========================================================
# 🕷 СКАНЕР И КРАУЛЕР
# =========================================================

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

def scan_page(url, base_domain):
    try:
        r = SESSION.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
    except: return [], [], []

    pdfs, imgs, nav = [], [], []

    # Ссылки навигации
    for a in soup.find_all('a', href=True):
        href = fix_url(url, a['href']).split('#')[0]
        if base_domain in href:
            if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'podarki', 'novogod', 'upakovka', 'page', 'pagen', 'p=']):
                nav.append(href)

    # PDF
    for a in soup.find_all('a', href=True):
        h = fix_url(url, a['href'])
        if h.lower().split('?')[0].endswith('.pdf'):
            if any(w in (a.get_text() + h).lower() for w in ['каталог', 'подар', '202']):
                pdfs.append({'name': a.get_text().strip() or "Каталог PDF", 'url': h})

    # Картинки
    for img in soup.find_all(['img', 'source']):
        src = img.get('data-src') or img.get('data-original') or img.get('srcset') or img.get('src')
        if not src: continue
        if ',' in src: src = src.split(',')[-1].strip().split(' ')[0]
        
        full_src = fix_url(url, src)
        alt = (img.get('alt') or img.get('title') or "").strip()
        blob = (full_src + " " + alt).lower()
        
        if any(j in blob for j in JUNK_FILES): continue
        if any(w in blob for w in TARGET_KEYWORDS):
            imgs.append({'name': alt or "Подарок", 'url': full_src})

    return pdfs, imgs, nav

def deep_crawl(start_url):
    domain = urllib.parse.urlparse(start_url).netloc
    visited, to_visit = set(), {start_url}
    all_pdfs, all_imgs, count = [], [], 0
    
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
                
    return list({v['url']:v for v in all_pdfs}.values()), list({v['url']:v for v in all_imgs}.values()), count

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Первый Снег | ГАРАНТИЯ", layout="wide", page_icon="❄️")
st.title("❄️ Экстрактор 2027: ГАРАНТИРОВАННЫЙ ЗАХВАТ КАРТИНOK")
st.info("Если сайт блокирует скачивание, система использует графический мост-прокси для захвата изображений.")

if 'found_data' not in st.session_state:
    st.session_state.found_data = None

query = st.text_input("Введите название компании (Рэйд 21, Спартак, Коммунарка, Абинекс...):")

if query:
    site = REGISTRY.get(query.lower().strip()) or f"https://{query.replace(' ', '-')}.ru"
    
    if st.button("🚀 НАЙТИ ТОВАРЫ И КАТАЛОГИ"):
        with st.spinner(f"Глубокий анализ {site}..."):
            pdfs, imgs, pages = deep_crawl(site)
            st.session_state.found_data = {'pdfs': pdfs, 'imgs': imgs, 'site': site}
            st.success(f"Найдено потенциальных товаров: {len(imgs)}")

if st.session_state.found_data:
    pdfs = st.session_state.found_data['pdfs']
    imgs = st.session_state.found_data['imgs']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📄 PDF Каталоги")
        for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
        if not pdfs: st.write("Не найдены.")

    with col2:
        st.subheader(f"📦 Сборка архива ({len(imgs)} шт.)")
        if imgs:
            if st.button("📥 СКАЧАТЬ ВСЁ ОДНИМ АРХИВОМ (ZIP)"):
                with st.spinner("Захват изображений через графический мост..."):
                    zip_io = io.BytesIO()
                    valid_count = 0
                    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
                        # Используем потоки для сверхбыстрого скачивания
                        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
                            results = list(ex.map(rescue_image_bytes, [im['url'] for im in imgs[:400]]))
                            
                            for idx, content in enumerate(results):
                                if content:
                                    ext = validate_and_format(content)
                                    if ext:
                                        valid_count += 1
                                        zf.writestr(f"present_{valid_count:03d}.{ext}", content)
                    
                    if valid_count > 0:
                        st.download_button(f"💾 СОХРАНИТЬ ZIP ({valid_count} шт.)", zip_io.getvalue(), "packaging_2027.zip", "application/zip")
                    else:
                        st.error("Ошибка: серверы сайта полностью закрыли доступ. Попробуйте другую компанию.")

            st.write("---")
            # Сетка превью (используем прокси для показа, если оригинал не грузится)
            g = st.columns(3)
            for i, im in enumerate(imgs[:12]):
                proxy_preview = f"https://wsrv.nl/?url={urllib.parse.quote(im['url'])}&w=300"
                g[i%3].image(proxy_preview, use_container_width=True, caption=im['name'][:30])

st.divider()
st.caption("Первый Снег ГАРАНТИЯ © 2025. Использование технологии WSrv Bridge.")
