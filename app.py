import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import streamlit as st

# 1. Настройка страницы
st.set_page_config(page_title="Снайпер-поиск каталогов 2025", page_icon="🎯", layout="centered")

st.markdown("""
    <style>
    .result-card { background-color: #ffffff; border: 1px solid #e2e8f0; padding: 15px; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid #00c853; }
    .stButton>button { background-color: #00c853; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 Снайпер-поиск подарков")
st.caption("Поиск ТОЛЬКО новогодних каталогов и прайсов. Без политики конфиденциальности и юр. мусора.")

# Выбор года
target_year = st.selectbox("Год сезона:", [2024, 2025, 2026], index=1)

# --- СПИСКИ ФИЛЬТРАЦИИ ---
# Эти слова ОБЯЗАТЕЛЬНО должны быть в названии ссылки или файла
WHITELIST = ["каталог", "прайс", "подарки", "новогод", "нг", str(target_year), "catalog", "price", "podarki", "ассортимент"]

# Эти слова ЗАПРЕЩЕНЫ (юр. мусор)
BLACKLIST = [
    "политика", "конфиденциальность", "персональных", "данных", "согласие", 
    "соглашение", "обработку", "вакансии", "инн", "огрн", "устав", "privacy", 
    "policy", "agreement", "узнать подробнее", "статьи", "новости"
]

# Запрещенные домены (юр. порталы, справочники)
BLOCKED_DOMAINS = [
    "pravo.rg.ru", "pravoved.ru", "nasledstvovrf.ru", "consultant.ru", "garant.ru", 
    "audit-it.ru", "zakon.ru", "wikipedia.org", "otzovik.com", "avito.ru"
]

# --- ФУНКЦИИ ---

def is_clean_link(text, url):
    """Проверяет ссылку на соответствие новогодней тематике и отсутствие мусора"""
    full_content = (text + url).lower()
    
    # 1. Проверка на мусорные слова
    if any(bad in full_content for bad in BLACKLIST):
        return False
    
    # 2. Проверка на полезные слова (хотя бы одно должно быть)
    if not any(good in full_content for good in WHITELIST):
        return False
        
    return True

def deep_scan_site(url):
    """Сканирует сайт на наличие прямых PDF/XLS файлов с подарками"""
    if any(b_domain in url for b_domain in BLOCKED_DOMAINS):
        return []
        
    files = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                link = a['href'].lower()
                
                # Ищем только документы
                if any(ext in link for ext in [".pdf", ".xlsx", ".xls"]):
                    # Применяем фильтр "новогодней темы"
                    if is_clean_link(text, link):
                        full_url = urllib.parse.urljoin(url, a['href'])
                        files.append({"title": text or "Документ", "url": full_url})
    except:
        pass
    return files

def fetch_search_results(query):
    results = []
    try:
        with DDGS() as ddgs:
            # Делаем запрос максимально специфичным
            final_query = f"{query} новогодние подарки кондитерские изделия каталог {target_year}"
            ddg_gen = ddgs.text(final_query, region='ru-ru', max_results=15)
            for r in ddg_gen:
                if not any(b_domain in r['href'] for b_domain in BLOCKED_DOMAINS):
                    results.append(r)
    except:
        pass
    return results

# --- ИНТЕРФЕЙС ---

q_input = st.text_input("Введите название компании (Лаконд, Акконд и т.д.):", placeholder="Регистр не важен...")

if st.button("🚀 НАЙТИ КАТАЛОГИ И ПРАЙСЫ"):
    if not q_input.strip():
        st.error("Введите название!")
    else:
        q = q_input.strip()
        st.write(f"### 🔍 Ищем подарки для '{q}'...")
        
        with st.spinner("Фильтруем мусор, ищем каталоги..."):
            web_results = fetch_search_results(q)
            
            found_files = []
            
            # 1. Проверяем сайты из поиска
            if web_results:
                for res in web_results[:5]:
                    site_files = deep_scan_site(res['href'])
                    found_files.extend(site_files)
            
            # 2. Прямой поиск PDF файлов в сети
            pdf_query = f"{q} новогодние подарки каталог {target_year} filetype:pdf"
            pdf_results = fetch_search_results(pdf_query)
            for p in pdf_results:
                if is_clean_link(p['title'], p['href']):
                    found_files.append({"title": p['title'], "url": p['href']})

            # Убираем дубликаты
            unique_files = {f['url']: f for f in found_files}.values()

            # ВЫВОД РЕЗУЛЬТАТОВ
            if unique_files:
                st.success(f"Найдено документов: {len(unique_files)}")
                for f in unique_files:
                    st.markdown(f"""
                    <div class="result-card">
                        <div style="font-size: 16px; font-weight: bold; color: #1b5e20;">📦 {f['title']}</div>
                        <a href="{f['url']}" target="_blank" style="color: #00c853; text-decoration: none; font-weight: bold;">📥 СКАЧАТЬ КАТАЛОГ / ПРАЙС (PDF/XLS)</a>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Автоматика не нашла прямых файлов. Попробуйте кнопки ниже.")

        # Ручные ссылки
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            g_url = f"https://www.google.com/search?q={urllib.parse.quote(q + ' подарки каталог ' + str(target_year) + ' pdf')}"
            st.link_button("Google (Каталоги)", g_url)
        with c2:
            y_url = f"https://yandex.ru/search/?text={urllib.parse.quote(q + ' новогодние подарки прайс ' + str(target_year) + ' xls')}"
            st.link_button("Яндекс (Прайсы)", y_url)
        with c3:
            vk_url = f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(q + ' подарки ' + str(target_year))}"
            st.link_button("ВКонтакте (Прайсы)", vk_url)
