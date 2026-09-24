import streamlit as st
import urllib.parse

# 1. Настройка страницы
st.set_page_config(page_title="Навигатор Подарков 2026", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .search-card { 
        background-color: #ffffff; 
        border: 2px solid #ff4b4b; 
        padding: 25px; 
        border-radius: 15px; 
        margin-bottom: 20px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
        text-align: center;
    }
    .btn-link { 
        background-color: #ff4b4b; 
        color: white !important; 
        padding: 14px 25px; 
        border-radius: 10px; 
        text-decoration: none; 
        font-weight: bold; 
        display: block; 
        text-align: center;
        margin-top: 15px;
        font-size: 18px;
    }
    .btn-link:hover { background-color: #d43f3f; transform: scale(1.02); transition: 0.2s; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Навигатор Подарков 2026")
st.write("Универсальный поиск каталогов и прайсов на сезон **2026 (Год Лошади)**.")

# --- ВВОД ДАННЫХ ---
query = st.text_input("Введите название фабрики или бренда:", placeholder="Например: Лаконд, Баян Сулу, Акконд...")

if query:
    q = query.strip()
    target_year = 2026
    st.markdown("---")
    st.subheader(f"🎯 Сформированы снайперские ссылки для: {q}")

    # ЖЕСТКИЙ ФИЛЬТР МУСОРА (Хоккей, Акции, Медицина)
    trash_filter = "-hockey -хоккей -nhl -scores -stock -finance -инвестиции -медицина -вакансии"
    
    # 1. PDF Каталоги (Google лучше ищет PDF)
    pdf_query = urllib.parse.quote(f'"{q}" кондитерская фабрика новогодние подарки каталог {target_year} filetype:pdf {trash_filter}')
    
    # 2. Excel Прайсы (Яндекс лучше находит прайсы в СНГ)
    xls_query = urllib.parse.quote(f'"{q}" новогодние подарки прайс-лист {target_year} (xls OR xlsx) {trash_filter}')
    
    # 3. Соцсети (VK часто единственный источник для ДНР и мелких ИП)
    vk_query = urllib.parse.quote(f'"{q}" новогодние подарки {target_year}')
    
    # 4. Официальный сайт (поиск через Яндекс)
    site_query = urllib.parse.quote(f'"{q}" кондитерская фабрика официальный сайт подарки {target_year}')

    # ОТОБРАЖЕНИЕ КАРТОЧЕК
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        <div class="search-card" style="border-color: #dc3545;">
            <h2 style="margin:0; color:#dc3545;">📕 PDF КАТАЛОГ</h2>
            <p style="font-size:14px; color:#666;">Прямые ссылки на PDF презентации <b>2026 (Год Лошади)</b></p>
            <a href="https://www.google.com/search?q={pdf_query}" target="_blank" class="btn-link" style="background-color: #dc3545;">📥 ОТКРЫТЬ КАТАЛОГ</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #007bff;">
            <h2 style="margin:0; color:#007bff;">🔵 ПРАЙСЫ В VK</h2>
            <p style="font-size:14px; color:#666;">Поиск выложенных прайсов в группах ВКонтакте</p>
            <a href="https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_query}" target="_blank" class="btn-link" style="background-color: #007bff;">📱 ИСКАТЬ В ВК</a>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="search-card" style="border-color: #28a745;">
            <h2 style="margin:0; color:#28a745;">📊 EXCEL ПРАЙС</h2>
            <p style="font-size:14px; color:#666;">Поиск таблиц с ценами и составами подарков <b>2026</b></p>
            <a href="https://yandex.ru/search/?text={xls_query}" target="_blank" class="btn-link" style="background-color: #28a745;">📥 ОТКРЫТЬ ПРАЙСЫ</a>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="search-card" style="border-color: #ffc107;">
            <h2 style="margin:0; color:#856404;">🌐 САЙТ ФАБРИКИ</h2>
            <p style="font-size:14px; color:#666;">Переход в раздел продукции на официальном сайте</p>
            <a href="https://yandex.ru/search/?text={site_query}" target="_blank" class="btn-link" style="background-color: #ffc107; color: black !important;">🔗 ПЕРЕЙТИ НА САЙТ</a>
        </div>
        """, unsafe_allow_html=True)

else:
    st.info("Введите название фабрики (например, Лаконд или Баян Сулу), чтобы мгновенно получить снайперские ссылки на каталоги 2026 года.")
