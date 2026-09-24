import streamlit as st
import urllib.parse
import datetime
from duckduckgo_search import DDGS

# 1. Настройка страницы
st.set_page_config(page_title="Навигатор Подарков 2026", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .catalog-card { 
        background-color: #ffffff; border-left: 6px solid #ff4b4b; 
        padding: 20px; border-radius: 12px; margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    .download-btn {
        background-color: #ff4b4b; color: white !important;
        padding: 12px 24px; border-radius: 8px; text-decoration: none;
        font-weight: bold; display: inline-block; margin-top: 10px; text-align: center;
    }
    .download-btn:hover { background-color: #d43f3f; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Навигатор Подарков 2026")
st.write("Введите название ЛЮБОЙ фабрики. Программа вытянет прямые ссылки на каталоги и прайсы.")

# Выбор года
target_year = 2026

# --- ЛОГИКА ПОИСКА ---

def get_clean_catalogs(query):
    found = []
    # Формируем запрос, который отсекает акции, спорт и медицину
    # Ищем: "Название" новогодние подарки каталог 2026
    search_query = f'"{query}" (кондитерская фабрика OR подарки) (каталог OR прайс) {target_year} filetype:pdf OR filetype:xlsx'
    
    try:
        with DDGS() as ddgs:
            # Ищем на русском языке
            results = list(ddgs.text(search_query, region='ru-ru', max_results=10))
            for res in results:
                link = res['href'].lower()
                title = res['title'].lower()
                
                # ЖЕСТКИЙ ФИЛЬТР МУСОРА
                bad_stuff = ["stock", "finance", "хоккей", "hockey", "медицина", "право", "политика", "данных", "согласие"]
                if any(bad in link or bad in title for bad in bad_stuff):
                    continue
                
                # ПРОВЕРКА НА ПОЛЕЗНОСТЬ
                good_stuff = ["каталог", "прайс", "подарки", "pdf", "xls", "2026", "catalog", "price"]
                if any(good in link or good in title for good in good_stuff):
                    found.append({
                        "title": res['title'],
                        "link": res['href'],
                        "snippet": res['body']
                    })
    except:
        pass
    return found

# --- ИНТЕРФЕЙС ---

company_name = st.text_input("Введите название компании (например: Баян Сулу, Лаконд, Акконд):", placeholder="Название или бренд...")

if st.button("🚀 НАЙТИ КАТАЛОГ / ПРАЙС 2026", type="primary"):
    if not company_name.strip():
        st.warning("Пожалуйста, введите название.")
    else:
        q = company_name.strip()
        st.write(f"### 🎯 Результаты для: {q}")
        
        with st.spinner(f"Ищу прямые ссылки на файлы {target_year} года..."):
            items = get_clean_catalogs(q)
            
            if items:
                st.success(f"Найдено полезных ресурсов: {len(items)}")
                for item in items:
                    # Определяем тип файла для иконки
                    icon = "📕 PDF" if ".pdf" in item['link'].lower() else "📊 EXCEL / ПРАЙС"
                    
                    st.markdown(f"""
                    <div class="catalog-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {item['title']}</h4>
                        <p style="font-size:13px; color:#64748b; margin:10px 0;">{item['snippet'][:200]}...</p>
                        <a href="{item['link']}" target="_blank" class="download-btn">📥 СКАЧАТЬ ФАЙЛ</a>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error("Прямых ссылок на файлы не найдено. Попробуйте уточнить название.")
                
        # Резервные кнопки (всегда выручают менеджера)
        st.markdown("---")
        st.write("### 🔍 Если файл не найден автоматически:")
        col1, col2 = st.columns(2)
        
        # Ссылки для ручного перехода
        g_q = urllib.parse.quote(f'"{q}" новогодние подарки каталог {target_year} filetype:pdf')
        vk_q = urllib.parse.quote(f'"{q}" подарки прайс 2026')
        
        with col1:
            st.link_button("📂 Искать PDF в Google", f"https://www.google.com/search?q={g_q}")
        with col2:
            st.link_button("📱 Искать прайсы в VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}")

st.divider()
st.caption(f"Поиск настроен на сезон {target_year}. Мусор (хоккей, акции, юристы) отсекается автоматически.")
