import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import streamlit as st
import time

# 1. Настройка страницы
st.set_page_config(page_title="Поиск новогодних каталогов", page_icon="🎁", layout="centered")

st.markdown("""
    <style>
    .reportview-container { background: #f0f2f6; }
    .catalog-box { border: 2px solid #28a745; background-color: #ffffff; padding: 20px; border-radius: 15px; margin-bottom: 20px; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
    .download-btn { background-color: #28a745; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block; margin-top: 10px; }
    .status-text { color: #555; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

st.title("🎁 Поиск новогодних каталогов")
st.write("Просто введите название фабрики. Система сама найдет сайт и вытянет прайсы.")

# --- МОЩНЫЙ ПОИСКОВОЙ ДВИЖОК ---

def get_links_from_url(url):
    """Сканирует сайт на наличие документов и новогодних разделов"""
    found = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = a['href'].lower()
                text = a.get_text().lower()
                
                # Ищем PDF, XLS или слова "новогодний", "каталог", "подарки"
                is_doc = any(ext in link for ext in [".pdf", ".xlsx", ".xls"])
                is_ny = any(word in text or word in link for word in ["новогод", "подарки", "каталог", "catalog", "price", "нг"])
                
                # Убираем мусор (соглашения, политики)
                is_trash = any(trash in text or trash in link for trash in ["согласие", "политика", "данных", "privacy"])
                
                if (is_doc or is_ny) and not is_trash:
                    full_url = urllib.parse.urljoin(url, a['href'])
                    if full_url not in [f['url'] for f in found]:
                        found.append({"title": a.get_text().strip() or "Открыть раздел", "url": full_url})
    except:
        pass
    return found

def find_everything(query):
    """Главная функция: ищет сайт, потом файлы на нем, потом файлы в сети"""
    all_results = []
    
    with DDGS() as ddgs:
        # 1. Находим официальный сайт
        site_search = list(ddgs.text(f"{query} официальный сайт кондитерская фабрика подарки", region='ru-ru', max_results=5))
        
        target_urls = []
        for s in site_search:
            link = s['href']
            # Исключаем мусорные домены справочников
            if not any(bad in link for bad in ["kartoteka", "list-org", "audit-it", "synapsenet", "google", "yandex"]):
                target_urls.append(link)
        
        # 2. Сканируем найденные сайты (особенно первый)
        if target_urls:
            with st.status(f"Проверяю сайты фабрики {query}...", expanded=False) as status:
                for site in target_urls[:2]: # Берем первые два наиболее вероятных сайта
                    st.write(f"Сканирую: {site}")
                    links = get_links_from_url(site)
                    all_results.extend(links)
                status.update(label="Сканирование завершено!", state="complete")

        # 3. Дополнительно ищем прямые PDF в интернете, если на сайте пусто
        pdf_search = list(ddgs.text(f'"{query}" новогодний каталог 2025 filetype:pdf', region='ru-ru', max_results=5))
        for p in pdf_search:
            if not any(trash in p['href'].lower() for trash in ["согласие", "политика"]):
                all_results.append({"title": p['title'], "url": p['href']})
                
    return all_results

# --- ИНТЕРФЕЙС ---

name = st.text_input("Название компании (например: Лаконд):", placeholder="Введите название...")

if st.button("🚀 НАЙТИ ВСЕ КАТАЛОГИ", type="primary"):
    if not name:
        st.error("Пожалуйста, введите название.")
    else:
        results = find_everything(name)
        
        st.markdown("---")
        if results:
            st.success(f"Найдено ресурсов: {len(results)}")
            
            # Убираем дубликаты ссылок
            unique_results = {res['url']: res for res in results}.values()
            
            for res in unique_results:
                icon = "📕" if ".pdf" in res['url'].lower() else "🌐"
                st.markdown(f"""
                <div class="catalog-box">
                    <h3 style="margin:0; font-size:18px;">{icon} {res['title']}</h3>
                    <p class="status-text">Источник: {urllib.parse.urlparse(res['url']).netloc}</p>
                    <a href="{res['url']}" target="_blank" class="download-btn">📥 ОТКРЫТЬ / СКАЧАТЬ</a>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.error("К сожалению, прямых ссылок не найдено. Попробуйте уточнить название или проверьте VK.")
            st.link_button("🔎 Искать вручную в VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(name + ' новогодние подарки 2025')}")

st.divider()
st.caption("Подсказка: если ввели 'Лаконд' и ничего не нашлось, попробуйте 'Лаконд Донецк'. Система ищет по актуальной базе 2025 года.")
