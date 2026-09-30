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
# 📦 НАСТРОЙКИ ФИЛЬТРАЦИИ (ТОЛЬКО КАРТОН И ТУБЫ)
# =========================================================
CARDBOARD_WORDS = [
    'картон', 'karton', 'cardboard', 'мгк', 'микрогофр', 'гофрокартон', 
    'переплет', 'переплёт', 'кашир', 'туб', 'tuba', 'tube', 'тубус',
    'коробка', 'box', 'футляр', 'шкатулка', 'сундучок', 'домик', 'книга'
]

# ИСКЛЮЧАЕМ (Жесть, Текстиль, Дерево, Пластик)
FOREIGN_MATERIALS = [
    'жест', 'zhest', 'металл', 'tin', 'банка', 'текстил', 'ткан', 'мешоч', 
    'рюкзак', 'плюш', 'мягк', 'игрушк', 'toy', 'дерев', 'фанер', 'wood',
    'пластик', 'plastik', 'пэт', 'пвх', 'керамик', 'стекл', 'валенк'
]

UI_JUNK = ['logo', 'icon', 'banner', 'button', 'social', 'vk', 'fb', 'instagram', 'cart', 'header', 'footer', 'pixel', 'arrow', 'bg', 'widget', 'metrika']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# =========================================================
# 🧠 УМНЫЙ ПОИСК САЙТА (БЕЗ ВНЕШНИХ БИБЛИОТЕК)
# =========================================================

def translit(text):
    """Транслитерация для поиска доменов"""
    symbols = str.maketrans(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "abvgdeezzijklmnoprstufhcchshsh_y_eua"
    )
    return text.lower().translate(symbols).replace(" ", "-")

def resolve_site(query):
    """Находит сайт компании по названию без поисковиков (чтобы не банили)"""
    q = query.lower().strip()
    
    # 1. Если это уже ссылка
    if '.' in q and ' ' not in q:
        return [q if q.startswith('http') else f"https://{q}"]
    
    # 2. Прямой подбор доменов ЕАЭС
    name = translit(q)
    variants = [
        f"https://{name}.ru", f"https://{name}.by", f"https://{name}.kz",
        f"https://{name}-tg.ru", f"https://{name}-2000.ru", f"https://{name}-gifts.ru"
    ]
    
    verified = []
    for v in variants:
        try:
            r = requests.head(v, headers=HEADERS, timeout=3, verify=False, allow_redirects=True)
            if r.status_code < 400:
                verified.append(r.url)
        except: continue
    
    # Если ничего не нашли, пробуем вернуть хотя бы первый вариант .ru
    return verified if verified else [f"https://{name}.ru"]

# =========================================================
# 🕷 ГЛУБОКИЙ СКАНЕР
# =========================================================

def is_cardboard_item(text):
    t = text.lower()
    if any(bad in t for bad in FOREIGN_MATERIALS): return False
    return any(good in t for good in CARDBOARD_WORDS)

def parse_page(url, domain):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    pdfs, imgs = [], []
    # PDF
    for a in soup.find_all('a', href=True):
        href = urljoin(url, a['href']).split('#')[0]
        if urlparse(href).netloc == domain and href.lower().endswith('.pdf'):
            txt = a.get_text().strip()
            if is_cardboard_item(txt + href) or 'catalog' in (txt + href).lower():
                pdfs.append({'name': txt or "Каталог PDF", 'url': quote(href, safe=':/?&=#')})
    
    # Images (Lazy Load)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if not src: continue
        full = urljoin(url, src)
        low = full.lower()
        if any(j in low for j in UI_JUNK) or not any(ex in low for ex in ['.jpg', '.jpeg', '.png', '.webp']):
            continue
        
        alt = (img.get('alt') or '').strip()
        if is_cardboard_item(alt + full + url):
            imgs.append({'name': alt or "Картонная упаковка", 'url': quote(full, safe=':/?&=#')})
            
    return pdfs, imgs

def deep_scan(start_url):
    domain = urlparse(start_url).netloc
    try:
        r = requests.get(start_url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    # Находим подразделы
    pages = {start_url}
    for a in soup.find_all('a', href=True):
        href = urljoin(start_url, a['href']).split('#')[0]
        if urlparse(href).netloc == domain:
            t = a.get_text().lower()
            if any(w in t or w in href.lower() for w in ['catalog', 'katalog', 'karton', 'upakov', 'podarki', '202']):
                pages.add(href)

    all_p, all_i = [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(parse_page, u, domain) for u in list(pages)[:30]]
        for f in as_completed(futures):
            p, i = f.result()
            all_p.extend(p)
            all_i.extend(i)

    return (list({v['url']:v for v in all_p}.values()), 
            list({v['url']:v for v in all_i}.values()))

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Картонный Поиск", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (Картон / МГК / Тубы)")

query = st.text_input("Введите название компании (напр. Рубин, Спартак, Академия):")

if query:
    with st.spinner("🚀 Глубокий поиск по картонным разделам..."):
        urls = resolve_site(query)
        target, pdfs, imgs = None, None, None
        
        for u in urls:
            p, i = deep_scan(u)
            if p or i:
                target, pdfs, imgs = u, p, i
                break
        
    if target:
        st.success(f"✅ Сайт компании: {target}")
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader(f"📄 PDF ({len(pdfs)})")
            for p in pdfs: st.markdown(f"📎 **[{p['name']}]({p['url']})**")
            
        with c2:
            st.subheader(f"📦 Фото картона ({len(imgs)})")
            if imgs:
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, 'w') as zf:
                    for idx, im in enumerate(imgs[:300]):
                        try:
                            res = requests.get(im['url'], timeout=5, verify=False).content
                            zf.writestr(f"{idx+1:03d}_{im['name'][:30]}.jpg", res)
                        except: continue
                st.download_button(f"📥 СКАЧАТЬ ZIP ({len(imgs)} шт.)", zip_io.getvalue(), "karton.zip")
                
                grid = st.columns(3)
                for i, im in enumerate(imgs[:9]): grid[i%3].image(im['url'], use_container_width=True)
    else:
        st.error("❌ Ничего не найдено. Попробуйте уточнить название.")
