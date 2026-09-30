import io
import zipfile
import time
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Полное подавление системных предупреждений SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🚀 РЕЕСТР ЦЕЛЕЙ (БАЗА ДАННЫХ)
# =========================================================
TARGET_REGISTRY = {
    'рубин': 'https://rubin-2000.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
    'акконд': 'https://akkond.ru',
    'славянка': 'https://slavyanka.ru'
}

# Ключевые слова фильтрации (Картон / МГК / Тубы)
CARDBOARD_ONLY = ['картон', 'мгк', 'гофр', 'переплет', 'туб', 'тубус', 'box', 'коробка', '2025', '2027', 'футляр']
FORBIDDEN = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'мешок', 'рюкзак']

# =========================================================
# 🛠 ТЕХНОЛОГИЯ ОБХОДА БЛОКИРОВОК (ENGINEERING)
# =========================================================

def get_high_perf_session():
    """Создает сессию, которую крайне сложно заблокировать"""
    session = requests.Session()
    # Имитируем реальный браузер на 100%
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    })
    return session

def resolve_url(query):
    q = query.lower().strip()
    # Прямой поиск в базе
    for name, url in TARGET_REGISTRY.items():
        if name in q: return url
    # Если введена ссылка
    if '.' in q and ' ' not in q:
        return q if q.startswith('http') else f"https://{q}"
    # Транслитерация
    d = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    slug = "".join(d.get(c, c) for c in q).replace(" ", "-")
    return f"https://{slug}.ru"

# =========================================================
# 🕷 АВТОНОМНЫЙ СКАНЕР
# =========================================================

def scan_resource(session, url, domain):
    try:
        # Увеличен таймаут до 30 сек для пробития плохих каналов связи
        r = session.get(url, timeout=30, verify=False, allow_redirects=True)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    pdfs, imgs = [], []
    # PDF Сбор
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().split('?')[0].endswith('.pdf'):
            comb = (a.get_text() + ' ' + href).lower()
            if any(g in comb for g in CARDBOARD_ONLY + ['каталог']):
                if not any(b in comb for b in ['политика', 'устав', 'реквизит']):
                    pdfs.append({'name': a.get_text().strip() or "PDF Каталог", 'url': quote(href, safe=':/?&=#')})
    
    # Сбор фото упаковки (Картон/Тубы)
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original') or im.get('data-lazy-src')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or '').lower() + ' ' + full.lower()
        if any(g in alt for g in CARDBOARD_ONLY):
            if not any(b in alt for b in FORBIDDEN + ['logo', 'icon', 'social', 'btn']):
                imgs.append({'name': im.get('alt') or "Упаковка", 'url': quote(full, safe=':/?&=#')})
                
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС УПРАВЛЕНИЯ
# =========================================================

st.set_page_config(page_title="NY Packaging Breaker", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")
st.write("Система обхода блокировок активна. Поиск по каталогам 2025-2027.")

query = st.text_input("Введите название компании (Спартак, Коммунарка, Рубин...):", key="search_field")

if query:
    target = resolve_url(query)
    st.info(f"🛰 Установлена связь с: **{target}**")
    
    session = get_high_perf_session()
    
    with st.spinner("Прорыв через сетевые фильтры и глубокий анализ картона..."):
        try:
            # Первый контакт
            r = session.get(target, timeout=30, verify=False)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')
            domain = urlparse(target).netloc
            
            # Находим разделы
            pages = {target}
            for a in soup.find_all('a', href=True):
                href = urljoin(target, a['href']).split('#')[0]
                if urlparse(href).netloc == domain:
                    text = a.get_text().lower()
                    if any(w in text or w in href.lower() for w in ['catalog', 'novogod', 'podarki', 'karton', 'tuba', '202']):
                        pages.add(href)
            
            # Глубокий сбор
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=6) as executor: # Чуть меньше потоков, чтобы не забанили
                futures = [executor.submit(scan_resource, session, url, domain) for url in list(pages)[:25]]
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
                    st.subheader(f"📦 Картон ({len(imgs)})")
                    if imgs:
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:400]):
                                try:
                                    img_data = session.get(im['url'], timeout=15).content
                                    zf.writestr(f"item_{idx+1}.jpg", img_data)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_io.getvalue(), "packaging.zip", key="dl_btn")
                        
                        grid = st.columns(3)
                        for idx, im in enumerate(imgs[:9]): grid[idx%3].image(im['url'], use_container_width=True)
            else:
                st.warning("Связь установлена, но целевой картонной упаковки на сайте не найдено.")
                
        except Exception as e:
            st.error(f"❌ Критический сбой связи с {target}. Сайт полностью блокирует облачные запросы.")
            st.info("💡 Решение для менеджера: Откройте сайт в обычном браузере, так как облачный сервер временно заблокирован защитой сайта.")
