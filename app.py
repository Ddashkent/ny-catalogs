import io
import zipfile
import re
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем мусорные уведомления
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 📦 БАЗА ДАННЫХ И ПРАВИЛА (ТОЛЬКО КАРТОН И ТУБЫ)
# =========================================================
TRUSTED_SITES = {
    'рубин': 'https://rubin-2000.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'акконд': 'https://akkond.ru'
}

# Белый список: забираем только это
WHITE_LIST = ['картон', 'мгк', 'микрогофр', 'гофр', 'переплет', 'туб', 'тубус', 'box', 'коробка', 'книга', '2025', '2027']
# Черный список: это нам не нужно
BLACK_LIST = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак', 'logo', 'social', 'header', 'footer']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# =========================================================
# 🛡 ТЕХНОЛОГИЯ ПРОРЫВА (PROXY BRIDGE)
# =========================================================

def get_html_via_bridge(url):
    """Пытается получить код страницы напрямую или через прокси-мост"""
    # 1. Прямая попытка
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if r.status_code == 200:
            return BeautifulSoup(r.text, 'html.parser')
    except: pass

    # 2. Попытка через прокси-мост AllOrigins (обход Geo-blocking)
    try:
        proxy_url = f"https://api.allorigins.win/get?url={quote(url)}"
        r = requests.get(proxy_url, timeout=15)
        if r.status_code == 200:
            content = r.json().get('contents')
            return BeautifulSoup(content, 'html.parser')
    except: pass
    
    return None

def is_valid_material(text, url=""):
    """Проверка: картон/туба или мусор"""
    t = (str(text) + ' ' + str(url)).lower()
    if any(b in t for b in BLACK_LIST): return False
    return any(w in t for w in WHITE_LIST)

# =========================================================
# 🕷 СКАНЕР И КРАУЛЕР
# =========================================================

def scan_page(url, domain):
    soup = get_html_via_bridge(url)
    if not soup: return [], []
    
    pdfs, imgs = [], []
    # Сбор PDF (каталоги)
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().endswith('.pdf'):
            txt = a.get_text().strip()
            if is_valid_material(txt + href) or 'catalog' in (txt + href).lower():
                pdfs.append({'name': txt or "Каталог PDF", 'url': quote(href, safe=':/?&=#')})
    
    # Сбор Картинок (только картон/тубы)
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or im.get('title') or '').lower()
        if is_valid_material(alt + full):
            imgs.append({'name': alt or "Картонная упаковка", 'url': quote(full, safe=':/?&=#')})
            
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Картонный Поиск 2027", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")
st.caption("Система обхода блокировок ЕАЭС активна. Автоматический отсев жести и игрушек.")

query = st.text_input("Введите название компании (Спартак, Коммунарка, Рубин...):", placeholder="Коммунарка")

if query:
    q = query.lower().strip()
    
    # Резолвинг сайта
    target_url = TRUSTED_SITES.get(q)
    if not target_url:
        target_url = f"https://{q.replace(' ', '-')}.ru"
    
    st.info(f"🛰 Устанавливаем соединение с: **{target_url}**")
    
    soup = get_html_via_bridge(target_url)
    
    if soup:
        domain = urlparse(target_url).netloc
        
        # Находим разделы каталога
        pages = {target_url}
        for a in soup.find_all('a', href=True):
            href = urljoin(target_url, a['href']).split('#')[0]
            if urlparse(href).netloc == domain:
                if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'katalog', 'podarki', 'novogod', 'karton', 'tuba']):
                    pages.add(href)
        
        with st.spinner("Глубокий анализ разделов на наличие картона и туб..."):
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(scan_page, url, domain) for url in list(pages)[:25]]
                for f in as_completed(futures):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
            
            # Убираем дубли
            final_pdfs = list({v['url']:v for v in all_pdfs}.values())
            final_imgs = list({v['url']:v for v in all_imgs}.values())
            
            if final_pdfs or final_imgs:
                c1, c2 = st.columns(2)
                
                with c1:
                    st.subheader(f"📄 PDF Каталоги ({len(final_pdfs)})")
                    for p in final_pdfs:
                        st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                    if not final_pdfs: st.write("Каталоги не найдены.")
                
                with c2:
                    st.subheader(f"🖼 Фото упаковки ({len(final_imgs)})")
                    if final_imgs:
                        # Создание ZIP
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(final_imgs[:350]):
                                try:
                                    res = requests.get(im['url'], timeout=5, verify=False).content
                                    zf.writestr(f"product_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(final_imgs)} шт.)", zip_io.getvalue(), "packaging.zip")
                        
                        # Превью
                        grid = st.columns(3)
                        for idx, im in enumerate(final_imgs[:9]):
                            grid[idx%3].image(im['url'], use_container_width=True)
                    else:
                        st.write("Изображения картонной упаковки не найдены.")
            else:
                st.warning("На сайте не найдено подходящих товаров в картонной упаковке или тубах.")
    else:
        st.error(f"❌ Сайт {target_url} полностью заблокировал доступ для облачного сервера. Рекомендуется открыть его вручную.")
