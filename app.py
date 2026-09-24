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
    .stApp { background-color: #f8f9fa; }
    .download-card { 
        background-color: #ffffff; border: 2px solid #28a745; 
        padding: 25px; border-radius: 15px; margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        text-align: center;
    }
    .btn-download {
        background-color: #28a745; color: white !important;
        padding: 15px 30px; border-radius: 10px; text-decoration: none;
        font-weight: bold; display: inline-block; font-size: 18px;
        transition: 0.3s;
    }
    .btn-download:hover { background-color: #218838; transform: scale(1.05); }
    .info-text { color: #666; font-size: 14px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Авто-Экстрактор Каталогов 2026")
st.write("Введите название фабрики. Система сама найдет и выведет **прямую кнопку на скачивание** каталога.")

# --- УМНАЯ ЛОГИКА ПОИСКА ---

def is_catalog_link(text, url):
    """Проверяет, является ли ссылка реальным каталогом новогодних подарков"""
    c = (text + url).lower()
    # Исключаем мусор сразу
    if any(bad in c for bad in ["policy", "privacy", "согласие", "вакансии", "хоккей", "акции", "инвест"]):
        return False
    # Ищем признаки подарков 2026 (Год Лошади)
    keywords = ["каталог", "прайс", "подарки", "2026", "лошад", "нг", "новогод", "catalog", "price", "pdf", "xlsx"]
    return any(k in c for k in keywords)

def get_direct_catalog(query):
    """Ищет прямые ссылки на файлы в сети"""
    results = []
    # Запрос: Название + Новогодние подарки 2026 / Год лошади
    search_q = f'"{query}" кондитерская фабрика новогодние подарки каталог 2026 OR "год лошади" filetype:pdf OR filetype:xlsx'
    
    try:
        with DDGS() as ddgs:
            resp = ddgs.text(search_q, region='ru-ru', max_results=10)
            for r in resp:
                if is_catalog_link(r['title'], r['href']):
                    results.append({"title": r['title'], "url": r['href']})
    except:
        pass
    return results

def scan_official_site(query):
    """Находит сайт и сканирует его на наличие кнопок 'Скачать'"""
    try:
        with DDGS() as ddgs:
            # Находим сайт
            site_search = list(ddgs.text(f"{query} официальный сайт кондитерская фабрика", max_results=2))
            if site_search:
                url = site_search[0]['href']
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                soup = BeautifulSoup(res.text, "html.parser")
                links = []
                for a in soup.find_all("a", href=True):
                    if is_catalog_link(a.get_text(), a['href']):
                        full_url = urllib.parse.urljoin(url, a['href'])
                        links.append({"title": a.get_text().strip() or "Каталог на сайте", "url": full_url})
                return links
    except:
        return []
    return []

# --- ИНТЕРФЕЙС ---

name = st.text_input("Название фабрики (например: Лаконд, Баян Сулу, Акконд):", placeholder="Введите название...")

if st.button("🚀 ПОЛУЧИТЬ ПРЯМУЮ ССЫЛКУ", type="primary"):
    if not name:
        st.error("Введите название!")
    else:
        st.write(f"🔍 Ищу каталог **{name}** на сезон **2026 (Год Лошади)**...")
        
        with st.spinner("Работаю... Вытягиваю прямые ссылки на документы..."):
            # Пробуем найти прямые файлы
            final_links = get_direct_catalog(name)
            
            # Если в сети мало файлов, лезем на официальный сайт
            if len(final_links) < 2:
                final_links += scan_official_site(name)
            
            # Убираем дубликаты
            unique = {l['url']: l for l in final_links}.values()
            
            st.markdown("---")
            
            if unique:
                st.success(f"Найдено ресурсов: {len(unique)}")
                for l in unique:
                    icon = "📕" if ".pdf" in l['url'].lower() else "📊"
                    st.markdown(f"""
                    <div class="download-card">
                        <div class="info-text">Найдено: {l['title']}</div>
                        <a href="{l['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ КАТАЛОГ {icon}</a>
                        <div style="margin-top:10px; font-size:11px; color:#aaa;">Источник: {urllib.parse.urlparse(l['url']).netloc}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error("Прямая ссылка на файл не найдена автоматически.")
                st.info("💡 **Совет:** Попробуйте уточнить название (например, 'Лаконд Донецк') или используйте поиск в VK, так как многие файлы еще закрыты паролями на сайтах.")
                st.link_button("📱 Искать прайс в ВКонтакте", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(name + ' подарки 2026')}")

st.divider()
st.caption("Приложение настроено на поиск каталогов 2026 года (символ: Лошадь). Весь мусор отсекается автоматически.")
