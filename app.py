import io
import re
import zipfile
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем предупреждения о небезопасном SSL (актуально для многих сайтов заводов)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🏆 ПРОВЕРЕННАЯ БАЗА ЗАКАЗЧИКОВ (РЕЕСТР МЕНЕДЖЕРА)
# =========================================================
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
    'рубин-тг': 'https://rubin-tg.ru',
}

# Ключевые слова для поиска упаковки и подарков
TARGET_KEYWORDS = [
    'новогод', 'подар', 'упаков', 'каталог', '2025', '2024', 
    'короб', 'жесть', 'картон', 'туба', 'текстиль', 'catalog', 'gift'
]

# Список слов-исключений (мусор)
BLACKLIST_KEYWORDS = [
    'политика', 'обработк', 'персональн', 'лицензия', 'устав', 
    'согласие', 'privacy', 'sout', 'спецоценка', 'вакансии'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# =========================================================
# 🛠 УМНЫЕ ФУНКЦИИ
# =========================================================

def get_target_url(query):
    """Определяет сайт по названию или ссылке"""
    q = query.lower().strip()
    
    # Если введена ссылка
    if '.' in q and not ' ' in q:
        return q if q.startswith('http') else f"https://{q}"
    
    # Поиск по реестру (самый надежный способ для менеджера)
    for name, site in COMPANIES_REGISTRY.items():
        if name in q:
            return site
            
    # Если названия нет в базе — пробуем транслит
    slug = q.replace(' ', '-').replace('академия', 'academy').replace('шоколада', 'chocolate')
    return f"https://{slug}.ru"

def fetch_page(url):
    """Загрузка страницы с защитой от сбоев"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception:
        return None

def scan_catalog(base_url):
    """Поиск файлов и картинок"""
    soup = fetch_page(base_url)
    if not soup:
        return None, None
    
    domain = urlparse(base_url).netloc
    
    # Находим внутренние страницы (Каталоги, Подарки)
    sections = {base_url}
    for a in soup.find_all('a', href=True):
        link = urljoin(base_url, a['href'])
        if urlparse(link).netloc == domain:
            text = a.get_text().lower()
            if any(w in text or w in link.lower() for w in ['catalog', 'katalog', 'podarki', 'novogod']):
                sections.add(link)
    
    found_pdfs = []
    found_imgs = []
    
    # Обходим разделы
    for page in list(sections)[:6]:
        psoup = fetch_page(page)
        if not psoup: continue
        
        # PDF
        for a in psoup.find_all('a', href=True):
            href = urljoin(page, a['href'])
            txt = a.get_text().strip()
            if href.lower().split('?')[0].endswith('.pdf'):
                combined = (txt + ' ' + href).lower()
                if any(w in combined for w in TARGET_KEYWORDS):
                    if not any(b in combined for b in BLACKLIST_KEYWORDS):
                        found_pdfs.append({'name': txt or "Каталог PDF", 'url': href})
        
        # Картинки (Упаковка)
        for im in psoup.find_all('img', src=True):
            src = urljoin(page, im['src'])
            alt = im.get('alt', '').strip()
            combined = (alt + ' ' + src).lower()
            if any(w in combined for w in TARGET_KEYWORDS):
                if not any(b in src.lower() for b in ['logo', 'icon', 'btn', 'social', 'header']):
                    found_imgs.append({'name': alt or "Упаковка", 'url': src})
    
    # Уникальность
    final_pdfs = list({v['url']:v for v in found_pdfs}.values())
    final_imgs = list({v['url']:v for v in found_imgs}.values())
    
    return final_pdfs, final_imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Поиск упаковки ЕАЭС", page_icon="🎁", layout="wide")

# Исправленный блок CSS
st.markdown("""
    <style>
    .stButton>button { width: 100%; background-color: #ff4b4b; color: white; height: 3em; border-radius: 8px; }
    .main-card { padding: 20px; border-radius: 10px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

st.title("🎁 Профессиональный поиск новогодних каталогов")
st.write("Специальный инструмент для поиска упаковки и подарков по базе производителей ЕАЭС.")

user_input = st.text_input("Введите название компании (например: Рубин, Академия шоколада, Коммунарка):")

if user_input:
    target_url = get_target_url(user_input)
    
    with st.status(f"🔎 Сканируем компанию: {user_input}...", expanded=True) as status:
        st.write(f"🌐 Официальный сайт: **{target_url}**")
        
        pdfs, imgs = scan_catalog(target_url)
        
        if pdfs is None and imgs is None:
            status.update(label="❌ Ошибка связи", state="error")
            st.error(f"Сайт {target_url} не отвечает. Менеджеру рекомендуется открыть его вручную: [Перейти на сайт]({target_url})")
        else:
            status.update(label="✅ Данные получены", state="complete")
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("📄 PDF-Каталоги")
                if pdfs:
                    for p in pdfs:
                        st.success(f"📎 [{p['name']}]({p['url']})")
                else:
                    st.write("Новогодние PDF не найдены.")

            with c2:
                st.subheader("🖼 Фото упаковки")
                if imgs:
                    st.info(f"Найдено изображений: {len(imgs)}")
                    
                    # Создание ZIP
                    zip_file = io.BytesIO()
                    with zipfile.ZipFile(zip_file, 'w') as zf:
                        for i, img in enumerate(imgs[:50]):
                            try:
                                img_res = requests.get(img['url'], timeout=5, verify=False).content
                                zf.writestr(f"item_{i}.jpg", img_res)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО В ZIP", zip_file.getvalue(), "catalog_packaging.zip")
                    
                    # Галерея
                    g_cols = st.columns(3)
                    for i, im in enumerate(imgs[:9]):
                        g_cols[i % 3].image(im['url'], use_container_width=True)
                else:
                    st.write("Фотографии упаковки не найдены.")
