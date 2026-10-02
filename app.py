import concurrent.futures
import io
import re
import zipfile
import datetime
import urllib.parse
from bs4 import BeautifulSoup
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
import streamlit as st
import urllib3
from urllib3.util.retry import Retry

# Отключение уведомлений SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# ⚙️ НАСТРОЙКИ ГЛУБИНЫ И ФИЛЬТРОВ
# =========================================================
MAX_SCAN_PAGES = 60  # Глубокое сканирование
THREADS = 10         # Высокая скорость

# Материалы и типы (Целевые)
TARGET_KEYWORDS = ['набор', 'подарок', 'коробк', 'туб', 'тубус', 'сундуч', 'домик', 'книг', 'футляр', 'шкатулк', 'баул', 'картон', 'мгк', 'микрогофр', 'гофр', 'переплет', '2025', '2027']
# Исключения (Мусор)
JUNK_WORDS = ['доставка', 'условия', 'banner', 'logo', 'icon', 'social', 'delivery', 'truck', 'телефон', 'header', 'footer', 'плитка', 'батончик', 'конфета на вес']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}

# =========================================================
# 🛠 СЕТЕВОЙ МОДУЛЬ
# =========================================================

def build_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.mount('http://', HTTPAdapter(max_retries=retry))
    return s

SESSION = build_session()

def fix_url(base, src):
    try:
        if not src: return ""
        if src.startswith('//'): src = 'https:' + src
        full = urllib.parse.urljoin(base, src)
        p = urllib.parse.urlparse(full)
        host = p.netloc.encode('idna').decode('ascii')
        path = urllib.parse.quote(urllib.parse.unquote(p.path))
        query = urllib.parse.quote(urllib.parse.unquote(p.query), safe='=&')
        return urllib.parse.urlunparse(p._replace(netloc=host, path=path, query=query))
    except: return src

def safe_fetch(url):
    try:
        r = SESSION.get(url, timeout=12, verify=False)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text, r.url
    except: pass
    return None, url

# =========================================================
# 🔍 ПОИСКОВИК САЙТОВ (УМНЫЙ)
# =========================================================

def perform_search(query):
    """Ищет официальный сайт через публичные поисковые шлюзы"""
    candidates = []
    # Поиск через Mojeek и DDG
    for q in [f'"{query}" официальный сайт новогодние подарки', f'{query} каталог подарков']:
        try:
            u = f"https://www.mojeek.com/search?q={urllib.parse.quote(q)}"
            r = SESSION.get(u, timeout=10)
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('http') and not any(x in href.lower() for x in ['yandex', 'google', 'vk.com', 'wikipedia', 'avito', 'ozon']):
                    p = urllib.parse.urlparse(href)
                    candidates.append(f"{p.scheme}://{p.netloc}")
        except: pass
    return list(dict.fromkeys(candidates))

# =========================================================
# 🕷 ГЛУБОКИЙ КРАУЛЕР
# =========================================================

def is_valid_gift(title, url, context=""):
    blob = (str(title) + " " + str(url) + " " + str(context)).lower().replace('ё', 'е')
    if any(j in blob for j in JUNK_WORDS): return False
    return any(t in blob for t in TARGET_KEYWORDS)

def extract_images_from_page(url):
    html, final_url = safe_fetch(url)
    if not html: return [], [], []
    
    soup = BeautifulSoup(html, 'lxml')
    domain = urllib.parse.urlparse(final_url).netloc
    
    # 1. Поиск новых ссылок (пагинация и категории)
    links = []
    for a in soup.find_all('a', href=True):
        href = fix_url(final_url, a['href'])
        if domain in href:
            txt = a.get_text().lower()
            if any(w in txt or w in href.lower() for w in ['catalog', 'podarki', 'novogod', 'category', 'page', 'upakovka']):
                links.append(href.split('#')[0])

    # 2. Поиск PDF
    pdfs = []
    for a in soup.find_all('a', href=True):
        h = fix_url(final_url, a['href'])
        if h.lower().split('?')[0].endswith('.pdf'):
            name = a.get_text().strip()
            if any(w in (name+h).lower() for w in ['каталог', 'подар', '202', 'price']):
                pdfs.append({'name': name or "PDF Каталог", 'url': h})

    # 3. Поиск Изображений продукции
    imgs = []
    # Ищем картинки в контейнерах, которые похожи на карточки товаров
    for container in soup.find_all(['div', 'li', 'article']):
        container_class = str(container.get('class', '')).lower()
        if any(c in container_class for c in ['product', 'item', 'card', 'goods']):
            img_tag = container.find('img')
            if img_tag:
                src = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or img_tag.get('data-original')
                if src:
                    f_src = fix_url(final_url, src)
                    alt = (img_tag.get('alt') or img_tag.get('title') or "").strip()
                    if is_valid_gift(alt, f_src, container.get_text()):
                        imgs.append({'name': alt or "Подарок", 'url': f_src})

    # Доп. поиск по всем картинкам, если в карточках пусто
    if not imgs:
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if not src: continue
            f_src = fix_url(final_url, src)
            alt = (img.get('alt') or "").strip()
            if is_valid_gift(alt, f_src):
                imgs.append({'name': alt or "Новогодний набор", 'url': f_src})

    return list({v['url']:v for v in pdfs}.values()), list({v['url']:v for v in imgs}.values()), list(set(links))

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Первый Снег | Глубокий поиск", layout="wide", page_icon="❄️")
st.title("❄️ Профессиональный Экстрактор Подарков (Глубокий анализ)")

query = st.text_input("Введите название компании (например: Рэйд 21, СолБигТрейд, Абинекс):")

if query:
    # 1. Поиск сайта
    with st.spinner(f"🔎 Ищем официальный сайт для «{query}»..."):
        # Прямой реестр для скорости
        registry = {"рэйд 21": "https://podarki-reid21.ru", "солбигтрейд": "https://конфета.бел", "абинекс": "https://abinex.ru", "коммунарка": "https://www.kommunarka.by", "спартак": "https://spartak.by"}
        
        target_site = registry.get(query.lower().strip())
        if not target_site:
            candidates = perform_search(query)
            if candidates: target_site = candidates[0]
            else: target_site = f"https://{query.replace(' ', '-')}.ru"

    st.success(f"🌐 Работаем с сайтом: **[{target_site}]({target_site})**")

    # 2. Глубокое сканирование (Рекурсия на 2 уровня)
    with st.spinner("📦 Глубокое сканирование категорий и карточек товара..."):
        all_pdfs, all_imgs = [], []
        
        # Уровень 1 (Главная)
        p1, i1, links = extract_images_from_page(target_site)
        all_pdfs.extend(p1)
        all_imgs.extend(i1)
        
        # Уровень 2 (Разделы каталога)
        scan_queue = list(set(links))[:MAX_SCAN_PAGES]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_to_url = {executor.submit(extract_images_from_page, url): url for url in scan_queue}
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    p, i, _ = future.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
                except: continue

        pdfs = list({v['url']:v for v in all_pdfs}.values())
        imgs = list({v['url']:v for v in all_imgs}.values())

        # ВЫВОД РЕЗУЛЬТАТОВ
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"📄 PDF Каталоги ({len(pdfs)})")
            if pdfs:
                for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
            else: st.info("PDF не найдены.")

        with col2:
            st.subheader(f"📦 Подарочные наборы ({len(imgs)})")
            if imgs:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx, im in enumerate(imgs[:500]):
                        try:
                            res = requests.get(im['url'], timeout=5, verify=False).content
                            if len(res) < 5000: continue # Игнорируем иконки
                            ext = im['url'].split('.')[-1][:3]
                            if ext not in ['jpg', 'png', 'web']: ext = 'jpg'
                            zf.writestr(f"gift_{idx+1}.{ext}", res)
                        except: continue
                
                st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_buf.getvalue(), "catalog_deep.zip", type="primary")
                
                grid = st.columns(3)
                for idx, im in enumerate(imgs[:12]):
                    grid[idx%3].image(im['url'], caption=im['name'][:40], use_container_width=True)
            else: st.info("Товары не найдены. Попробуйте уточнить название.")

st.divider()
st.caption("Инструмент «Первый Снег» | Глубокий обход категорий | Сезон 2025-2027")
