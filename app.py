import streamlit as st
import urllib.parse
import datetime

# 1. Настройка страницы
st.set_page_config(page_title="Поиск новогодних каталогов", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .search-card { 
        background-color: #ffffff; 
        border: 2px solid #007bff; 
        padding: 20px; 
        border-radius: 12px; 
        margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .btn-link {
        background-color: #007bff; color: white !important;
        padding: 12px 20px; border-radius: 8px; text-decoration: none;
        font-weight: bold; display: block; text-align: center;
        margin-top: 10px;
    }
    .btn-link:hover { background-color: #0056b3; }
    .pdf-style { border-color: #dc3545; }
    .pdf-btn { background-color: #dc3545; }
    .pdf-btn:hover { background-color: #a71d2a; }
    .xls-style { border-color: #28a745; }
    .xls-btn { background-color: #28a745; }
    .xls-btn:hover { background-color: #1e7e34; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Навигатор Новогодних Каталогов")
st.write("Универсальный поиск каталогов и прайсов любых фабрик СНГ (Лаконд, Баян Сулу, Акконд и др.)")

# --- НАСТРОЙКИ ПОИСКА ---
col_y, col_q = st.columns([1, 3])
with col_y:
    target_year = st.selectbox("Год сезона:", [2025, 2026], index=0)
with col_q:
    query = st.text_input("Введите название фабрики:", placeholder="Например: Лаконд")

if query:
    q = query.strip()
    st.markdown("---")
    st.subheader(f"🎯 Сформированы снайперские ссылки для {q} ({target_year}):")

    # Формируем запросы с фильтрацией мусора
    # Исключаем хоккей, акции, медицину, инвесторов
    filter_trash = "-хоккей -hockey -stock -finance -акции -инвестиции -медицина -вакансии"
    
    # 1. Запрос для PDF каталогов
    pdf_q = urllib.parse.quote(f'"{q}" кондитерская фабрика новогодние подарки каталог {target_year} filetype:pdf {filter_trash}')
    
    # 2. Запрос для Excel прайсов
    xls_q = urllib.parse.quote(f'"{q}" новогодние подарки прайс-лист {target_year} (xls OR xlsx) {filter_trash}')
    
    # 3. Запрос для VK (для ИП и тех, у кого нет сайта)
    vk_q = urllib.parse.quote(f'"{q}" новогодние подарки {target_year}')
    
    # 4. Официальный сайт (поиск раздела продукции)
    site_q = urllib.parse.quote(f'"{q}" кондитерская фабрика официальный сайт подарки {target_year}')

    # ОТОБРАЖЕНИЕ КАРТОЧЕК
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"""
        <div class="search-card pdf-style">
            <h3 style="margin:0; color:#dc3545;">📕 PDF КАТАЛОГИ</h3>
            <p style="font-size:13px; color:#666;">Поиск прямых PDF-файлов с презентацией подарков на {target_year} год.</p>
            <a href="https://yandex.ru/search/?text={pdf_q}" target="_blank" class="btn-link pdf-btn">📥 НАЙТИ PDF КАТАЛОГИ</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #007bff;">
            <h3 style="margin:0; color:#007bff;">🔵 СОЦСЕТИ / VK</h3>
            <p style="font-size:13px; color:#666;">Поиск прайсов в ВКонтакте (актуально для фабрик ДНР и локальных ИП).</p>
            <a href="https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}" target="_blank" class="btn-link">📱 ИСКАТЬ В ВК</a>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="search-card xls-style">
            <h3 style="margin:0; color:#28a745;">📊 EXCEL ПРАЙСЫ</h3>
            <p style="font-size:13px; color:#666;">Поиск таблиц с ценами, весом и составами подарков.</p>
            <a href="https://yandex.ru/search/?text={xls_q}" target="_blank" class="btn-link xls-btn">📥 НАЙТИ EXCEL ПРАЙСЫ</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #ffc107;">
            <h3 style="margin:0; color:#856404;">🌐 САЙТ ФАБРИКИ</h3>
            <p style="font-size:13px; color:#666;">Переход на официальный сайт компании в раздел новогодней продукции.</p>
            <a href="https://yandex.ru/search/?text={site_q}" target="_blank" class="btn-link" style="background-color: #ffc107; color: black !important;">🔗 ПЕРЕЙТИ НА САЙТ</a>
        </div>
        """, unsafe_allow_html=True)

    st.success("💡 **Инструкция:** Если по 2026 году ничего не найдено (фабрика еще не обновилась), переключите год на **2025** вверху страницы.")

else:
    st.info("Введите название компании выше, чтобы мгновенно получить ссылки на её каталоги.")
