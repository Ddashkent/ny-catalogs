import io
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 📦 БАЗА И НАСТРОЙКИ
# =========================================================
# Прямые ссылки, чтобы менеджеры не искали
OFFICIAL_SITES = {
    'рубин': 'https://rubin-2000.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'академия шоколада': 'https://academy-chocolate.ru',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
}

# Только картонное направление
GOOD_WORDS = ['картон', 'мгк', 'микрогофр', 'гофро', 'переплет', 'туб', 'тубус', 'tube', 'box', 'коробка']
BAD_WORDS = ['жесть', 'металл', 'tin', 'банка', 'текстиль', 'мягк', 'игрушк', 'дерев', 'пластик']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# =========================================================
# 🛠 ТЕХНИЧЕСКИЕ ФУНКЦИИ
# =========================================================

@st.cache_data(ttl=3600) # Кэшируем на час, чтобы UI не падал
def get_verified_data(target_url):
    domain = urlparse(target_url).netloc
    
    def fetch(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            return BeautifulSoup(r.text, 'html.parser')
        except: return None

    base_soup = fetch(target_url)
    if not base_soup: return [], []

    # Собираем разделы каталога
    pages = {target_url}
    for a in base_soup.find_all('a', href=True):
        href = urljoin(target_url, a['href']).split('#')[0]
        if urlparse(href).netloc == domain:
            txt = a.get_text().lower()
            if any(w in txt or w in href.lower() for w in ['catalog', 'katalog', 'upakov', 'podarki', 'karton', 'tuba']):
                pages.add(href)

    all_pdfs, all_imgs = [], []
    
    def parse_page(url):
        soup = fetch(url)
        if not soup: return [], []
        ps, imgs = [], []
        # PDF
        for a in soup.find_all('a', href=True):
            h = urljoin(url, a['href']).split('#')[0]
            if h.lower().endswith('.pdf'):
                t = a.get_text().strip()
                if any(w in (t+h).lower() for w in GOOD_WORDS + ['каталог']):
                    ps.append({'name': t or "Каталог PDF", 'url': quote(h, safe=':/?&=#')})
        # Картинки (включая Lazy Load)
        for im in soup.find_all('img'):
            src = im.get('src') or im.get('data-src') or im.get('data-original') or im.get('data-lazy-src')
            if not src: continue
            full = urljoin(url, src)
            alt = (im.get('alt') or '').lower()
            # Фильтр: только картон, без металла
            if any(g in (alt+full).lower() for g in GOOD_WORDS):
                if not any(b in (alt+full).lower() for b in BAD_WORDS + ['logo', 'icon', 'social', 'header', 'footer']):
                    imgs.append({'name': alt or "Картонная упаковка", 'url': quote(full, safe=':/?&=#')})
        return ps, imgs

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(parse_page, u) for u in list(pages)[:25]]
        for f in as_completed(futures):
            p, i = f.result()
            all_pdfs.extend(p)
            all_imgs.extend(i)

    return (list({v['url']:v for v in all_pdfs}.values()), 
            list({v['url']:v for v in all_imgs}.values()))

def translit(text):
    chars = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return "".join(chars.get(c, c) for c in text.lower()).replace(" ", "-")

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Поиск упаковки 2027", layout="wide")

# Стабильный стиль без лишних анимаций
st.markdown("<style>.stImage > img {border-radius: 10px; border: 1px solid #eee;}</style>", unsafe_allow_html=True)

st.title("📦 Анализатор новогодней упаковки (Картон / МГК / Тубы)")
st.info("Введите название компании. Мы сами найдем сайт и соберем фото картонной упаковки 2025-2027.")

query = st.text_input("Название компании (например: Рубин, Спартак, Коммунарка):", key="search_input")

if query:
    q_low = query.lower().strip()
    
    # 1. Определяем сайт
    target_url = None
    if q_low in OFFICIAL_SITES:
        target_url = OFFICIAL_SITES[q_low]
    elif '.' in q_low and ' ' not in q_low:
        target_url = q_low if q_low.startswith('http') else f"https://{q_low}"
    else:
        name = translit(q_low)
        target_url = f"https://{name}.ru"
    
    # 2. Поиск и сбор (с защитой от JS-ошибки)
    st.write(f"🔎 Сканируем официальный сайт: **{target_url}**")
    
    # Используем одну стабильную точку входа для данных
    pdfs, imgs = get_verified_data(target_url)
    
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
                # Генерация ZIP
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, 'w') as zf:
                    for idx, im in enumerate(imgs[:400]):
                        try:
                            res = requests.get(im['url'], timeout=5, verify=False).content
                            zf.writestr(f"product_{idx+1}.jpg", res)
                        except: continue
                
                st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_io.getvalue(), "catalog.zip", key="zip_btn")
                
                # Галерея
                g = st.columns(3)
                for i, im in enumerate(imgs[:12]):
                    g[i%3].image(im['url'], use_container_width=True)
            else:
                st.write("Изображения картона не найдены.")
    else:
        st.warning("Ничего не найдено. Если вы уверены, что сайт существует, попробуйте ввести его адрес полностью.")
