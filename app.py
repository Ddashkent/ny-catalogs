import io
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Отключаем предупреждения о безопасности
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 ГЛОБАЛЬНЫЙ РЕЕСТР
# =========================================================
COMPANY_DB = {
    'рубин': 'https://rubin-2000.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
    'акконд': 'https://akkond.ru'
}

# Тематические фильтры (Картон, МГК, Тубы)
GOOD_WORDS = ['картон', 'мгк', 'микрогофр', 'гофро', 'переплет', 'туб', 'тубус', 'box', 'коробка', '2025', '2027']
BAD_WORDS = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак']

# =========================================================
# 🛠 СИСТЕМА УСТОЙЧИВЫХ ЗАПРОСОВ (ANTI-TIMEOUT)
# =========================================================

def get_smart_session():
    """Создает сессию с автоматическими повторами при сбоях"""
    session = requests.Session()
    retry = Retry(
        total=3,  # 3 попытки
        backoff_factor=1, 
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    })
    return session

def translit(text):
    d = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return "".join(d.get(c, c) for c in text.lower()).replace(" ", "-")

def resolve_target_url(query):
    q = query.lower().strip()
    # 1. База
    for name, url in COMPANY_DB.items():
        if name in q: return url
    # 2. Если URL
    if '.' in q and ' ' not in q:
        return q if q.startswith('http') else f"https://{q}"
    # 3. Транслит
    return f"https://{translit(q)}.ru"

# =========================================================
# 🕷 СКАНЕР
# =========================================================

def scan_single_page(session, url, domain):
    try:
        r = session.get(url, timeout=20, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    pdfs, imgs = [], []
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().endswith('.pdf'):
            comb = (a.get_text() + ' ' + href).lower()
            if any(g in comb for g in GOOD_WORDS + ['каталог']) and not any(b in comb for b in ['политика', 'устав']):
                pdfs.append({'name': a.get_text().strip() or "PDF Каталог", 'url': quote(href, safe=':/?&=#')})
    
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or '').lower() + ' ' + full.lower()
        if any(g in alt for g in GOOD_WORDS) and not any(b in alt for b in BAD_WORDS + ['logo', 'icon', 'social']):
            imgs.append({'name': im.get('alt') or "Упаковка", 'url': quote(full, safe=':/?&=#')})
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Поиск упаковки 2027", layout="wide")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")

user_query = st.text_input("Название компании (Коммунарка, Рубин, Спартак...):")

if user_query:
    target_url = resolve_target_url(user_query)
    st.info(f"🚀 Попытка подключения к: **{target_url}**")
    
    session = get_smart_session()
    
    try:
        # Увеличенный таймаут для первого контакта
        response = session.get(target_url, timeout=25, verify=False)
        response.raise_for_status()
        
        main_soup = BeautifulSoup(response.text, 'html.parser')
        domain = urlparse(target_url).netloc
        
        # Поиск разделов
        pages = {target_url}
        for a in main_soup.find_all('a', href=True):
            href = urljoin(target_url, a['href']).split('#')[0]
            if urlparse(href).netloc == domain:
                if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'novogod', 'podarki', 'karton', 'tuba', '202']):
                    pages.add(href)

        with st.spinner(f"Глубокий анализ {len(pages)} разделов..."):
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(scan_single_page, session, url, domain) for url in list(pages)[:30]]
                for f in as_completed(futures):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
            
            pdfs = list({v['url']:v for v in all_pdfs}.values())
            imgs = list({v['url']:v for v in all_imgs}.values())

            if pdfs or imgs:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"📄 PDF ({len(pdfs)})")
                    for p in pdfs: st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                with col2:
                    st.subheader(f"🖼 Картон ({len(imgs)})")
                    if imgs:
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:400]):
                                try:
                                    img_data = session.get(im['url'], timeout=10).content
                                    zf.writestr(f"item_{idx+1}.jpg", img_data)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_io.getvalue(), "packaging.zip")
                        g = st.columns(3)
                        for idx, im in enumerate(imgs[:9]): g[idx%3].image(im['url'], use_container_width=True)
            else:
                st.warning("На сайте не найдено подходящей картонной упаковки.")
                
    except Exception as e:
        st.error(f"⚠️ Не удалось стабильно подключиться к {target_url}. Сайт перегружен или блокирует запросы из облака.")
        st.info("Рекомендация менеджерам: попробуйте зайти на сайт через браузер или повторите поиск через 1 минуту.")
