import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import streamlit as st

# 1. Настройка страницы
st.set_page_config(page_title="Поиск каталогов 2025", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .file-card { background-color: #ffffff; border: 1px solid #e2e8f0; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #ff4b4b; }
    .stButton>button { background-color: #ff4b4b; color: white; border-radius: 8px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# Определение года (Ставим 2025 как основной для текущего сезона)
st.title("🍬 Универсальный поиск каталогов")
target_year = st.selectbox("Выберите год для поиска:", [2024, 2025, 2026], index=1)

# --- ФУНКЦИИ ---

# Глубокий сканер сайта (ищет файлы прямо внутри домена)
def deep_scan_site(url):
    files = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Ищем все ссылки на PDF, XLS, XLSX
            for a in soup.find_all("a", href=True):
                link = a['href'].lower()
                if any(ext in link for ext in [".pdf", ".xlsx", ".xls"]):
                    full_url = urllib.parse.urljoin(url, a['href'])
                    title = a.get_text(strip=True) or "Скачать каталог/прайс"
                    files.append({"title": title, "url": full_url})
    except:
        pass
    return files

# Поиск через DuckDuckGo с фильтрами
def smart_search(query):
    results = []
    try:
        with DDGS() as ddgs:
            # Добавляем регион Россия и русский язык
            ddg_gen = ddgs.text(query, region='ru-ru', safesearch='off', max_results=10)
            for r in ddg_gen:
                results.append(r)
    except:
        pass
    return results

# --- ИНТЕРФЕЙС ---

query_input = st.text_input("Название компании или сайт (например: Лаконд, donko.su, Акконд):", placeholder="Введите здесь...")

if st.button("🚀 Найти все каталоги и файлы"):
    if not query_input.strip():
        st.error("Введите название!")
    else:
        q = query_input.strip()
        st.write(f"### 🎯 Результаты для '{q}' на {target_year} год:")
        
        with st.spinner("Выполняю глубокий поиск документов..."):
            
            # 1. Сначала ищем официальный сайт
            search_query = f"{q} официальный сайт новогодние подарки каталог {target_year}"
            web_results = smart_search(search_query)
            
            found_anything = False
            
            # 2. Если в результатах есть ссылки, сканируем их на наличие PDF
            if web_results:
                for res in web_results[:3]: # Проверяем первые 3 результата
                    site_url = res['href']
                    st.write(f"🔎 Проверяю сайт: `{site_url}`")
                    
                    files_on_site = deep_scan_site(site_url)
                    
                    if files_on_site:
                        found_anything = True
                        for f in files_on_site:
                            # Фильтруем, чтобы год был в названии или ссылке (или просто выводим всё)
                            st.markdown(f"""
                            <div class="file-card">
                                <b>📄 {f['title']}</b><br>
                                <a href="{f['url']}" target="_blank">📥 СКАЧАТЬ ФАЙЛ (PDF/XLS)</a>
                            </div>
                            """, unsafe_allow_html=True)
            
            # 3. Дополнительный поиск прямых PDF через поисковик
            st.markdown("---")
            st.write("### 🌍 Дополнительные находки в сети:")
            direct_query = f"{q} новогодние подарки каталог {target_year} filetype:pdf"
            direct_files = smart_search(direct_query)
            
            for item in direct_files:
                if any(ext in item['href'].lower() for ext in [".pdf", ".xlsx", ".doc"]):
                    found_anything = True
                    st.markdown(f"✅ **[{item['title']}]({item['href']})**")
                    st.caption(item['body'])
            
            if not found_anything:
                st.warning("Автоматика не смогла скачать файл напрямую. Попробуйте нажать кнопку ниже для ручного просмотра.")
                
        # Резервные кнопки
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            g_url = f"https://www.google.com/search?q={urllib.parse.quote(q + ' каталог ' + str(target_year) + ' pdf')}"
            st.link_button("🔎 Открыть поиск Google", g_url)
        with c2:
            vk_url = f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(q + ' новогодние подарки ' + str(target_year))}"
            st.link_button("📱 Искать в VK (Прайсы)", vk_url)
