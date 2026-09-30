import io
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем предупреждения о безопасности
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 РЕЕСТР ПРОИЗВОДИТЕЛЕЙ (БАЗА ЗНАНИЙ)
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
    'рахат': 'https://rakhat.kz',
    'акконд': 'https://akkond.ru'
}

# Тематические фильтры (Картон и Тубы)
GOOD_WORDS = ['картон', 'мгк', 'микрогофр', 'гофро', 'переплет', 'туб', 'тубус', 'box', 'коробка', 'книга', '2025', '2027']
BAD_WORDS = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерево', 'пластик', 'мешок', 'рюкзак']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# =========================================================
# 🛠 ТЕХНИЧЕСКИЕ МОДУЛИ
# =========================================================

def translit(text):
    """Преобразование названия в доменное имя"""
    d = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return "".join(d.get(c, c) for c in text.lower()).replace(" ", "-")

def get_target_url(query):
    """Умный поиск сайта без ошибок кэша"""
    q = query.lower().strip()
    
    # 1. Поиск в базе
    for name, url in COMPANY_DB.items():
        if name in q:
            return url
            
    # 2. Если введена ссылка
    if '.' in q and ' ' not in q:
        return q if q.startswith('http') else f"https://{q}"
        
    # 3. Авто-подбор домена
    slug = translit(q)
    for tld in ['ru', 'by', 'kz', 'com']:
        test_url = f"https://{slug}.{tld}"
        try:
            r = requests.head(test_url, headers=HEADERS, timeout=2, verify=False)
            if r.status_code < 400: return test_url
        except: continue
        
    return f"https://{slug}.ru"

def scan_page(url, domain):
    """Парсинг одной страницы на картонную упаковку"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    pdfs, imgs = [], []
    # Сбор PDF
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if href.lower().endswith('.pdf'):
            text = (a.get_text() + ' ' + href).lower()
            if not any(b in text for b in ['политика', 'устав']):
                if any(g in text for g in GOOD_WORDS + ['каталог']):
                    pdfs.append({'name': a.get_text().strip() or "Каталог PDF", 'url': quote(href, safe=':/?&=#')})
                    
    # Сбор Картинок
    for im in soup.find_all('img'):
        src = im.get('src') or im.get('data-src') or im.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        alt = (im.get('alt') or '').lower() + ' ' + full.lower()
        
        # Фильтр: Должен быть картон, не должно быть металла/текстиля
        if any(g in alt for g in GOOD_WORDS):
            if not any(b in alt for b in BAD_WORDS + ['logo', 'icon', 'social', 'btn']):
                imgs.append({'name': im.get('alt') or "Упаковка картон", 'url': quote(full, safe=':/?&=#')})
                
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Поиск упаковки 2027", layout="wide")

st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")
st.caption("Автоматический анализ разделов 2025-2027. Металл и мягкая игрушка исключаются.")

user_query = st.text_input("Название компании (Спартак, Рубин, Академия шоколада...):", key="main_search")

if user_query:
    target_site = get_target_url(user_query)
    
    # Сброс старых состояний
    st.info(f"🚀 Подключено к официальному сайту: **{target_site}**")
    
    with st.spinner("Глубокий анализ разделов каталога..."):
        domain = urlparse(target_site).netloc
        
        # Находим подразделы каталога
        try:
            r = requests.get(target_site, headers=HEADERS, timeout=10, verify=False)
            main_soup = BeautifulSoup(r.text, 'html.parser')
            pages = {target_site}
            for a in main_soup.find_all('a', href=True):
                href = urljoin(target_site, a['href']).split('#')[0]
                if urlparse(href).netloc == domain:
                    if any(w in a.get_text().lower() or w in href.lower() for w in ['catalog', 'novogod', 'podarki', 'karton', 'tuba']):
                        pages.add(href)
            
            # Многопоточный сбор данных
            all_pdfs, all_imgs = [], []
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(scan_page, url, domain) for url in list(pages)[:25]]
                for f in as_completed(futures):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)
            
            # Удаление дублей
            pdfs = list({v['url']:v for v in all_pdfs}.values())
            imgs = list({v['url']:v for v in all_imgs}.values())
            
            # Вывод результатов
            if pdfs or imgs:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader(f"📄 PDF Каталоги ({len(pdfs)})")
                    for p in pdfs:
                        st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                    if not pdfs: st.write("Не найдены.")
                
                with col2:
                    st.subheader(f"🖼 Картон и тубы ({len(imgs)})")
                    if imgs:
                        # ZIP
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:400]):
                                try:
                                    res = requests.get(im['url'], timeout=5, verify=False).content
                                    zf.writestr(f"item_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} фото)", zip_io.getvalue(), "packaging.zip")
                        
                        # Галерея
                        g = st.columns(3)
                        for i, im in enumerate(imgs[:9]):
                            g[i%3].image(im['url'], use_container_width=True)
                    else:
                        st.write("Картонная упаковка не найдена.")
            else:
                st.error("Ничего не найдено. Проверьте правильность названия.")
                
        except Exception as e:
            st.error(f"Ошибка доступа к сайту: {e}")
