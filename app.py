import io
import re
import zipfile
import datetime
import urllib.parse
import concurrent.futures

import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image
from duckduckgo_search import DDGS
import urllib3

# Отключение предупреждений
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройки времени
CURRENT_YEAR = datetime.date.today().year
TARGET_YEARS = {str(CURRENT_YEAR), str(CURRENT_YEAR + 1), str(CURRENT_YEAR + 2)}

# =========================================================
# ⚙️ СИСТЕМА ПОИСКА И ФИЛЬТРАЦИИ
# =========================================================

# Глобальные заголовки
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
}

def safe_fetch(url, timeout=10):
    """Загрузка страницы с корректной кодировкой"""
    try:
        # Обработка кириллических доменов (.бел, .рф)
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.encode('idna').decode('ascii')
        url = urllib.parse.urlunparse(parsed._replace(netloc=host))
        
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text, r.url
    except:
        pass
    return None, url

def is_target_site(company_query, html, url):
    """Профессиональная оценка сайта: подарки/конфеты + название компании"""
    if not html: return 0
    
    soup = BeautifulSoup(html, 'lxml')
    text = (soup.get_text() + " " + (soup.title.string if soup.title else "")).lower().replace('ё', 'е')
    
    # 🛑 ЧЕРНЫЙ СПИСОК (Анти-металл, Анти-стройка)
    bad_industries = ['металлопрокат', 'арматура', 'бетон', 'кирпич', 'автосервис', 'шины', 'ювелирный', 'недвижимость']
    if any(word in text for word in bad_industries):
        return -100

    score = 0
    # 🎯 КЛЮЧЕВЫЕ СЛОВА (Подарки, Конфеты)
    good_keywords = ['подарк', 'конфет', 'сладк', 'новогод', 'упаков', 'коробк', 'туб', 'набор', 'каталог']
    score += sum(20 for word in good_keywords if word in text)
    
    # 🏢 СОВПАДЕНИЕ НАЗВАНИЯ
    company_name = company_query.lower().strip()
    if company_name in text or company_name in url.lower():
        score += 50
        
    return score

# =========================================================
# 🕷 СКАНЕР КАТАЛОГОВ (КАРТОН / ТУБЫ)
# =========================================================

def scan_page(url):
    html, final_url = safe_fetch(url)
    if not html: return [], []
    
    soup = BeautifulSoup(html, 'lxml')
    pdfs, imgs = [], []
    
    # Поиск PDF
    for a in soup.find_all('a', href=True):
        href = urllib.parse.urljoin(final_url, a['href'])
        if href.lower().split('?')[0].endswith('.pdf'):
            title = a.get_text().strip()
            if any(w in (title + href).lower() for w in ['каталог', 'подарк', 'price', 'catalog']):
                pdfs.append({'name': title or "Каталог PDF", 'url': href})

    # Поиск Изображений (Только подарки/наборы)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if not src: continue
        full_src = urllib.parse.urljoin(final_url, src)
        alt = (img.get('alt') or "").lower()
        
        # Фильтр материала и типа (Картон, Тубы, Наборы)
        if any(w in (alt + full_src).lower() for w in ['набор', 'подар', 'короб', 'туб', 'мгк', 'картон']):
            if not any(bad in full_src.lower() for bad in ['logo', 'social', 'icon', 'banner']):
                imgs.append({'name': alt or "Новогодний набор", 'url': full_src})
                
    return pdfs, imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Первый Снег | Поиск", layout="wide", page_icon="❄️")
st.title("❄️ Поисковик и Экстрактор Новогодних Каталогов")

query = st.text_input("Введите название компании (например: Абинекс, СолБигТрейд, Спартак):", placeholder="Абинекс")

if query:
    with st.spinner(f"🔍 Ищем официальный сайт «{query}» в сети..."):
        # 1. Поиск кандидатов через DDGS
        candidates = []
        try:
            with DDGS() as ddgs:
                results = ddgs.text(f"{query} официальный сайт новогодние подарки конфеты", max_results=10)
                for r in results:
                    url = r['href']
                    # Отсекаем мусор
                    if not any(m in url for m in ['wildberries', 'ozon', 'avito', 'vk.com', 'wikipedia', 'youtube']):
                        candidates.append(url)
        except Exception as e:
            st.error("Ошибка поисковой системы. Попробуйте позже.")
            st.stop()

        # 2. Верификация тематики сайтов
        best_site = None
        max_score = -1
        
        for url in candidates:
            html, final_url = safe_fetch(url)
            score = is_target_site(query, html, final_url)
            if score > max_score:
                max_score = score
                best_site = final_url
        
        if not best_site or max_score < 10:
            st.error(f"❌ Не удалось найти сайт для «{query}», связанный с подарками.")
            st.stop()

    st.success(f"🌐 Найден подходящий сайт: **[{best_site}]({best_site})** (Релевантность: {max_score})")

    # 3. Глубокое сканирование каталога
    with st.spinner("📦 Анализируем структуру сайта и собираем наборы 2025-2027..."):
        domain = urllib.parse.urlparse(best_site).netloc
        
        # Собираем ссылки на разделы
        html, _ = safe_fetch(best_site)
        soup = BeautifulSoup(html, 'lxml')
        sections = {best_site}
        for a in soup.find_all('a', href=True):
            href = urllib.parse.urljoin(best_site, a['href']).split('#')[0]
            if domain in href and any(w in href.lower() for w in ['catalog', 'novogod', 'podarki', 'upakovka']):
                sections.add(href)
        
        all_pdfs, all_imgs = [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(scan_page, url) for url in list(sections)[:20]]
            for f in concurrent.futures.as_completed(futures):
                p, i = f.result()
                all_pdfs.extend(p)
                all_imgs.extend(i)

        # Удаление дублей
        pdfs = list({v['url']:v for v in all_pdfs}.values())
        imgs = list({v['url']:v for v in all_imgs}.values())

        # ВЫВОД
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"📄 PDF Каталоги ({len(pdfs)})")
            if pdfs:
                for p in pdfs:
                    st.markdown(f"• **[{p['name']}]({p['url']})**")
            else: st.info("PDF не найдены.")

        with col2:
            st.subheader(f"📦 Наборы и Упаковка ({len(imgs)})")
            if imgs:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, img in enumerate(imgs[:300]):
                        try:
                            r = requests.get(img['url'], timeout=5, verify=False).content
                            ext = img['url'].split('.')[-1][:3]
                            if ext not in ['jpg', 'png', 'web']: ext = 'jpg'
                            zf.writestr(f"item_{i+1}.{ext}", r)
                        except: continue
                
                st.download_button("📥 СКАЧАТЬ ZIP С КАРТИНКАМИ", zip_buffer.getvalue(), "packaging_2027.zip", type="primary")
                
                grid = st.columns(3)
                for idx, im in enumerate(imgs[:9]):
                    grid[idx%3].image(im['url'], caption=im['name'][:30], use_container_width=True)
            else: st.info("Изображения не найдены.")

st.divider()
st.caption("Инструмент «Первый Снег» | Поиск через DuckDuckGo | Полная автоматизация ЕАЭС")
