import io
import re
import zipfile
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import streamlit as st

# =========================================================
# 🏆 ЭКСПЕРТНАЯ БАЗА ПРОИЗВОДИТЕЛЕЙ (МЕНЕДЖЕРУ НЕ НУЖНО ИСКАТЬ)
# =========================================================
# Мы заранее прописываем правильные сайты для ключевых игроков
COMPANIES_REGISTRY = {
    'рубин': 'https://rubin-tg.ru',
    'академия шоколада': 'https://academy-chocolate.ru',
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'рахат': 'https://rakhat.kz',
    'миракс': 'https://mirax-gifts.ru',
    'дилявер': 'https://dilyaver.com',
    'росшоколад': 'https://roschocolate.ru',
    'москондитер': 'https://mosconditer.ru',
    'акконд': 'https://akkond.ru',
    'славянка': 'https://slavyanka.ru',
    'красный октябрь': 'https://www.uniconf.ru',
    'рот фронт': 'https://www.uniconf.ru',
    'бабаевский': 'https://www.uniconf.ru',
    'эссен': 'https://essenproduction.com',
    'победа': 'https://store.pobedavkusa.ru',
    'сириус': 'https://sirius-gk.ru',
}

# Ключевые слова для поиска (максимально широко)
TARGET_WORDS = ['новогод', 'подар', 'упаков', 'каталог', '2025', '2024', 'короб', 'жесть', 'картон', 'туба', 'catalog', 'gift']
# Исключаем мусор
JUNK_WORDS = ['политика', 'обработк', 'персональн', 'лицензия', 'устав', 'согласие', 'privacy', 'sout', 'special-assessment']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# =========================================================
# 🛠 УМНАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ САЙТА
# =========================================================

def get_official_url(query):
    query = query.lower().strip()
    
    # 1. Если менеджер ввел адрес вручную
    if '.' in query and ' ' not in query:
        return query if query.startswith('http') else f"https://{query}"
    
    # 2. Поиск по нашему реестру (самый точный способ)
    for key in COMPANIES_REGISTRY:
        if key in query:
            return COMPANIES_REGISTRY[key]
    
    # 3. Интеллектуальный подбор (транслит + ЕАЭС зоны)
    # Если ввели "Академия шоколада" -> academy-chocolate.ru
    trans = query.replace('академия', 'academy').replace('шоколада', 'chocolate').replace(' ', '-')
    return f"https://{trans}.ru"

def safe_request(url):
    """Метод для безопасного получения данных с сайта"""
    try:
        # Увеличиваем таймаут и отключаем проверку SSL (часто просрочены на заводах)
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        return None

# =========================================================
# 🕷 СКАНЕР КАТАЛОГОВ
# =========================================================

def parse_site(url):
    soup = safe_request(url)
    if not soup:
        return None, None
    
    domain = urlparse(url).netloc
    
    # Ищем все ссылки на подразделы "Каталоги", "Новый год" и т.д.
    subpages = {url}
    for a in soup.find_all('a', href=True):
        link = urljoin(url, a['href'])
        text = a.get_text().lower()
        if any(w in text or w in link.lower() for w in ['catalog', 'novogod', 'podarki', 'ny2025']):
            if urlparse(link).netloc == domain:
                subpages.add(link)
    
    pdfs, imgs = [], []
    
    # Сканируем найденные подразделы
    for page in list(subpages)[:6]:
        p_soup = safe_request(page)
        if not p_soup: continue
        
        # 1. Ищем PDF
        for a in p_soup.find_all('a', href=True):
            f_url = urljoin(page, a['href'])
            f_text = a.get_text().strip()
            if f_url.lower().split('?')[0].endswith('.pdf'):
                if any(w in (f_text + f_url).lower() for w in TARGET_WORDS):
                    if not any(j in (f_text + f_url).lower() for j in JUNK_WORDS):
                        pdfs.append({'name': f_text or "Новогодний каталог", 'url': f_url})
        
        # 2. Ищем Картинки Упаковки
        for im in p_soup.find_all('img', src=True):
            i_src = urljoin(page, im['src'])
            i_alt = im.get('alt', '').strip()
            if any(w in (i_alt + i_src).lower() for w in TARGET_WORDS):
                if not any(j in i_src.lower() for j in ['logo', 'icon', 'social', 'btn']):
                    imgs.append({'name': i_alt or "Упаковка", 'url': i_src})
    
    # Чистим дубли
    pdfs = list({v['url']:v for v in pdfs}.values())
    imgs = list({v['url']:v for v in imgs}.values())
    
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС ДЛЯ МЕНЕДЖЕРА
# =========================================================

st.set_page_config(page_title="Поиск каталогов ЕАЭС", page_icon="🎁", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #ff4b4b; color: white; }
    </style>
    """, unsafe_allow_safe_area=True)

st.title("🚀 Универсальный поиск новогодней упаковки")
st.subheader("Инструмент для отделов закупок и менеджеров")

query = st.text_input("Введите название компании (Спартак, Рубин, Академия шоколада, Миракс...)", 
                     help="Просто введите название, система сама найдет официальный сайт.")

if query:
    site_url = get_official_url(query)
    
    with st.status(f"💼 Работаем с компанией: {query}...", expanded=True) as status:
        st.write(f"🔗 Определен официальный сайт: {site_url}")
        
        pdfs, imgs = parse_site(site_url)
        
        if pdfs is None and imgs is None:
            status.update(label="❌ Ошибка доступа к сайту", state="error")
            st.error(f"""
            **Сайт {site_url} не отвечает на запрос нашего сервера.**
            Причины: сайт заблокирован в облаке или на нем стоит защита от роботов.
            
            👉 **Что делать менеджеру:** 
            Откройте сайт вручную по ссылке: [{site_url}]({site_url})
            """)
        else:
            status.update(label="✅ Данные успешно собраны!", state="complete")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.header("📄 PDF Каталоги")
                if pdfs:
                    for p in pdfs:
                        st.success(f"📎 [{p['name']}]({p['url']})")
                else:
                    st.write("На сайте нет PDF-файлов с каталогами.")

            with col2:
                st.header("🖼 Фото упаковки")
                if imgs:
                    st.info(f"Найдено фото товаров: {len(imgs)}")
                    
                    # Генерация ZIP
                    zip_io = io.BytesIO()
                    with zipfile.ZipFile(zip_io, 'w') as zf:
                        for i, img in enumerate(imgs[:50]):
                            try:
                                res = requests.get(img['url'], timeout=5, verify=False).content
                                zf.writestr(f"gift_packaging_{i}.jpg", res)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО АРХИВОМ (.ZIP)", zip_io.getvalue(), "packaging_archive.zip")
                    
                    # Сетка
                    grid = st.columns(3)
                    for idx, im in enumerate(imgs[:9]):
                        grid[idx%3].image(im['url'], use_container_width=True)
                else:
                    st.write("Фотографии новогодней упаковки не найдены.")
