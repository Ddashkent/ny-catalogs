import streamlit as st
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import urllib.parse
import datetime

# 1. Настройка страницы
st.set_page_config(page_title="Каталоги Подарков 2026", page_icon="🍬", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .catalog-card { 
        background-color: #ffffff; border-left: 6px solid #e91e63; 
        padding: 20px; border-radius: 10px; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .download-btn {
        background-color: #e91e63; color: white !important;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        font-weight: bold; display: inline-block; margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Навигатор Подарков 2026")
st.write("Введите название фабрики. Система найдет официальный сайт и вытянет каталог.")

# --- БАЗА ЗНАНИЙ (Для 100% точности по вашему списку) ---
KNOWLEDGE_BASE = {
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "рубин": "rubin-2000.ru",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "лоте рахат": "rakhat.kz",
    "конфешн": "confashion.ru",
    "саратовская кф": "confashion.ru",
    "тореро": "torero.ru",
    "абинекс": "abineks.ru",
    "рэйд-21": "raid21.ru",
    "сибпродторг": "sibprodtorg.ru",
    "столичные поставки": "stolichnye.ru",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "рот фронт": "uniconf.ru",
    "бабаевский": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "фортуна": "fortuna-podarki.ru"
}

# Списки фильтрации
GOOD_EXT = [".pdf", ".xls", ".xlsx", ".doc", "/catalog/", "/podarki/", "/products/"]
BAD_WORDS = ["медицина", "врач", "рейтинг", "отзывы", "статья", "wiki", "hockey", "хоккей", "политика", "данных", "согласие"]

# --- ФУНКЦИИ ---

def scan_website(url):
    """Заходит на сайт и вытаскивает все ссылки на каталоги/подарки"""
    files = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        base_url = url if url.startswith("http") else f"http://{url}"
        res = requests.get(base_url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a['href'].lower()
                text = a.get_text().lower()
                
                # Ищем признаки каталога
                if any(ext in href for ext in GOOD_EXT) or any(kw in text for kw in ["каталог", "прайс", "подарки", "2026"]):
                    if not any(bad in text or bad in href for bad in BAD_WORDS):
                        full_link = urllib.parse.urljoin(base_url, a['href'])
                        files.append({"title": a.get_text().strip() or "Каталог/Прайс", "link": full_link})
    except:
        pass
    return files

def find_site_via_search(query):
    """Поиск сайта, если его нет в базе знаний"""
    try:
        with DDGS() as ddgs:
            # Жесткий запрос: название + отрасль
            q = f'"{query}" кондитерская фабрика подарки официальный сайт'
            res = list(ddgs.text(q, region='ru-ru', max_results=3))
            for r in res:
                link = r['href']
                if not any(bad in link for bad in ["medicina", "pravo", "wiki", "otzovik"]):
                    return link
    except:
        return None

# --- ИНТЕРФЕЙС ---

company_input = st.text_input("Название компании:", placeholder="Например: Лаконд или Акконд")

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ 2026", type="primary"):
    if not company_input:
        st.error("Введите название!")
    else:
        query = company_input.lower().strip()
        st.write(f"🔍 Анализирую: **{query}**")
        
        # 1. Проверяем Базу Знаний
        target_site = KNOWLEDGE_BASE.get(query)
        
        # 2. Если в базе нет, ищем сайт через поиск
        if not target_site:
            with st.spinner("Ищу официальный сайт фабрики..."):
                target_site = find_site_via_search(query)
        
        if target_site:
            st.info(f"🌐 Найден сайт: `{target_site}`. Извлекаю файлы каталогов...")
            
            # 3. Сканируем сайт на наличие PDF/XLS
            with st.spinner("Сканирую разделы подарков..."):
                links = scan_website(target_site)
                
                # Если на самом сайте пусто, пробуем найти прямые PDF в сети для этой фабрики
                if not links:
                    with DDGS() as ddgs:
                        pdf_q = f'site:{target_site} каталог новогодние подарки 2026 filetype:pdf'
                        extra = list(ddgs.text(pdf_q, max_results=5))
                        for e in extra:
                            links.append({"title": e['title'], "link": e['href']})

            # Вывод результатов
            if links:
                st.success(f"Найдено ресурсов: {len(links)}")
                unique_links = {l['link']: l for l in links}.values()
                for l in unique_links:
                    st.markdown(f"""
                    <div class="catalog-card">
                        <h4 style="margin:0;">📦 {l['title']}</h4>
                        <a href="{l['link']}" target="_blank" class="download-btn">📥 СКАЧАТЬ КАТАЛОГ / ПРАЙС 2026</a>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Прямых ссылок на файлы не найдено. Попробуйте зайти на сайт вручную.")
                st.link_button("🔗 Перейти на сайт", f"http://{target_site}")
        else:
            st.error("Не удалось найти сайт компании. Уточните название.")

st.divider()
st.caption("База знаний обновлена: Лаконд, Акконд и др. теперь находятся мгновенно.")
