import io
import re
import zipfile
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import streamlit as st

# ==========================================
# 🏆 БАЗА ТИТАНОВ РЫНКА (ПРЯМЫЕ ССЫЛКИ)
# ==========================================
OFFICIAL_DIRECTORY = {
    'рубин': 'https://rubin-tg.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'рахат': 'https://rakhat.kz',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
    'красный октябрь': 'https://www.uniconf.ru',
    'акконд': 'https://akkond.ru',
    'славянка': 'https://slavyanka.ru',
}

# Ключевые слова для подтверждения, что сайт «тот самый»
VERIFICATION_KEYWORDS = ['подар', 'упаков', 'каталог', 'конфет', 'новогод']

# Исключения для PDF (полный отсев мусора)
PDF_IGNORE = ['политика', 'обработк', 'персональн', 'устав', 'реквизит', 'лиценз', 'согласие', 'privacy', 'sout', 'special-assessment']

# Целевые слова для поиска (Новый Год 2025 / Упаковка)
TARGET_WORDS = ['новогод', '2025', '2024', 'подар', 'упаков', 'короб', 'туба', 'жесть', 'картон', 'каталог', 'catalog', 'gift', 'new-year']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ==========================================
# 🛠 БЛОК ЛОГИКИ ПОИСКА
# ==========================================

def check_site_relevance(url):
    """Проверяет, действительно ли сайт занимается подарками/упаковкой"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'lxml')
        text = soup.get_text().lower()
        return any(word in text for word in VERIFICATION_KEYWORDS)
    except:
        return False

def resolve_domain(query):
    query = query.lower().strip()
    
    # 1. Если это URL
    if '.' in query and ' ' not in query:
        return f"https://{query.replace('https://', '').replace('http://', '')}"
    
    # 2. Поиск в реестре гигантов
    for name, domain in OFFICIAL_DIRECTORY.items():
        if name in query:
            return domain
            
    # 3. Умный перебор зон ЕАЭС с верификацией контента
    base_name = query.replace(' ', '-')
    # Также пробуем транслит для сложных названий
    variants = [base_name, base_name.replace('-', ''), 'akademiya-shokolada' if 'академия' in query else base_name]
    
    tlds = ['ru', 'by', 'kz', 'com', 'ru']
    for v in variants:
        for tld in tlds:
            test_url = f"https://{v}.{tld}"
            try:
                # Проверяем доступность и содержание
                resp = requests.head(test_url, headers=HEADERS, timeout=2, allow_redirects=True)
                if resp.status_code < 400:
                    real_url = resp.url
                    if check_site_relevance(real_url):
                        return real_url
            except:
                continue
    return None

# ==========================================
# 🕷 КРАУЛЕР (СБОР ДАННЫХ)
# ==========================================

def get_data(site_url):
    try:
        res = requests.get(site_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'lxml')
    except Exception as e:
        st.error(f"Ошибка доступа: {e}")
        return

    # Находим разделы каталогов (авто-переход)
    links_to_check = {site_url}
    for a in soup.find_all('a', href=True):
        href = urljoin(site_url, a['href'])
        txt = a.get_text().lower()
        if any(w in txt or w in href for w in ['catalog', 'katalog', 'podarki', 'novogod']):
            if urlparse(href).netloc == urlparse(site_url).netloc:
                links_to_check.add(href)
    
    links_to_check = list(links_to_check)[:6] # Ограничение глубины

    pdfs = []
    imgs = []
    
    prog = st.progress(0)
    for i, link in enumerate(links_to_check):
        try:
            r = requests.get(link, headers=HEADERS, timeout=7)
            s = BeautifulSoup(r.text, 'lxml')
            
            # Собираем PDF
            for a in s.find_all('a', href=True):
                url = urljoin(link, a['href'])
                name = a.get_text().strip()
                if url.lower().endswith('.pdf'):
                    # Фильтр: Должен быть новогодним и не быть юридическим мусором
                    if any(w in (name+url).lower() for w in TARGET_WORDS):
                        if not any(bad in (name+url).lower() for bad in PDF_IGNORE):
                            pdfs.append({'name': name if len(name) > 3 else "Новогодний каталог", 'url': url})
            
            # Собираем Фото упаковки
            for im in s.find_all('img', src=True):
                src = urljoin(link, im['src'])
                alt = im.get('alt', '').strip()
                # Фильтр: только упаковка/подарки, игнорируем лого и иконки
                if any(w in (alt+src).lower() for w in TARGET_WORDS):
                    if not any(bad in src.lower() for bad in ['logo', 'icon', 'banner', 'button', 'cart', 'social']):
                        imgs.append({'name': alt if alt else src.split('/')[-1], 'url': src})
        except:
            continue
        prog.progress((i + 1) / len(links_to_check))

    # Уникализация списков
    pdfs = [dict(t) for t in {tuple(d.items()) for d in pdfs}]
    imgs = [dict(t) for t in {tuple(d.items()) for d in imgs}]
    
    return pdfs, imgs

# ==========================================
# 🖥 ИНТЕРФЕЙС
# ==========================================

st.set_page_config(page_title="NY Catalog Finder Pro", page_icon="🎁", layout="wide")
st.title("🎁 Поиск упаковки и подарков ЕАЭС")
st.markdown("Поиск по базе производителей **Беларуси, России и Казахстана**.")

query = st.text_input("Введите название компании (например: Рубин, Академия шоколада, Спартак):", placeholder="Рубин")

if query:
    with st.spinner(f"Ищем официальный сайт для '{query}'..."):
        site = resolve_domain(query)
        
    if site:
        st.success(f"✅ Найден официальный сайт: {site}")
        
        pdfs, imgs = get_data(site)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📄 PDF Каталоги")
            if pdfs:
                for p in pdfs:
                    st.info(f"👉 [{p['name']}]({p['url']})")
            else:
                st.write("Каталоги в PDF не найдены.")
                
        with col2:
            st.subheader("🖼 Фото упаковки / подарков")
            if imgs:
                st.write(f"Найдено изображений: {len(imgs)}")
                
                # Создание ZIP
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, 'a', zipfile.ZIP_DEFLATED) as zf:
                    for i, im in enumerate(imgs[:50]): # Лимит 50 фото
                        try:
                            res = requests.get(im['url'], timeout=5).content
                            ext = im['url'].split('.')[-1][:3]
                            if ext not in ['jpg', 'png', 'web']: ext = 'jpg'
                            zf.writestr(f"gift_{i}.{ext}", res)
                        except: continue
                
                st.download_button("📥 Скачать архив с картинками", zip_buf.getvalue(), "catalog_images.zip", "application/zip")
                
                # Превью
                c = st.columns(3)
                for idx, im in enumerate(imgs[:6]):
                    c[idx%3].image(im['url'], use_container_width=True)
            else:
                st.write("Изображения не найдены.")
    else:
        st.error("❌ Не удалось найти официальный сайт. Попробуйте ввести точный адрес (например: rubin-tg.ru)")
