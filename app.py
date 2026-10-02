import io
import re
import zipfile
import requests
from bs4 import BeautifulSoup
from PIL import Image
import streamlit as st
from duckduckgo_search import DDGS
import urllib.parse
import concurrent.futures

# Настройки
st.set_page_config(page_title="Поиск Новогодних Каталогов", page_icon="🎁", layout="wide")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 1. ЗОЛОТОЙ РЕЕСТР (Для 100% точности по лидерам рынка)
GOLDEN_REGISTRY = {
    "спартак": "https://spartak.by",
    "коммунарка": "https://www.kommunarka.by",
    "абинекс": "https://podarok-k.ru",
    "солбигтрейд": "https://конфета.бел",
    "солбиг трейд": "https://конфета.бел",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru",
    "рахат": "https://rakhat.kz",
    "баян сулу": "https://www.bayansulu.kz",
    "миракс": "https://mirax-gifts.ru",
    "дилявер": "https://dilyaver.com",
    "росшоколад": "https://roschocolate.ru",
    "акконд": "https://akkond.ru",
}

# 2. ФУНКЦИЯ ПОИСКА (УМНЫЙ ЯНДЕКС-СТИЛЬ)
def find_official_site(name):
    name_low = name.lower().strip()
    
    # Сначала проверяем наш проверенный список
    if name_low in GOLDEN_REGISTRY:
        return GOLDEN_REGISTRY[name_low]
    
    # Если нет в списке, ищем в сети с уточняющими словами
    try:
        with DDGS() as ddgs:
            # Магический запрос, чтобы найти именно кондитерку/упаковку
            query = f"{name} официальный сайт кондитерская фабрика новогодние подарки упаковка каталог"
            results = ddgs.text(query, max_results=10)
            
            for r in results:
                url = r['href'].lower()
                # Жесткий фильтр мусора
                bad_sites = ['imdb.com', 'wikipedia', 'football', 'soccer', 'vk.com', 'ok.ru', 'facebook', 'instagram', 'youtube', '2gis', 'avito', 'otzovik']
                if not any(bad in url for bad in bad_sites):
                    return r['href']
    except:
        pass
    return None

# 3. СКАНЕР САЙТА
def scan_site(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        soup = BeautifulSoup(r.text, 'lxml')
        domain = urllib.parse.urlparse(url).netloc
    except:
        return [], []

    pdfs = []
    imgs = []
    
    # Ключевые слова (только подарки и упаковка)
    keywords = ['подар', 'набор', 'новогод', 'короб', 'упаков', 'туб', 'каталог', '2025', '2026', '2027', 'present', 'gift', 'box']

    # PDF Каталоги
    for a in soup.find_all('a', href=True):
        href = urllib.parse.urljoin(url, a['href'])
        if href.lower().split('?')[0].endswith('.pdf'):
            if any(k in (a.get_text() + href).lower() for k in keywords):
                pdfs.append({'name': a.get_text().strip() or "Новогодний каталог", 'url': href})

    # Картинки товаров
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if not src: continue
        img_url = urllib.parse.urljoin(url, src)
        alt = (img.get('alt') or img.get('title') or "").lower()
        
        # Фильтруем: только то, что похоже на подарки, и убираем иконки
        if any(k in (alt + img_url).lower() for k in keywords):
            if not any(bad in img_url.lower() for bad in ['logo', 'icon', 'social', 'banner', 'visa', 'cart', 'truck', 'header', 'footer']):
                imgs.append(img_url)

    return pdfs, list(set(imgs))

# 4. СКАЧИВАНИЕ
def download_img(url):
    try:
        # Используем мост для обхода защит
        proxy_url = f"https://wsrv.nl/?url={urllib.parse.quote(url)}&n=-1"
        r = requests.get(proxy_url, timeout=10)
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content
    except:
        pass
    return None

# ИНТЕРФЕЙС
st.title("🎁 Профессиональный поиск новогодних каталогов")
st.markdown("Поиск по базе производителей **ЕАЭС (РФ, РБ, КЗ)**. Автоматический отсев нецелевых сайтов.")

company = st.text_input("Введите название компании (например: Спартак, Абинекс, СолБигТрейд):", placeholder="Спартак")

if company:
    if st.button("🚀 НАЙТИ"):
        site = find_official_site(company)
        
        if site:
            st.success(f"✅ Найден официальный сайт: {site}")
            
            with st.spinner("Анализируем каталог подарков..."):
                pdfs, imgs = scan_site(site)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📄 PDF Каталоги")
                    if pdfs:
                        for p in pdfs:
                            st.info(f"👉 [{p['name']}]({p['url']})")
                    else:
                        st.write("Прямых PDF-файлов не найдено.")
                
                with col2:
                    st.subheader("🖼 Упаковка и подарки")
                    if imgs:
                        st.write(f"Найдено изображений: {len(imgs)}")
                        
                        # Кнопка архива
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w") as zf:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                                results = list(ex.map(download_img, imgs[:400]))
                                count = 0
                                for res in results:
                                    if res:
                                        count += 1
                                        zf.writestr(f"gift_{count}.jpg", res)
                        
                        if count > 0:
                            st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО (ZIP)", zip_buffer.getvalue(), f"{company}_catalog.zip", "application/zip")
                        
                        # Сетка картинок
                        grid = st.columns(3)
                        for i, url in enumerate(imgs[:12]):
                            grid[i%3].image(url, use_container_width=True)
                    else:
                        st.warning("Изображения подарков не найдены.")
        else:
            st.error("❌ Не удалось найти официальный сайт компании. Попробуйте ввести адрес (например: spartak.by)")
