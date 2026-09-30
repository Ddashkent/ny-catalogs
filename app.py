import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import io
import zipfile
import time

# --- НАСТРОЙКИ И КЛЮЧЕВЫЕ СЛОВА ---
# Список исключений (чтобы не качать логотипы и мусор)
DOC_BLACKLIST_STEMS = [
    'logo', 'icon', 'banner', 'button', 'social', 'vk', 'fb', 'instagram', 
    'cart', 'avatar', 'payment', 'header', 'footer', 'pixel'
]

# Ключевые слова для поиска подарков и упаковки
TARGET_KEYWORDS = [
    'подар', 'упаков', 'короб', 'новогод', 'каталог', '2024', '2025', 
    'gift', 'box', 'new-year', 'catalog', 'ny'
]

st.set_page_config(page_title="Поиск новогодних каталогов ЕАЭС", page_icon="🎁")
st.title("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ")

def is_relevant(text):
    """Проверяет, относится ли текст или ссылка к подаркам/упаковке"""
    text = text.lower()
    return any(word in text for word in TARGET_KEYWORDS)

def is_blocked(url):
    """Проверяет, не является ли файл баннером или логотипом"""
    url = url.lower()
    return any(bad in url for bad in DOC_BLACKLIST_STEMS)

def get_site_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        st.error(f"Ошибка доступа к {url}: {e}")
        return None

def process_site(domain):
    if not domain.startswith(('http://', 'https://')):
        domain = 'https://' + domain
    
    st.info(f"Сканируем: {domain}...")
    soup = get_site_content(domain)
    if not soup:
        return

    found_pdfs = []
    found_images = []

    # 1. Ищем PDF каталоги
    for a in soup.find_all('a', href=True):
        href = urljoin(domain, a['href'])
        link_text = a.get_text().strip()
        
        if href.lower().endswith('.pdf'):
            if is_relevant(link_text) or is_relevant(href):
                found_pdfs.append({'url': href, 'name': link_text or "Каталог PDF"})

    # 2. Если PDF не нашли или нужно собрать картинки как "каталог"
    # Ищем картинки, которые похожи на товары/упаковку
    for img in soup.find_all('img', src=True):
        src = urljoin(domain, img['src'])
        alt = img.get('alt', '').strip()
        
        # Фильтруем: должен быть релевантным И не быть в блэклисте (лого/баннеры)
        if not is_blocked(src) and (is_relevant(alt) or is_relevant(src)):
            name = alt if alt else src.split('/')[-1]
            found_images.append({'url': src, 'name': name})

    # ВЫВОД РЕЗУЛЬТАТОВ
    if found_pdfs:
        st.subheader("📄 Найденные PDF каталоги:")
        for pdf in found_pdfs:
            st.markdown(f"**[{pdf['name']}]({pdf['url']})**")
    
    if found_images:
        st.subheader(f"🖼 Найдено картинок упаковки/подарков: {len(found_images)}")
        
        # Кнопка создания архива
        if st.button("📥 Создать архив с картинками"):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for i, img in enumerate(found_images):
                    try:
                        img_data = requests.get(img['url'], timeout=5).content
                        # Чистим имя файла от запрещенных символов
                        clean_name = re.sub(r'[^\w\-_.]', '_', img['name'])
                        if not clean_name.lower().endswith(('.jpg', '.png', '.jpeg')):
                            clean_name += ".jpg"
                        
                        zip_file.writestr(f"{clean_name}", img_data)
                    except:
                        continue
            
            st.download_button(
                label="💾 Скачать ZIP-архив картинок",
                data=zip_buffer.getvalue(),
                file_name="ny_catalog_images.zip",
                mime="application/zip"
            )

# --- ИНТЕРФЕЙС ---
url_input = st.text_input("Введите адрес сайта заказчика (например, spartak.by или site.ru):")

if url_input:
    process_site(url_input)
