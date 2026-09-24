import datetime
import re
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st

# 1. Конфигурация страницы
st.set_page_config(
    page_title="Поисковик Новогодних Каталогов и Прайсов",
    page_icon="🎁",
    layout="wide",
)

# Вычисление актуального сезона
now = datetime.datetime.now()
default_year = now.year + 1 if now.month >= 8 else now.year

st.title("🎁 Автоматический Движок Поиска Каталогов и Прайсов")
st.caption(
    "Универсальный инструмент: ищет прямые PDF-файлы, Excel-прайсы и официальные новогодние страницы любых компаний."
)

# Боковая панель
with st.sidebar:
    st.header("⚙️ Параметры поиска")
    target_year = st.number_input(
        "Целевой год каталога:",
        min_value=2024,
        max_value=2030,
        value=default_year,
    )
    search_type = st.radio(
        "Что ищем в первую очередь?",
        [
            "📄 Прямые файлы (PDF / Excel / Прайсы)",
            "🌐 Веб-страницы каталогов",
            "📱 Поиск в соцсетях (VK / Telegram)",
        ],
    )


# 2. Модуль Умного Поиска через DuckDuckGo API
def search_duckduckgo(query, max_results=10):
    try:
        results = []
        with DDGS() as ddgs:
            ddg_gen = ddgs.text(query, max_results=max_results)
            if ddg_gen:
                for r in ddg_gen:
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "link": r.get("href", ""),
                            "snippet": r.get("body", ""),
                        }
                    )
        return results
    except Exception as e:
        st.error(f"Ошибка обращения к поисковому серверу: {e}")
        return []


# 3. Модуль прямой проверки сайта (если ввели домен)
def scan_website_for_pdfs(domain, year):
    if not domain.startswith("http"):
        url = f"https://{domain}"
    else:
        url = domain

    found_files = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Ищем ссылки на PDF, XLS и упоминания каталога/прайса
                if any(
                    ext in href.lower()
                    for ext in [".pdf", ".xlsx", ".xls", ".doc"]
                ) or any(
                    kw in href.lower()
                    for kw in ["catalog", "price", "novogod", "podarki"]
                ):
                    full_link = urllib.parse.urljoin(url, href)
                    title = a.get_text(strip=True) or "Скачать документ"
                    found_files.append({"title": title, "link": full_link})
    except Exception:
        pass
    return found_files


# --- ОСНОВНОЙ ИНТЕРФЕЙС ---

user_query = st.text_input(
    "🔎 Введите название компании, бренд, фабрику или сайт:",
    placeholder="Например: Красный Мозырянин, КФ Победа, glavupak.ru, ИП Сарыева...",
)

if st.button("🚀 Найти актуальный каталог / прайс", type="primary"):
    if not user_query.strip():
        st.warning("Пожалуйста, введите запрос для поиска!")
    else:
        query = user_query.strip()
        st.markdown("---")
        st.subheader(
            f"🎯 Результаты поиска каталогов на {target_year} год для: **{query}**"
        )

        # Проверка: ввели сайт или просто название?
        is_domain = (
            "." in query
            and " " not in query
            and not query.endswith(".")
            and len(query) > 3
        )

        with st.spinner("Идет сканирование сети и поиск файлов..."):

            # --- ЭТАП 1: Сканирование сайта напрямую (если введен домен) ---
            if is_domain:
                st.info(f"🌐 Обнаружен прямой сайт `{query}`. Сканируем структуру...")
                site_files = scan_website_for_pdfs(query, target_year)
                if site_files:
                    st.success(
                        f"Найдено документов прямо на сайте: {len(site_files)}"
                    )
                    for item in site_files[:5]:
                        st.markdown(f"👉 [{item['title']}]({item['link']})")
                else:
                    st.write(
                        "Прямых файлов на главной странице не обнаружено, выполняем глубокий поиск..."
                    )

            # --- ЭТАП 2: Поиск прямых документов (PDF/XLS) ---
            if "Прямые файлы" in search_type or is_domain:
                st.write("### 📄 Найденные файлы каталогов и прайс-листов:")

                file_query = f"{query} (новогодние подарки OR каталог OR прайс) {target_year} filetype:pdf OR filetype:xlsx"
                file_results = search_duckduckgo(file_query, max_results=8)

                # Фильтруем результаты, где действительно есть файлы или каталоги
                pdfs_found = 0
                for item in file_results:
                    link = item["link"]
                    if any(
                        ext in link.lower()
                        for ext in [".pdf", ".xlsx", ".xls", ".doc"]
                    ) or any(
                        kw in link.lower()
                        for kw in [
                            "catalog",
                            "price",
                            "novogod",
                            "podark",
                            "2025",,
                            "2026",
                        ]
                    ):
                        pdfs_found += 1
                        st.markdown(f"📥 **[{item['title']}]({link})**")
                        st.caption(
                            f"Ссылка: {link}\n\n_{item['snippet'][:150]}..._"
                        )
                        st.markdown("---")

                if pdfs_found == 0:
                    st.warning(
                        "Прямых PDF/Excel файлов в открытом доступе не найдено. Смотрите разделы на сайтах ниже 👇"
                    )

            # --- ЭТАП 3: Поиск веб-страниц и веб-каталогов ---
            st.write("### 🌐 Официальные страницы и веб-каталоги:")
            web_query = f"{query} новогодние подарки каталог {target_year}"
            web_results = search_duckduckgo(web_query, max_results=6)

            if web_results:
                for item in web_results:
                    st.markdown(f"🔗 **[{item['title']}]({item['link']})**")
                    st.write(f"_{item['snippet']}_")
                    st.markdown("---")
            else:
                st.write("Страниц по строгому запросу не найдено.")

            # --- ЭТАП 4: Поиск в Соцсетях (для ИП, ДНР, локальных поставщиков) ---
            st.write("### 📱 Поиск прайсов в VK / Telegram / Соцсетях:")
            social_query = (
                f"{query} новогодние подарки прайс каталог {target_year} vk.com"
            )
            social_results = search_duckduckgo(social_query, max_results=3)

            if social_results:
                for item in social_results:
                    st.markdown(f"💬 **[{item['title']}]({item['link']})**")
            else:
                st.write("Записей в соцсетях не найдено.")

        # Резервные кнопки быстрых переходов
        st.markdown("---")
        st.write("### 🚀 Если нужный файл закрыт, открыть поиск в один клик:")
        c1, c2, c3 = st.columns(3)
        with c1:
            g_url = f"https://www.google.com/search?q={urllib.parse.quote(query + ' новогодние подарки каталог ' + str(target_year) + ' filetype:pdf')}"
            st.link_button(f"🔍 Google (Поиск PDF {target_year})", g_url)
        with c2:
            y_url = f"https://yandex.ru/search/?text={urllib.parse.quote(query + ' новогодние подарки каталог прайс ' + str(target_year))}"
            st.link_button(f"🟡 Яндекс (Поиск прайсов)", y_url)
        with c3:
            vk_url = f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(query + ' новогодние подарки ' + str(target_year))}"
            st.link_button(f"🔵 Поиск ВКонтакте", vk_url)
