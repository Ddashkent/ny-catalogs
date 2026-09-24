import streamlit as st
import urllib.parse
import datetime

# 1. Настройка страницы
st.set_page_config(page_title="Поиск новогодних каталогов 2025", page_icon="🍬")

st.markdown("""
    <style>
    .reportview-container { background: #f0f2f6; }
    .search-card { 
        border: 2px solid #ff4b4b; 
        background-color: #ffffff; 
        padding: 25px; 
        border-radius: 15px; 
        margin-bottom: 20px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
    }
    .btn-link { 
        background-color: #ff4b4b; 
        color: white !important; 
        padding: 12px 20px; 
        border-radius: 8px; 
        text-decoration: none; 
        font-weight: bold; 
        display: block; 
        text-align: center;
        margin-top: 10px;
    }
    .btn-link:hover { background-color: #d43f3f; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Навигатор кондитерских каталогов 2025")
st.write("Универсальный инструмент: находит прайсы и каталоги любых фабрик СНГ без лишнего мусора.")

# Определение года
year = 2025

# --- ИНТЕРФЕЙС ---

name = st.text_input("Введите название фабрики (например: Лаконд, Акконд, Славянка, Коммунарка):", placeholder="Регистр и точность сайта не важны...")

if name:
    st.markdown("---")
    st.write(f"### 🎯 Сформированы прямые пути для поиска **{name}**:")
    
    # Очищаем название для запроса
    clean_name = name.strip()
    
    # ФОРМИРУЕМ ГИПЕР-ТОЧНЫЕ ЗАПРОСЫ
    # 1. Поиск PDF в Яндексе (он лучше всего находит каталоги в РФ/СНГ)
    yandex_pdf_q = urllib.parse.quote(f'"{clean_name}" кондитерская фабрика новогодние подарки каталог {year} filetype:pdf')
    
    # 2. Поиск Прайсов в Excel
    yandex_xls_q = urllib.parse.quote(f'"{clean_name}" новогодние подарки прайс-лист {year} (xls OR xlsx)')
    
    # 3. Поиск в соцсетях (VK часто единственный источник прайсов для ДНР/локальных ИП)
    vk_q = urllib.parse.quote(f'"{clean_name}" новогодние подарки 2025')

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        <div class="search-card">
            <h3>📕 PDF КАТАЛОГИ</h3>
            <p>Открывает сразу список PDF файлов фабрики <b>{clean_name}</b> на 2025 год.</p>
            <a href="https://yandex.ru/search/?text={yandex_pdf_q}" target="_blank" class="btn-link">📥 ОТКРЫТЬ КАТАЛОГИ (PDF)</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #007bff;">
            <h3>🔵 ГРУППЫ И ПРАЙСЫ VK</h3>
            <p>Если сайта нет (как у многих ИП или фабрик ДНР), свежий прайс будет здесь.</p>
            <a href="https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}" target="_blank" class="btn-link" style="background-color: #007bff;">📱 ПОИСК В ВК</a>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="search-card" style="border-color: #28a745;">
            <h3>📊 EXCEL ПРАЙС-ЛИСТЫ</h3>
            <p>Поиск таблиц с ценами и составами подарков фабрики <b>{clean_name}</b>.</p>
            <a href="https://yandex.ru/search/?text={yandex_xls_q}" target="_blank" class="btn-link" style="background-color: #28a745;">📥 ОТКРЫТЬ ПРАЙСЫ (XLS)</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #ffc107;">
            <h3>🌐 ОФИЦИАЛЬНЫЙ САЙТ</h3>
            <p>Переход сразу в раздел новогодней продукции на сайте компании.</p>
            <a href="https://yandex.ru/search/?text={urllib.parse.quote(clean_name + ' кондитерская фабрика официальный сайт подарки')}" target="_blank" class="btn-link" style="background-color: #ffc107; color: black !important;">🔗 ПЕРЕЙТИ НА САЙТ</a>
        </div>
        """, unsafe_allow_html=True)

    st.info("💡 **Почему это удобно?** Менеджеру не нужно открывать Google Диск или мучиться с поиском. Каждая кнопка выше — это 'снайперский' запрос, который отсекает рекламу и показывает только файлы по теме.")
else:
    st.warning("Введите название компании выше, чтобы получить ссылки.")
