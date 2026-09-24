import streamlit as st
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import urllib.parse
import re

# 1. Настройка страницы
st.set_page_config(page_title="Экстрактор каталогов 2026", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .reportview-container { background: #f8f9fa; }
    .download-card { 
        background-color: #ffffff; 
        border: 2px solid #28a745; 
        padding: 20px; 
        border-radius: 12px; 
        margin-bottom: 15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .btn-download {
        background-color: #28a745;
        color: white !important;
        padding: 10px 20px;
        border-radius: 6px;
        text-decoration: none;
        font-weight: bold;
        display: inline-block;
        margin-top: 10px;
    }
    .btn-download:hover { background-color: #218838; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Экстрактор подарков 2026")
st.write("Введите название фабрики. Программа сама найдет и вытянет прямую ссылку на скачивание файла.")

# Установка года сезона
target_year = 2026

# --- МОЗГ ПРОГРАММЫ ---

def is_valid_catalog(text, link):
    """Проверяет, является ли ссылка реальным каталогом подарков"""
    content = (text + link).lower()
    # Обязательные слова
    positive = ["каталог", "прайс", "подарки", "новогод", "нг", "из конфет", "catalog", "price", "pdf", "xls"]
    # Мусор (хоккей, акции, юристы)
    negative = ["hockey", "хоккей", "stock", "finance", "акции", "инвест", "политика", "данных", "privacy", "agreement", "согласие"]
    
    if any(neg in content for neg in negative):
        return False
    if any(pos in content for pos in positive):
        return True
    return False

def get_direct_files(query):
    """Ищет в сети прямые ссылки на PDF и Excel"""
    found_files = []
    
    # Формируем жесткий поисковый запрос, чтобы отсечь лишнее
    search_q = f'"{query}" кондитерская фабрика новогодние подарки каталог {target_year} filetype:pdf OR filetype:xlsx'
    
    try:
        with DDGS() as ddgs:
            # Ищем именно файлы
            res = list(ddgs.text(search_q, region='ru-ru', max_results=15))
            for item in res:
                link = item['href']
                title = item['title']
                
                if is_valid_catalog(title, link):
                    found_files.append({"title": title, "url": link})
    except:
        pass
    return found_files

def scan_official_site(query):
    """Находит сайт компании и пытается вытянуть файлы оттуда"""
    try:
        with DDGS() as ddgs:
            # 1. Находим основной сайт
            res = list(ddgs.text(f"{query} официальный сайт кондитерская фабрика", region='ru-ru', max_results=3))
            if res:
                base_url = res[0]['href']
                # 2. Заходим на сайт и ищем ссылки на PDF
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(base_url, headers=headers, timeout=7)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    site_files = []
                    for a in soup.find_all("a", href=True):
                        href = a['href']
                        text = a.get_text()
                        if is_valid_catalog(text, href):
                            full_url = urllib.parse.urljoin(base_url, href)
                            site_files.append({"title": text.strip() or "Каталог на сайте", "url": full_url})
                    return site_files
    except:
        pass
    return []

# --- ИНТЕРФЕЙС ---

company = st.text_input("Введите название компании (например: Лаконд):", placeholder="Название фабрики...")

if st.button("🚀 ПОЛУЧИТЬ ПРЯМУЮ ССЫЛКУ", type="primary"):
    if not company:
        st.error("Введите название!")
    else:
        st.write(f"🔍 Сканирую сеть для **{company}** на сезон **{target_year}**...")
        
        with st.spinner("Извлекаю прямые ссылки на файлы..."):
            # Метод 1: Поиск файлов в сети
            links = get_direct_files(company)
            
            # Метод 2: Поиск на официальном сайте
            links += scan_official_site(company)
            
            # Убираем дубликаты
            unique_links = {l['url']: l for l in links}.values()
            
            st.markdown("---")
            
            if unique_links:
                st.success(f"Найдено ресурсов: {len(unique_links)}")
                for l in unique_links:
                    icon = "📕" if ".pdf" in l['url'].lower() else "📊"
                    if not ".pdf" in l['url'].lower() and not ".xls" in l['url'].lower():
                        icon = "🌐"
                        
                    st.markdown(f"""
                    <div class="download-card">
                        <h4 style="margin:0;">{icon} {l['title']}</h4>
                        <p style="font-size:12px; color:gray;">Источник: {urllib.parse.urlparse(l['url']).netloc}</p>
                        <a href="{l['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ ФАЙЛ / ОТКРЫТЬ</a>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error("Прямых ссылок на файлы 2026 года не найдено.")
                st.info("💡 Совет: Многие фабрики еще не выложили каталоги 2026 в открытый доступ. Попробуйте найти их в VK:")
                st.link_button("🔎 Искать прайсы в ВКонтакте", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(company + ' подарки 2026')}")

st.divider()
st.caption("Система автоматически фильтрует финансовые новости, спорт и юридические документы.")
