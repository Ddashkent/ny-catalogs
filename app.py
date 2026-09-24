import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import pandas as pd
import streamlit as st
import io
import zipfile

# 1. Настройка страницы
st.set_page_config(page_title="Визуальный Навигатор Подарков", page_icon="🖼️", layout="wide")

# АВТО-ГОД
now = datetime.datetime.now()
target_year = now.year + 1 if now.month >= 8 else now.year

st.title(f"🖼️ Визуальный Экстрактор Подарков {target_year}")
st.caption("Программа находит сайт, выгружает прайсы и скачивает все изображения продукции.")

# --- БАЗА И ФИЛЬТРЫ ---
KNOWLEDGE_BASE = {
    "лаконд": "lakond.ru", "акконд": "akkond.ru", "донко": "donko.su", "тор": "donko.su",
    "рубин": "rubin-2000.ru", "дилявер": "dilaver.ru", "главупак": "glavupak.ru",
    "коммунарка": "kommunarka.by", "спартак": "spartak.by", "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz", "славянка": "slavyanka.ru", "победа": "pobeda.market"
}

# --- УМНЫЕ ФУНКЦИИ ---

def find_site(query):
    if query.lower() in KNOWLEDGE_BASE: return KNOWLEDGE_BASE[query.lower()]
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{query}" кондитерская фабрика официальный сайт', max_results=3))
            for r in res:
                if not any(x in r['href'] for x in ["wiki", "otzovik", "checko"]):
                    return urllib.parse.urlparse(r['href']).netloc
    except: return None

def get_assets(url):
    """Собирает ссылки на документы и картинки"""
    docs, imgs = [], []
    try:
        res = requests.get(f"http://{url}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 1. Поиск документов
        for a in soup.find_all("a", href=True):
            h = a['href'].lower()
            if any(ext in h for ext in [".pdf", ".xlsx", ".xls"]):
                docs.append({"title": a.get_text().strip() or "Файл", "link": urllib.parse.urljoin(f"http://{url}", a['href'])})
        
        # 2. Поиск картинок (фильтруем логотипы и иконки)
        for img in soup.find_all("img", src=True):
            src = img['src']
            # Игнорируем иконки соцсетей, логотипы и мелкий мусор
            if any(x in src.lower() for x in ["logo", "icon", "facebook", "vk", "instagram", "telegr", "wp-content/plugins"]):
                continue
            full_img_url = urllib.parse.urljoin(f"http://{url}", src)
            if full_img_url not in imgs:
                imgs.append(full_img_url)
                
    except: pass
    return docs, imgs

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании:", placeholder="Например: Баян Сулу")

if st.button("🚀 ЗАПУСТИТЬ ПОЛНЫЙ СБОР ДАННЫХ", type="primary"):
    if company_query:
        site = find_site(company_query)
        if site:
            st.success(f"🌐 Сайт определен: `{site}`")
            docs, imgs = get_assets(site)
            
            tab1, tab2 = st.tabs(["📄 Документы и Файлы", "🖼️ Визуальный каталог (Картинки)"])
            
            with tab1:
                if docs:
                    for d in docs:
                        st.markdown(f"✅ **{d['title']}** — [Скачать]({d['link']})")
                else: st.warning("Прямых PDF/XLS файлов не найдено.")
            
            with tab2:
                if imgs:
                    st.write(f"Найдено изображений продукции: {len(imgs)}")
                    
                    # Кнопка скачивания всех картинок архивом
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
                        for i, img_url in enumerate(imgs[:40]): # Ограничим до 40 для скорости
                            try:
                                img_res = requests.get(img_url, timeout=5)
                                if img_res.status_code == 200:
                                    ext = img_url.split(".")[-1].split("?")[0]
                                    if len(ext) > 4: ext = "jpg"
                                    zip_file.writestr(f"product_{i+1}.{ext}", img_res.content)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ВСЕ КАРТИНКИ ОДНИМ АРХИВОМ (.ZIP)", zip_buffer.getvalue(), f"{company_query}_images.zip", "application/zip")
                    
                    # Сетка с картинками для просмотра
                    cols = st.columns(4)
                    for idx, img_url in enumerate(imgs[:20]):
                        cols[idx % 4].image(img_url, use_column_width=True)
                else:
                    st.warning("Изображения продукции не удалось извлечь автоматически.")
        else:
            st.error("Не удалось найти сайт компании.")

st.divider()
st.caption(f"Инструмент автоматически переключится на следующий сезон в августе {now.year} года.")
