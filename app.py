import concurrent.futures
import io
import re
import zipfile
import datetime
import urllib.parse
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
import streamlit as st
import urllib3
from urllib3.util.retry import Retry

# Глубокие настройки
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
MAX_DEPTH_PAGES = 100 # Лимит страниц для полной выгрузки
THREADS = 15          # Максимальная скорость

# Реестр для мгновенного входа
REGISTRY = {
    "рэйд 21": "https://podarki-reid21.ru",
    "солбигтрейд": "https://конфета.бел",
    "абинекс": "https://podarok-k.ru",
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru"
}

# Ключевые слова для поиска (Белый список)
TARGET_WORDS = ['набор', 'подарок', 'коробк', 'туб', 'тубус', 'сундуч', 'домик', 'книг', 'футляр', 'шкатулк', 'баул', 'картон', 'мгк', 'гофр', 'переплет', '2025', '2026', '2027']
# Мусор (Черный список)
JUNK_FILES = ['logo', 'icon', 'social', 'banner', 'delivery', 'truck', 'visa', 'mastercard', 'cart', 'header', 'footer', 'arrow', 'slider', 'bg-']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

# =========================================================
# ⚙️ СЕТЕВАЯ ИНЖЕНЕРИЯ
# =========================================================

def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
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
# 🕷 ГЛУБОКИЙ КРАУЛЕР (DEEP SCAN)
# =========================================================

def is_useful(url, text=""):
    t = (str(url) + " " + str(text)).lower()
    if any(j in t for j in JUNK_FILES): return False
    return any(w in t for w in TARGET_WORDS)

def scan_page(url, base_domain):
    """Парсит страницу: извлекает товары и находит ссылки на пагинацию/категории"""
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code != 200: return [], [], []
        soup = BeautifulSoup(r.text, 'lxml')
    except: return [], [], []

    pdfs, imgs, nav_links = [], [], []

    # 1. Собираем навигацию (категории, страницы 1,2,3...)
    for a in soup.find_all('a', href=True):
        href = fix_url(url, a['href'])
        clean_href = href.split('#')[0]
        if base_domain in clean_href:
            link_text = a.get_text().lower()
            # Если ссылка похожа на категорию или пагинацию
            if any(w in link_text or w in clean_href for w in ['catalog', 'podarki', 'novogod', 'upakovka', 'page', 'pagen', 'p=']):
                nav_links.append(clean_href)

    # 2. Собираем PDF
    for a in soup.find_all('a', href=True):
        h = fix_url(url, a['href'])
        if h.lower().split('?')[0].endswith('.pdf'):
            if is_useful(h, a.get_text()):
                pdfs.append({'name': a.get_text().strip() or "Каталог PDF", 'url': h})

    # 3. Собираем изображения продукции (умный поиск)
    # Ищем во всех тегах, которые могут содержать картинку товара
    for img in soup.find_all(['img', 'source']):
        # Проверяем все возможные атрибуты источника
        src = img.get('data-src') or img.get('data-original') or img.get('srcset') or img.get('src') or img.get('data-lazy')
        if not src: continue
        # Если это srcset, берем последнюю (самую большую) картинку
        if ',' in src: src = src.split(',')[-1].strip().split(' ')[0]
        
        f_src = fix_url(url, src)
        alt = (img.get('alt') or img.get('title') or "").strip()
        
        if is_useful(f_src, alt):
            imgs.append({'name': alt or "Новогодний товар", 'url': f_src})

    return pdfs, imgs, nav_links

def deep_crawl(start_url):
    base_domain = urllib.parse.urlparse(start_url).netloc
    
    visited = set()
    to_visit = {start_url}
    
    all_pdfs = []
    all_imgs = []
    
    pages_count = 0
    
    # Рекурсивный обход в ширину через ThreadPool
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        while to_visit and pages_count < MAX_DEPTH_PAGES:
            # Берем пачку ссылок для сканирования
            current_batch = list(to_visit - visited)[:20]
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
            # Обновляем прогресс в Streamlit
            st.toast(f"Просканировано страниц: {pages_count}...", icon="🔎")

    # Чистим дубликаты
    final_pdfs = list({v['url']:v for v in all_pdfs}.values())
    final_imgs = list({v['url']:v for v in all_imgs}.values())
    
    return final_pdfs, final_imgs, pages_count

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Deep Explorer 2027", layout="wide", page_icon="❄️")
st.title("❄️ Первый Снег: Глубокий Рекурсивный Экстрактор")
st.caption("Полный обход всех категорий, пагинаций и карточек товара. Заходит в самые глубокие разделы сайта.")

query = st.text_input("Введите название компании (напр. Рэйд 21, Абинекс, Спартак):", placeholder="Рэйд 21")

if query:
    target_site = REGISTRY.get(query.lower().strip())
    if not target_site:
        target_site = f"https://{query.replace(' ', '-')}.ru" # Фолбэк

    st.info(f"🚀 Запускаем глубокий поиск по адресу: **{target_site}**")

    # Запуск краулера
    pdfs, imgs, total_p = deep_crawl(target_site)

    if not pdfs and not imgs:
        st.error("❌ Ничего не найдено. Проверьте правильность названия или доступность сайта.")
    else:
        st.success(f"✅ Глубокий анализ завершен. Обработано страниц: **{total_p}**")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"📄 Каталоги PDF ({len(pdfs)})")
            if pdfs:
                for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
            else: st.write("Не найдены.")

        with c2:
            st.subheader(f"📦 Подарки и Упаковка ({len(imgs)})")
            if imgs:
                # Генерация архива
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Скачиваем реально найденные картинки
                    for idx, im in enumerate(imgs[:500]): # Лимит 500 для ZIP
                        try:
                            # Проверка размера перед добавлением
                            r = SESSION.get(im['url'], timeout=5).content
                            if len(r) > 5000: # Игнорируем мелкие иконки
                                ext = im['url'].split('.')[-1][:3]
                                if ext not in ['jpg', 'png', 'web']: ext = 'jpg'
                                zf.writestr(f"item_{idx+1}.{ext}", r)
                        except: continue
                
                st.download_button(f"📥 СКАЧАТЬ ПОЛНЫЙ АРХИВ ({len(imgs)} шт.)", zip_io.getvalue(), "deep_catalog.zip", type="primary")
                
                # Галерея превью
                st.write("---")
                grid = st.columns(4)
                for i, im in enumerate(imgs[:16]): # Показываем первые 16
                    grid[i%4].image(im['url'], caption=im['name'][:30], use_container_width=True)
            else:
                st.write("Изображения товаров не найдены.")

st.divider()
st.caption("Deep-Dive Technology © 2025. Спроектировано для обхода сложных структур каталогов.")
