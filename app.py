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

# Базовые настройки
st.set_page_config(page_title="Поиск Подарков", page_icon="🎁")
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# 1. ФУНКЦИЯ ПОИСКА САЙТА (КАК ЯНДЕКС)
def find_site(company_name):
    try:
        with DDGS() as ddgs:
            # Ищем официальный сайт и каталог
            query = f"{company_name} официальный сайт новогодние подарки каталог"
            results = list(ddgs.text(query, max_results=5))
            for r in results:
                url = r['href']
                # Пропускаем мусор (соцсети и справочники)
                if not any(x in url.lower() for x in ['vk.com', 'ok.ru', 'facebook', 'instagram', 'youtube', 'wikipedia', '2gis', 'avito']):
                    return url
    except:
        pass
    return None

# 2. ФУНКЦИЯ СБОРА ДАННЫХ
def scan_site(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'lxml')
        domain = urllib.parse.urlparse(url).netloc
    except:
        return [], []

    pdfs = []
    imgs = []
    
    # Ключевые слова для фильтра (только подарки и упаковка)
    keywords = ['подар', 'набор', 'новогод', 'короб', 'упаков', 'туб', 'каталог', '2025', '2026', '2027']

    # Ищем PDF
    for a in soup.find_all('a', href=True):
        href = urllib.parse.urljoin(url, a['href'])
        if href.lower().endswith('.pdf'):
            if any(k in (a.get_text() + href).lower() for k in keywords):
                pdfs.append({'name': a.get_text().strip() or "Каталог", 'url': href})

    # Ищем картинки (проверяем src и data-src)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if not src: continue
        img_url = urllib.parse.urljoin(url, src)
        alt = (img.get('alt') or "").lower()
        
        # Только подарки! Исключаем логотипы и иконки
        if any(k in (alt + img_url).lower() for k in keywords):
            if not any(bad in img_url.lower() for bad in ['logo', 'icon', 'social', 'banner', 'visa', 'truck']):
                imgs.append(img_url)

    return pdfs, list(set(imgs))

# 3. ФУНКЦИЯ СКАЧИВАНИЯ КАРТИНКИ
def download_image(url):
    try:
        # Если напрямую не дает, пробуем через графический мост (всегда работает)
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if r.status_code != 200:
            proxy_url = f"https://wsrv.nl/?url={urllib.parse.quote(url)}"
            r = requests.get(proxy_url, timeout=10)
        
        if len(r.content) > 5000: # Игнорируем мелочь
            img = Image.open(io.BytesIO(r.content))
            fmt = img.format.lower()
            return {'bytes': r.content, 'ext': fmt if fmt else 'jpg'}
    except:
        pass
    return None

# ИНТЕРФЕЙС
st.title("🚀 Быстрый поиск новогодних каталогов")
company = st.text_input("Название компании:", placeholder="Например: Абинекс")

if company:
    if st.button("НАЙТИ"):
        site = find_site(company)
        if site:
            st.success(f"Найден сайт: {site}")
            with st.spinner("Собираем подарки..."):
                pdfs, imgs = scan_site(site)
                
                # Если PDF нет, пишем об этом
                if pdfs:
                    st.subheader("📄 Найдены каталоги (PDF):")
                    for p in pdfs:
                        st.markdown(f"[{p['name']}]({p['url']})")
                
                # Собираем картинки в архив
                if imgs:
                    st.subheader(f"🖼 Найдено картинок подарков: {len(imgs)}")
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                            results = list(executor.map(download_image, imgs[:500]))
                            count = 0
                            for res in results:
                                if res:
                                    count += 1
                                    zf.writestr(f"gift_{count}.{res['ext']}", res['bytes'])
                    
                    if count > 0:
                        st.download_button("📥 СКАЧАТЬ ВСЕ КАРТИНКИ (ZIP)", zip_buffer.getvalue(), f"{company}_podarki.zip", "application/zip")
                    
                    # Показываем превью
                    cols = st.columns(4)
                    for i, url in enumerate(imgs[:12]):
                        cols[i%4].image(url, use_container_width=True)
                else:
                    st.warning("Картинки подарков не найдены.")
        else:
            st.error("Не удалось найти сайт компании. Попробуйте ввести адрес вручную.")
