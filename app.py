import io
import re
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем все предупреждения о безопасности соединений
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 РЕЕСТР ПРОИЗВОДИТЕЛЕЙ (БАЗА ЗНАНИЙ)
# =========================================================
FIXED_SITES = {
    'рубин': 'https://rubin-2000.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
    'акконд': 'https://akkond.ru',
    'славянка': 'https://slavyanka.ru',
}

# Фильтр материалов (Картон, МГК, Тубы)
WHITE_LIST = ['картон', 'мгк', 'микрогофр', 'гофр', 'переплет', 'туб', 'тубус', 'box', 'коробка', '2025', '2027']
BLACK_LIST = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак', 'logo', 'social']

# Реальные заголовки браузера для обхода блокировок
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# =========================================================
# ⚙️ ТЕХНИЧЕСКАЯ ЛОГИКА
# =========================================================

def get_soup(url):
    """Безопасная загрузка страницы с обходом защиты"""
    try:
        # Увеличиваем таймаут и отключаем проверку сертификатов
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        r.encoding = 'utf-8'
        if r.status_code == 200:
            return BeautifulSoup(r.text, 'html.parser')
    except:
        return None
    return None

def is_relevant(text, url=""):
    """Проверка материала: только картон и тубы"""
    t = (str(text) + ' ' + str(url)).lower()
    if any(b in t for b in BLACK_LIST): return False
    return any(w in t for w in WHITE_LIST)

def scan_page(url, domain):
    """Сбор PDF и Картинок с одной страницы"""
    soup = get_soup(url)
    if not soup: return [], []
    
    pdfs, imgs = [], []
    # Сбор PDF (каталоги 2027)
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().split('?')[0].endswith('.pdf'):
            txt = a.get_text().strip()
            if is_relevant(txt + href) or 'catalog' in (txt + href).lower():
                if not any(b in (txt + href).lower() for b in ['политика', 'устав']):
                    pdfs.append({'name': txt or "Каталог PDF", 'url': quote(href, safe=':/?&=#')})
    
    # Сбор Картинок (Картон / Тубы)
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or im.get('title') or '').lower()
        if is_relevant(alt + full):
            if not any(b in full.lower() for b in ['logo', 'icon', 'social', 'btn']):
                imgs.append({'name': alt or "Упаковка", 'url': quote(full, safe=':/?&=#')})
                
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Картонный Поиск 2027", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")

query = st.text_input("Введите название компании (например: Коммунарка, Рубин, Спартак):", placeholder="Коммунарка")

if query:
    q = query.lower().strip()
    
    # 1. Определяем сайт
    target_url = FIXED_SITES.get(q)
    if not target_url:
        target_url = f"https://{q.replace(' ', '-')}.ru"
    
    st.info(f"🛰 Подключение к: **{target_url}**")
    
    soup = get_soup(target_url)
    if soup:
        domain = urlparse(target_url).netloc
        
        # 2. Находим разделы
        pages = {target_url}
        for a in soup.find_all('a', href=True):
            href = urljoin(target_url, a['href']).split('#')[0]
            if urlparse(href).netloc == domain:
                if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'katalog', 'podarki', 'novogod', 'karton', 'tuba']):
                    pages.add(href)
        
        # 3. Глубокий многопоточный сбор
        with st.spinner("Сбор всех карточек товара и каталогов 2027..."):
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(scan_page, url, domain) for url in list(pages)[:30]]
                for f in as_completed(futures):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
            
            # Уникализация
            final_pdfs = list({v['url']:v for v in all_pdfs}.values())
            final_imgs = list({v['url']:v for v in all_imgs}.values())
            
            if final_pdfs or final_imgs:
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader(f"📄 PDF ({len(final_pdfs)})")
                    for p in final_pdfs: st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                    if not final_pdfs: st.write("Не найдены.")
                with c2:
                    st.subheader(f"📦 Картон / Тубы ({len(final_imgs)})")
                    if final_imgs:
                        # Создание ZIP
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(final_imgs[:400]):
                                try:
                                    res = requests.get(im['url'], timeout=5, verify=False).content
                                    zf.writestr(f"item_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(final_imgs)} фото)", zip_io.getvalue(), "packaging_archive.zip")
                        
                        grid = st.columns(3)
                        for idx, im in enumerate(final_imgs[:9]):
                            grid[idx%3].image(im['url'], use_container_width=True)
            else:
                st.warning("На сайте не найдено подходящей картонной упаковки.")
    else:
        st.error(f"❌ Сайт {target_url} не отвечает. Вероятно, он заблокировал доступ для облачного сервера. Попробуйте ввести точный адрес сайта.")
