import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st

# 1. Конфигурация страницы
st.set_page_config(
    page_title="Поисковик Новогодних Каталогов",
    page_icon="🎁",
    layout="wide",
)

# Вычисление актуального сезона
now = datetime.datetime.now()
default_year = now.year + 1 if now.month >= 8 else now.year

st.title("🎁 Автоматический поиск Новогодних Каталогов")
st.caption(
    "Универсальный инструмент: ищет PDF-файлы, Excel-прайсы и страницы каталогов любых компаний в реальном времени."
)

# Боковая панель
with st.sidebar:
    st.header("⚙️ Параметры")
    target_year = st.number_input(
        "Целевой год каталога:",
        min_value=2024,
        max_value=2030,
        value=default_year,
    )
    search_type = st.radio(
        "Что ищем?",
        [
            "📄 Прямые файлы (PDF / Excel)",
            "🌐 Веб-страницы каталогов",
            "📱 Соцсети (VK / Telegram)",
        ],
    )


# 2. Модуль Умного Поиска
def search_ddg(query, max_results=8):
    results = []
    try:
        with DDGS() as ddgs:
            ddg_gen = ddgs.text(query, max_results=max_results)
            for r in ddg_gen:
                results.append({
                    "title": r.get("title", ""),
                    "link": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
    except Exception as e:
        st.warning(f"Поисковый сервер временно отклонил запрос. Попробуйте еще раз через минуту.")
    return results


# 3. Модуль прямой проверки сайта
def scan_site(domain):
    found_files = []
    try:
        url = domain if domain.startswith("http") else f"https://{domain}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(ext in href for ext in [".pdf", ".xls", ".doc"]) or \
                   any(kw in href for kw in ["catalog", "price", "novogod"]):
                    full_link = urllib.parse.urljoin(url, a["href"])
                    found_files.append({"title": a.get_text(strip=True) or "Документ", "link": full_link})
    except:
        pass
    return found_files


# --- ИНТЕРФЕЙС ---

user_query = st.text_input(
    "🔎 Введите название компании, фабрики или адрес сайта:",
    placeholder="Например: Акконд, ТОР Донецк, kf-pobeda.ru, ИП Саляхов...",
)

if st.button("🚀 Найти каталог / прайс", type="primary"):
    if not user_query.strip():
        st.error("Введите название компании!")
    else:
        query = user_query.strip()
        st.markdown("---")
        st.subheader(f"🎯 Результаты для: {query} (Сезон {target_year})")

        is_domain = "." in query and " " not in query

        with st.spinner("Ищу информацию в сети..."):
            
            # 1. Сканирование сайта напрямую
            if is_domain:
                st.info(f"🌐 Сканируем домен {query}...")
                direct_files = scan_site(query)
                if direct_files:
                    for f in direct_files[:5]:
                        st.markdown(f"✅ [Найдено на сайте: {f['title']}]({f['link']})")
            
            # 2. Поиск файлов (PDF/XLS)
            st.write("### 📄 Найденные файлы и документы:")
            file_query = f"{query} новогодние подарки каталог {target_year} filetype:pdf OR filetype:xlsx"
            files = search_ddg(file_query)
            
            if files:
                for item in files:
                    st.markdown(f"📥 **[{item['title']}]({item['link']})**")
                    st.caption(f"{item['snippet'][:200]}...")
                    st.markdown("---")
            else:
                st.write("Прямых файлов не найдено. Проверьте веб-страницы ниже.")

            # 3. Поиск веб-страниц
            st.write("### 🌐 Официальные страницы и ссылки:")
            web_query = f"{query} каталог новогодних подарков {target_year}"
            web_res = search_ddg(web_query)
            
            for item in web_res:
                st.markdown(f"🔗 **[{item['title']}]({item['link']})**")
                st.markdown("---")

        # Резервные кнопки
        st.write("### 🚀 Быстрый переход в глобальный поиск:")
        c1, c2, c3 = st.columns(3)
        with c1:
            g_url = f"https://www.google.com/search?q={urllib.parse.quote(query + ' каталог подарков ' + str(target_year) + ' pdf')}"
            st.link_button("Google Поиск", g_url)
        with c2:
            y_url = f"https://yandex.ru/search/?text={urllib.parse.quote(query + ' прайс новогодние подарки ' + str(target_year))}"
            st.link_button("Яндекс Поиск", y_url)
        with c3:
            vk_url = f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(query + ' подарки ' + str(target_year))}"
            st.link_button("Поиск в VK", vk_url)
