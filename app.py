import io
import zipfile
import re
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Полное отключение проверок безопасности для старых систем заводов
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 📦 СПЕЦИФИКАЦИЯ МАТЕРИАЛОВ (ТОЛЬКО КАРТОН)
# =========================================================
WHITE_LIST = ['картон', 'мгк', 'микрогофр', 'гофро', 'переплет', 'туб', 'тубус', 'tube', 'box', 'коробка', '2025', '2027', 'футляр']
BLACK_LIST = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак', 'лого', 'logo', 'social', 'vk', 'fb']

# База официальных сайтов
DIRECT_DIRECTORY = {
    'рубин': 'https://rubin-2000.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
}

# =========================================================
# 🛡 ТЕХНОЛОГИЯ "СЕТЕВОЙ МОСТ" (ОБХОД БЛОКИРОВОК)
# =========================================================

def get_content_via_bridge(url):
    """Пытается пробить защиту сайта через несколько методов"""
    # Список публичных прокси-мостов для обхода Geo-blocking
    bridges = [
        lambda u: requests.get(u, timeout=15, verify=False), # Прямой
        lambda u: requests.get(f"https://api.allorigins.win/get?url={quote(u)}", timeout=20), # Мост 1
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }
    
    for attempt, bridge in enumerate(bridges):
        try:
            r = bridge(url)
            # Если это allorigins, вынимаем данные из JSON
            if "allorigins" in r.url:
                data = r.json().get('contents', '')
                if data: return BeautifulSoup(data, 'html.parser')
            elif r.status_code == 200:
                return BeautifulSoup(r.text, 'html.parser')
        except:
            continue
    return None

def is_cardboard(text, url=""):
    """Профессиональный фильтр материала"""
    t = (str(text) + ' ' + str(url)).lower()
    if any(b in t for b in BLACK_LIST): return False
    return any(w in t for w in WHITE_LIST)

# =========================================================
# 🕷 СКАНЕР И ФИЛЬТР
# =========================================================

def scan_page(url, domain):
    soup = get_content_via_bridge(url)
    if not soup: return [], []
    
    pdfs, imgs = [], []
    # Сбор PDF 2027
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().endswith('.pdf'):
            txt = a.get_text().strip()
            if is_cardboard(txt + href) or 'catalog' in (txt+href).lower():
                pdfs.append({'name': txt or "Каталог PDF", 'url': quote(href, safe=':/?&=#')})
    
    # Сбор фото товаров (Картон/Тубы)
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or im.get('title') or '').lower()
        if is_cardboard(alt + full):
            imgs.append({'name': alt or "Картонная упаковка", 'url': quote(full, safe=':/?&=#')})
            
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Cardboard NY Finder 2027", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")
st.caption("Система обхода блокировок EAEU включена. Только картонная тара 2025-2027.")

query = st.text_input("Название компании (напр. Коммунарка, Рубин, Спартак):", placeholder="Спартак")

if query:
    q = query.lower().strip()
    target_url = DIRECT_DIRECTORY.get(q, f"https://{q.replace(' ', '-')}.by" if 'ком' in q or 'спар' in q else f"https://{q.replace(' ', '-')}.ru")
    
    st.info(f"🛰 Устанавливаем мост к: **{target_url}**")
    
    soup = get_content_via_bridge(target_url)
    if soup:
        domain = urlparse(target_url).netloc
        
        # Находим подразделы
        pages = {target_url}
        for a in soup.find_all('a', href=True):
            href = urljoin(target_url, a['href']).split('#')[0]
            if urlparse(href).netloc == domain:
                if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'novogod', 'podarki', 'karton', 'tuba', '202']):
                    pages.add(href)
        
        with st.spinner("Глубокий анализ разделов..."):
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(scan_page, url, domain) for url in list(pages)[:25]]
                for f in as_completed(futures):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
            
            pdfs = list({v['url']:v for v in all_pdfs}.values())
            imgs = list({v['url']:v for v in all_imgs}.values())
            
            if pdfs or imgs:
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader(f"📄 PDF ({len(pdfs)})")
                    for p in pdfs: st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                with c2:
                    st.subheader(f"📦 Картон / Тубы ({len(imgs)})")
                    if imgs:
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:300]):
                                try:
                                    res = requests.get(im['url'], timeout=5, verify=False).content
                                    zf.writestr(f"product_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_io.getvalue(), "packaging.zip")
                        
                        grid = st.columns(3)
                        for idx, im in enumerate(imgs[:9]): grid[idx%3].image(im['url'], use_container_width=True)
            else:
                st.warning("На сайте не найдено подходящей упаковки из картона или туб.")
    else:
        st.error(f"❌ Не удалось пробить защиту сайта {target_url}. Сайт блокирует внешние запросы.")
