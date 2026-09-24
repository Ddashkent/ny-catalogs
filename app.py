import datetime
import urllib.parse
from duckduckgo_search import DDGS
import streamlit as st

# Настройка страницы
st.set_page_config(
    page_title="Экспресс-Поиск Каталогов и Прайсов",
    page_icon="⚡",
    layout="centered",
)

# Определение года сезона
now = datetime.datetime.now()
target_year = now.year + 1 if now.month >= 8 else now.year

# Стилизация под минималистичный корпоративный инструмент
st.markdown(
    """
    <style>
    .stApp { background-color: #f8f9fa; }
    .main-title { font-size: 26px; font-weight: bold; color: #1e293b; margin-bottom: 5px; }
    .sub-title { font-size: 14px; color: #64748b; margin-bottom: 25px; }
    .file-card { background-color: #ffffff; border-left: 5px solid #10b981; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 12px; }
    .web-card { background-color: #ffffff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 12px; }
    </style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='main-title'>⚡ Экспресс-поиск Прайсов и Каталогов {target_year}</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='sub-title'>Универсальный инструмент для коммерческого отдела. Мгновенно вытягивает файлы каталогов и прайсы без работы с поисковиками.</div>",
    unsafe_allow_html=True,
)


# Функция фонового поиска прямых документов
def fetch_direct_assets(company_name, year):
    pdf_files = []
    excel_files = []
    web_catalogs = []

    # 1. Поиск файлов (PDF / XLSX)
    file_query = f'"{company_name}" (новогодние подарки OR каталог OR прайс) {year} (filetype:pdf OR filetype:xlsx OR filetype:xls)'

    try:
        with DDGS() as ddgs:
            # Ищем файлы
            raw_files = list(ddgs.text(file_query, max_results=12))
            for item in raw_files:
                link = item.get("href", "")
                title = item.get("title", "Файл каталога")
                snippet = item.get("body", "")

                if ".pdf" in link.lower():
                    pdf_files.append(
                        {"title": title, "link": link, "snippet": snippet}
                    )
                elif (
                    ".xlsx" in link.lower()
                    or ".xls" in link.lower()
                    or "прайс" in title.lower()
                ):
                    excel_files.append(
                        {"title": title, "link": link, "snippet": snippet}
                    )

            # 2. Если файлов мало, ищем прямую страницу интерактивного каталога
            if len(pdf_files) == 0:
                web_query = f'"{company_name}" каталог новогодних подарков {year} официальный сайт'
                raw_web = list(ddgs.text(web_query, max_results=5))
                for item in raw_web:
                    link = item.get("href", "")
                    title = item.get("title", "")
                    if not any(
                        bad in link
                        for bad in ["wikipedia", "youtube", "otzovik", "avito"]
                    ):
                        web_catalogs.append(
                            {
                                "title": title,
                                "link": link,
                                "snippet": item.get("body", ""),
                            }
                        )

    except Exception:
        pass

    return pdf_files, excel_files, web_catalogs


# Поле ввода
company_input = st.text_input(
    "Введите название компании, бренда или сайта:",
    placeholder="Например: КФ Победа, Красный Мозырянин, glavupak.ru...",
)

if st.button("🚀 Получить каталог / прайс", type="primary", use_container_width=True):
    if not company_input.strip():
        st.warning("Пожалуйста, введите название компании.")
    else:
        comp = company_input.strip()

        with st.spinner("Сканируем сеть и извлекаем прямые файлы..."):
            pdfs, excels, webs = fetch_direct_assets(comp, target_year)

        st.markdown("---")

        # ВЫВОД РЕЗУЛЬТАТОВ: ТОЛЬКО ПРЯМЫЕ ССЫЛКИ НА ФАЙЛЫ ИЛИ СТРАНИЦЫ

        # 1. Прямые PDF файлы
        if pdfs:
            st.success(f"✅ Найдены готовые PDF-каталоги ({len(pdfs)}):")
            for f in pdfs[:4]:
                st.markdown(
                    f"""
                <div class='file-card'>
                    <h4>📄 {f['title']}</h4>
                    <p style='font-size: 13px; color: #475569;'>{f['snippet'][:180]}...</p>
                    <a href='{f['link']}' target='_blank' style='background-color: #10b981; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;'>📥 Скачать / Открыть PDF</a>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # 2. Прямые Excel прайсы
        if excels:
            st.success(f"📊 Найдены Excel-прайсы / Таблицы ({len(excels)}):")
            for f in excels[:3]:
                st.markdown(
                    f"""
                <div class='file-card' style='border-left-color: #059669;'>
                    <h4>📊 {f['title']}</h4>
                    <a href='{f['link']}' target='_blank' style='background-color: #059669; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;'>📥 Скачать Прайс (Excel)</a>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # 3. Интерактивные веб-страницы каталогов (если PDF нет)
        if webs and not pdfs:
            st.info("🌐 Прямой PDF не опубликован, но найдена страница онлайн-каталога:")
            for w in webs[:3]:
                st.markdown(
                    f"""
                <div class='web-card'>
                    <h4>🌐 {w['title']}</h4>
                    <p style='font-size: 13px; color: #475569;'>{w['snippet'][:180]}...</p>
                    <a href='{w['link']}' target='_blank' style='background-color: #3b82f6; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;'>🔗 Открыть веб-каталог на сайте</a>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # 4. Если вообще ничего не найдено автоматически
        if not pdfs and not excels and not webs:
            st.error(
                "Файлы не найдены в открытом доступе. Возможно, компания высылает прайс только по запросу."
            )
            st.write("Попробуйте прямой поиск по соцсетям:")
            vk_url = f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={urllib.parse.quote(comp + ' новогодние подарки прайс ' + str(target_year))}"
            st.link_button("🔵 Проверить выложен ли прайс ВКонтакте", vk_url)
