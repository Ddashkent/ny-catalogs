import datetime
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import urllib.parse
import streamlit as st

# 1. Настройка страницы
st.set_page_config(page_title="Универсальный Поисковик Каталогов 2025/2026", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .card-success {
        background-color: #ffffff; border-left: 6px solid #28a745;
        padding: 18px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .btn-download {
        background-color: #28a745; color: white !important;
        padding: 9px 18px; border-radius: 6px; text-decoration: none;
        font-weight: bold; display: inline-block; margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Универсальный Экстрактор Каталогов")
st.write("Автоматический поиск официальных сайтов и скачивание новогодних каталогов **любых** фабрик.")

# Выбор сезона
target_year = st.selectbox("Сезон поиска:", [2025, 2026], index=0)

# --- СПИСКИ БЛОКИРОВКИ МУСОРА ---
BLACK_DOMAINS = [
    "wikipedia.org", "otzovik", "avito", "krasotaimedicina", "pravo", "consultant", 
    "garant", "list-org", "checko", "synapse", "hh.ru", "rabota", "youtube", 
    "instagram", "facebook", "vk.com", "espn", "365scores", "rg.ru", "audit-it"
]

BLACK_WORDS = [
    "политика", "конфиденциальность", "персональные", "согласие", "соглашение", 
    "вакцинация", "хоккей", "медицина", "отзывы", "вакансии", "инвесторам", "акции"
]

GOOD_WORDS = ["каталог", "прайс", "подарки", "новогод", "нг", "продукция", "catalog", "price", "pdf", "xls"]

# --- ДИНАМИЧЕСКИЙ ДВИЖОК ---

def resolve_official_domain(company_query):
    """Динамически находит официальный сайт ЛЮБОЙ компании"""
    try:
        with DDGS() as ddgs:
            # Жестко формулируем запрос для отсечения нерелевантного мусора
            search_text = f'"{company_query}" кондитерская фабрика официальный сайт'
            results = list(ddgs.text(search_text, region='ru-ru', max_results=6))
            
            for item in results:
                url = item['href']
                # Проверяем, что сайт не входит в черный список справочников
                if not any(bad in url.lower() for bad in BLACK_DOMAINS):
                    # Извлекаем чистое имя домена
                    parsed = urllib.parse.urlparse(url)
                    domain = f"{parsed.scheme}://{parsed.netloc}"
                    return domain, url
    except Exception as e:
        pass
    return None, None

def extract_catalogs_from_url(base_url):
    """Сканирует найденный сайт на файлы и страницы каталогов"""
    found_links = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(base_url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            for a in soup.find_all("a", href=True):
                href = a['href'].lower()
                text = a.get_text().lower().strip()
                
                # Проверка: полезная ли ссылка?
                is_doc = any(ext in href for ext in [".pdf", ".xlsx", ".xls"])
                is_catalog_page = any(word in text or word in href for word in GOOD_WORDS)
                
                if (is_doc or is_catalog_page):
                    if not any(bad in text or bad in href for bad in BLACK_WORDS):
                        full_url = urllib.parse.urljoin(base_url, a['href'])
                        title = a.get_text().strip() or "Каталог продукции / Прайс"
                        
                        if full_url not in [item['link'] for item in found_links]:
                            found_links.append({"title": title, "link": full_url})
    except:
        pass
    return found_links

def search_network_files(company_query):
    """Запасной метод: поиск прямых PDF файлов этой компании в сети"""
    pdf_links = []
    try:
        with DDGS() as ddgs:
            q = f'"{company_query}" новогодние подарки каталог {target_year} filetype:pdf'
            results = list(ddgs.text(q, region='ru-ru', max_results=5))
            for item in results:
                url = item['href']
                title = item['title']
                if not any(bad in url.lower() for bad in BLACK_DOMAINS):
                    if not any(bad in title.lower() for bad in BLACK_WORDS):
                        pdf_links.append({"title": title, "link": url})
    except:
        pass
    return pdf_links

# --- ИНТЕРФЕЙС ---

company_input = st.text_input("Введите название ЛЮБОЙ фабрики или бренда:", placeholder="Например: Баян Сулу, Красный Мозырянин, Победа, Лаконд...")

if st.button("🚀 НАЙТИ КАТАЛОГ 2025/2026", type="primary"):
    if not company_input.strip():
        st.error("Пожалуйста, введите название компании.")
    else:
        query = company_input.strip()
        st.write(f"🔍 Ищем информацию для: **{query}**...")
        
        with st.spinner("1. Динамически определяем официальный сайт..."):
            domain, direct_page = resolve_official_domain(query)
            
        found_catalogs = []
        
        if domain:
            st.info(f"🌐 Найден официальный сайт: `{domain}`")
            with st.spinner("2. Сканируем сайт на наличие файлов и каталогов..."):
                found_catalogs = extract_catalogs_from_url(domain)
        else:
            st.warning("Не удалось автоматически определить домен. Выполняю прямой поиск файлов в сети...")

        # Если на самом сайте прямых ссылок не нашлось, ищем PDF в сети
        if not found_catalogs:
            with st.spinner("3. Ищем выложенные PDF-каталоги фабрики в сети..."):
                found_catalogs = search_network_files(query)

        st.markdown("---")
        
        # Вывод результатов
        if found_catalogs:
            st.success(f"Найдено ресурсов: {len(found_catalogs)}")
            unique_results = {item['link']: item for item in found_catalogs}.values()
            
            for item in unique_results:
                icon = "📕 PDF" if ".pdf" in item['link'].lower() else ("📊 EXCEL" if ".xls" in item['link'].lower() else "🌐 СТРАНИЦА")
                st.markdown(f"""
                <div class="card-success">
                    <h4 style="margin:0; font-size:16px;">{icon} | {item['title']}</h4>
                    <p style="font-size:12px; color:gray; margin: 4px 0;">Ссылка: {item['link'][:80]}...</p>
                    <a href="{item['link']}" target="_blank" class="btn-download">📥 СКАЧАТЬ / ОТКРЫТЬ</a>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.error(f"Прямых файлов не найдено. Нажмите кнопку ниже, чтобы открыть официальный раздел фабрики.")
            if domain:
                st.link_button(f"🔗 Перейти на сайт {domain}", domain)

        # Резервный блок поиска для сложных случаев
        st.markdown("---")
        st.caption("Быстрые резервные ссылки для поиска прайсов:")
        c1, c2 = st.columns(2)
        with c1:
            g_q = urllib.parse.quote(f'"{query}" новогодние подарки каталог {target_year} filetype:pdf')
            st.link_button("📂 Гугл поиск (Только PDF)", f"https://www.google.com/search?q={g_q}")
        with c2:
            vk_q = urllib.parse.quote(f'"{query}" новогодние подарки прайс {target_year}')
            st.link_button("📱 Поиск прайсов ВКонтакте", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}")
