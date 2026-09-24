import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import streamlit as st

# 1. Настройка интерфейса (Минимализм)
st.set_page_config(page_title="Поиск новогодних каталогов", page_icon="🍬")

st.markdown("""
    <style>
    .catalog-card { background-color: #f8f9fa; border: 2px solid #28a745; padding: 20px; border-radius: 12px; margin-bottom: 15px; }
    .btn-main { background-color: #28a745; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block; }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Экспресс-поиск каталогов")
st.write("Введите название фабрики. Программа сама найдет сайт и вытянет прямую ссылку на каталог.")

# Текущий год
year = 2025

# Ключевые слова для "вкусного" поиска
GOOD_WORDS = ["каталог", "прайс", "подарки", "новогод", "нг", "из конфет", "catalog", "price", "pdf", "xls"]
# Мусор, который мы удаляем
BAD_WORDS = ["политика", "конфиденциальность", "персональные", "данные", "согласие", "акции", "инвесторам", "stock", "finance"]

# --- МОЗГ ПРИЛОЖЕНИЯ ---

def find_official_site(name):
    """Находит официальный сайт компании по названию"""
    try:
        with DDGS() as ddgs:
            # Ищем официальный сайт
            res = list(ddgs.text(f"{name} официальный сайт кондитерская фабрика", max_results=3))
            if res:
                return res[0]['href']
    except:
        return None
    return None

def scan_site_for_catalogs(url):
    """Заходит на сайт и ищет ссылки на документы"""
    catalogs = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                text = a.get_text().lower().strip()
                link = a['href'].lower()
                
                # Фильтр: это должна быть ссылка на документ или раздел подарков
                if any(good in text or good in link for good in GOOD_WORDS):
                    # Проверка на мусор
                    if not any(bad in text or bad in link for bad in BAD_WORDS):
                        full_url = urllib.parse.urljoin(url, a['href'])
                        title = a.get_text().strip() or "Открыть каталог / раздел"
                        if full_url not in [c['link'] for c in catalogs]:
                            catalogs.append({"title": title, "link": full_url})
    except:
        pass
    return catalogs

# --- ИНТЕРФЕЙС ---

company_name = st.text_input("Введите название компании (например: Лаконд или lakond.ru):", placeholder="Название или сайт...")

if st.button("🚀 НАЙТИ КАТАЛОГ", type="primary"):
    if not company_name:
        st.warning("Введите название компании")
    else:
        with st.spinner(f"Захожу на сайт {company_name} и ищу каталоги..."):
            
            # Определяем, ввели домен или название
            if "." in company_name and " " not in company_name:
                base_url = company_name if company_name.startswith("http") else f"https://{company_name}"
            else:
                base_url = find_official_site(company_name)
            
            if base_url:
                st.info(f"📍 Работаю с сайтом: {base_url}")
                
                # Сканируем сайт напрямую
                found_links = scan_site_for_catalogs(base_url)
                
                if found_links:
                    st.success(f"Найдено прямых ссылок: {len(found_links)}")
                    for item in found_links:
                        st.markdown(f"""
                        <div class="catalog-card">
                            <h4 style="margin-top:0;">📦 {item['title']}</h4>
                            <a href="{item['link']}" target="_blank" class="btn-main">📥 ОТКРЫТЬ ФАЙЛ / РАЗДЕЛ</a>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("На главной странице сайта прямых ссылок на файлы не найдено. Попробуйте поиск ниже.")
            else:
                st.error("Не удалось автоматически найти официальный сайт. Попробуйте ввести домен (например, lakond.ru)")

        # Резервные кнопки (всегда работают)
        st.markdown("---")
        st.write("### 🔍 Если не нашли на сайте, ищем в сети:")
        c1, c2 = st.columns(2)
        with c1:
            g_q = urllib.parse.quote(f'"{company_name}" новогодний каталог {year} filetype:pdf')
            st.link_button("📂 Искать PDF в Google", f"https://www.google.com/search?q={g_q}")
        with c2:
            vk_q = urllib.parse.quote(f'"{company_name}" подарки прайс 2025')
            st.link_button("📱 Искать прайс в VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}")
