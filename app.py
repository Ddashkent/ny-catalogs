import concurrent.futures
import io
import re
import urllib.parse
import zipfile
import requests
from bs4 import BeautifulSoup
from PIL import Image
from requests.adapters import HTTPAdapter
import streamlit as st
import urllib3
from urllib3.util.retry import Retry

# Отключение уведомлений SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_DEPTH_PAGES = 80
THREADS = 10

REGISTRY = {
    "рэйд 21": "https://podarki-reid21.ru",
    "солбигтрейд": "https://конфета.бел",
    "абинекс": "https://podarok-k.ru",
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru"
}

TARGET_WORDS = ['набор', 'подарок', 'коробк', 'туб', 'тубус', 'сундуч', 'домик', 'книг', 'футляр', 'шкатулк', 'баул', 'картон', 'мгк', 'гофр', 'переплет', '2025', '2026', '2027']
JUNK_FILES = ['logo', 'icon', 'social', 'banner', 'delivery', 'truck', 'visa', 'mastercard', 'cart', 'header', 'footer', 'arrow', 'slider', 'bg-']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ
# =========================================================

def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    return s

SESSION = get_session()

def fix_url(base, src):
    if not src: return ""
    src = src.strip()
    if src.startswith('//'): src = 'https:' + src
    try:
        full = urllib.parse.urljoin(base, src)
        p = urllib.parse.urlparse(full)
        host = p.netloc.encode('idna').decode('ascii')
        path = urllib.parse.quote(urllib.parse.unquote(p.path))
        query = urllib.parse.quote(urllib.parse.unquote(p.query), safe='=&?')
        return urllib.parse.urlunparse(p._replace(netloc=host, path=path, query=query))
    except: return src

# =========================================================
# 🖼 ВАЛИДАТОР ИЗОБРАЖЕНИЙ (ГАРАНТИЯ ОТКРЫТИЯ В ZIP)
# =========================================================

def fetch_and_validate_image(img_info, referer_url):
    """Качает байты, проверяет через PIL и возвращает ТОЛЬКО валидную картинку"""
    try:
        url = img_info['url']
        headers = dict(HEADERS)
        headers['Referer'] = referer_url
        
        r = SESSION.get(url, headers=headers, timeout=8, verify=False)
        if r.status_code != 200 or len(r.content) < 3000:
            return None

        # Проверка байтов через PIL (если битый файл или HTML - вызовет исключение)
        image_stream = io.BytesIO(r.content)
        img = Image.open(image_stream)
        w, h = img.size
        
        # Отсекаем иконки и странные пропорции (баннеры)
        if w < 100 or h < 100: return None
        ratio = w / h
        if ratio > 2.5 or ratio < 0.3: return None
        
        # Определяем РЕАЛЬНОЕ расширение
        fmt = (img.format or 'JPEG').lower()
        ext = 'jpg' if fmt == 'jpeg' else fmt
        if ext not in ['jpg', 'png', 'webp']: ext = 'jpg'
        
        return {
            'bytes': r.content,
            'ext': ext,
            'name': img_info['name']
        }
    except Exception:
        return None

# =========================================================
# 🕷 КРАУЛЕР
# =========================================================

def is_useful(url, text=""):
    t = (str(url) + " " + str(text)).lower()
    if any(j in t for j in JUNK_FILES): return False
    return any(w in t for w in TARGET_WORDS)

def scan_page(url, base_domain):
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200: return [], [], []
        soup = BeautifulSoup(r.text, 'lxml')
    except: return [], [], []

    pdfs, imgs, nav_links = [], [], []

    # Навигация
    for a in soup.find_all('a', href=True):
        href = fix_url(url, a['href'])
        clean_href = href.split('#')[0]
        if base_domain in clean_href:
            link_text = a.get_text().lower()
            if any(w in link_text or w in clean_href for w in ['catalog', 'podarki', 'novogod', 'upakovka', 'page', 'pagen', 'p=']):
                nav_links.append(clean_href)

    # PDF
    for a in soup.find_all('a', href=True):
        h = fix_url(url, a['href'])
        if h.lower().split('?')[0].endswith('.pdf'):
            if is_useful(h, a.get_text()):
                pdfs.append({'name': a.get_text().strip() or "Каталог PDF", 'url': h})

    # Изображения
    for img in soup.find_all(['img', 'source']):
        src = img.get('data-src') or img.get('data-original') or img.get('srcset') or img.get('src') or img.get('data-lazy')
        if not src: continue
        if ',' in src: src = src.split(',')[-1].strip().split(' ')[0]
        
        f_src = fix_url(url, src)
        alt = (img.get('alt') or img.get('title') or "").strip()
        
        if is_useful(f_src, alt):
            imgs.append({'name': alt or "Новогодний товар", 'url': f_src, 'page_url': url})

    return pdfs, imgs, nav_links

def deep_crawl(start_url):
    base_domain = urllib.parse.urlparse(start_url).netloc
    visited = set()
    to_visit = {start_url}
    
    all_pdfs, all_imgs = [], []
    pages_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        while to_visit and pages_count < MAX_DEPTH_PAGES:
            current_batch = list(to_visit - visited)[:15]
            if not current_batch: break
            
            for url in current_batch: visited.add(url)
            
            future_to_url = {executor.submit(scan_page, url, base_domain): url for url in current_batch}
            new_links = set()
            
            for future in concurrent.futures.as_completed(future_to_url):
                pages_count += 1
                try:
                    p, i, l = future.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
                    for link in l:
                        if link not in visited: new_links.add(link)
                except: continue
            
            to_visit.update(new_links)

    final_pdfs = list({v['url']:v for v in all_pdfs}.values())
    final_imgs = list({v['url']:v for v in all_imgs}.values())
    
    return final_pdfs, final_imgs, pages_count

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Первый Снег | Экстрактор", layout="wide", page_icon="❄️")
st.title("❄️ Первый Снег: Валидированный Поисковик Подарков")

query = st.text_input("Введите название компании (напр. Рэйд 21, Абинекс, Спартак):", placeholder="Рэйд 21")

if query:
    target_site = REGISTRY.get(query.lower().strip())
    if not target_site:
        target_site = f"https://{query.replace(' ', '-')}.ru"

    st.info(f"🚀 Сканируем сайт: **{target_site}**")

    with st.spinner("Идет глубокий обход страниц..."):
        pdfs, imgs, total_p = deep_crawl(target_site)

    if not pdfs and not imgs:
        st.error("❌ Ничего не найдено. Проверьте адрес сайта.")
    else:
        st.success(f"✅ Обработано страниц: **{total_p}**. Найдено карточек: **{len(imgs)}**")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"📄 Каталоги PDF ({len(pdfs)})")
            if pdfs:
                for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
            else: st.write("PDF не найдены.")

        with c2:
            st.subheader(f"📦 Наборы и Упаковка ({len(imgs)})")
            if imgs:
                # ВАЛИДАЦИЯ И СБОРКА ZIP В МНОГОПОТОЧНОМ РЕЖИМЕ
                with st.spinner("Проверяем целостность картинок и формируем ZIP..."):
                    valid_images = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
                        futures = [ex.submit(fetch_and_validate_image, img, target_site) for img in imgs[:350]]
                        for f in concurrent.futures.as_completed(futures):
                            res = f.result()
                            if res: valid_images.append(res)

                    zip_io = io.BytesIO()
                    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
                        for idx, valid_img in enumerate(valid_images, start=1):
                            # Безопасное имя файла
                            clean_title = re.sub(r'[^\w\s-]', '', valid_img['name'])[:30].strip()
                            safe_filename = f"box_{idx:03d}_{clean_title or 'item'}.{valid_img['ext']}"
                            zf.writestr(safe_filename, valid_img['bytes'])

                st.download_button(
                    f"📥 СКАЧАТЬ ВАЛИДНЫЙ ZIP-АРХИВ ({len(valid_images)} шт.)", 
                    zip_io.getvalue(), 
                    "valid_packaging_catalog.zip", 
                    mime="application/zip",
                    type="primary"
                )
                
                st.write("---")
                grid = st.columns(4)
                for i, im in enumerate(imgs[:12]):
                    grid[i%4].image(im['url'], caption=im['name'][:25], use_container_width=True)
            else:
                st.write("Изображения не найдены.")

st.divider()
st.caption("Инструмент «Первый Снег» | 100% Валидация байтов через PIL")
