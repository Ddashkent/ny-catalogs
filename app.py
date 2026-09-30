import io
import zipfile
import re
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Выключаем бесполезные алерты
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 РЕЕСТР И ФИЛЬТРЫ
# =========================================================
DIRECTORY = {
    'рубин': 'https://rubin-2000.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'академия шоколада': 'https://academy-chocolate.ru',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'акконд': 'https://akkond.ru'
}

# Только то, что нужно тебе
CARDBOARD_ONLY = ['картон', 'мгк', 'гофр', 'переплет', 'туб', 'тубус', 'box', 'коробка', '2025', '2027']
# То, что мы ненавидим в этой задаче
GARBAGE = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак', 'logo', 'social']

def get_session():
    s = requests.Session()
    s.verify = False
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive'
    })
    return s

# =========================================================
# ⚙️ ТЕХНИЧЕСКОЕ ЯДРО
# =========================================================

def translit(text):
    d = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return "".join(d.get(c, c) for c in text.lower()).replace(" ", "-")

def check_content(text, url=""):
    t = (str(text) + ' ' + str(url)).lower()
    if any(g in t for g in GARBAGE): return False
    return any(c in t for c in CARDBOARD_ONLY)

def scan_page(session, url, domain):
    try:
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        pdfs, imgs = [], []
        # Ищем PDF (каталоги 2027)
        for a in soup.find_all('a', href=True):
            h = urljoin(url, a['href']).split('#')[0]
            if h.lower().endswith('.pdf'):
                txt = a.get_text().strip()
                if check_content(txt + h) or 'catalog' in (txt+h).lower():
                    pdfs.append({'name': txt or "Каталог PDF", 'url': quote(h, safe=':/?&=#')})
        
        # Ищем фото (Картон/Тубы)
        for im in soup.find_all('img'):
            src = im.get('src') or im.get('data-src') or im.get('data-original')
            if not src: continue
            f = urljoin(url, src)
            alt = (im.get('alt') or '').lower()
            if check_content(alt + f):
                imgs.append({'name': im.get('alt') or "Упаковка", 'url': quote(f, safe=':/?&=#')})
        return pdfs, imgs
    except: return [], []

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Поиск упаковки 2027", layout="wide")
st.title("🎁 Поиск упаковки: Картон / МГК / Тубы")

name = st.text_input("Название (напр. Рубин, Коммунарка, Спартак):")

if name:
    q = name.lower().strip()
    url = DIRECTORY.get(q)
    if not url:
        url = f"https://{translit(q)}.by" if 'ком' in q or 'спар' in q else f"https://{translit(q)}.ru"
    
    st.write(f"📡 Работаем с: {url}")
    
    session = get_session()
    
    try:
        # Быстрый чекин главной
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        domain = urlparse(url).netloc
        
        # Находим разделы
        pages = {url}
        for a in soup.find_all('a', href=True):
            h = urljoin(url, a['href']).split('#')[0]
            if urlparse(h).netloc == domain:
                if any(w in a.get_text().lower() or w in h.lower() for w in ['catalog', 'novogod', 'podarki', 'karton', 'tuba']):
                    pages.add(h)
        
        with st.spinner("Собираем картонную упаковку..."):
            p_all, i_all = [], []
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = [ex.submit(scan_page, session, p, domain) for p in list(pages)[:25]]
                for f in as_completed(futures):
                    res_p, res_i = f.result()
                    p_all.extend(res_p)
                    i_all.extend(res_i)
            
            # Чистим дубликаты
            pdfs = list({v['url']:v for v in p_all}.values())
            imgs = list({v['url']:v for v in i_all}.values())
            
            if pdfs or imgs:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"📄 PDF ({len(pdfs)})")
                    for p in pdfs: st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                with col2:
                    st.subheader(f"📦 Фото ({len(imgs)})")
                    if imgs:
                        z_io = io.BytesIO()
                        with zipfile.ZipFile(z_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:400]):
                                try:
                                    res = session.get(im['url'], timeout=5).content
                                    zf.writestr(f"item_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", z_io.getvalue(), "packaging.zip")
                        
                        g = st.columns(3)
                        for i, im in enumerate(imgs[:9]): g[i%3].image(im['url'], use_container_width=True)
            else:
                st.warning("На сайте нет нужных материалов (картона/туб).")
    except Exception as e:
        st.error(f"Сайт не отвечает. Возможно, временная блокировка. Попробуй через минуту.")
