import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import pandas as pd
import streamlit as st

# 1. Настройка страницы
st.set_page_config(page_title="Интеллектуальный Навигатор Подарков", page_icon="🍬", layout="wide")

# АВТО-ОПРЕДЕЛЕНИЕ ГОДА СЕЗОНА
now = datetime.datetime.now()
# Если сейчас август и позже, ищем подарки на СЛЕДУЮЩИЙ год
target_year = now.year + 1 if now.month >= 8 else now.year

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .catalog-card { background-color: #ffffff; border-left: 6px solid #28a745; padding: 15px; border-radius: 10px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .web-card { background-color: #ffffff; border-left: 6px solid #007bff; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title(f"🎄 Навигатор Подарков: Сезон {target_year}")
st.caption(f"Автоматизированный поиск каталогов, прайсов и выгрузка товаров. Текущий поиск настроен на {target_year} год.")

# --- БАЗА И ФИЛЬТРЫ ---
KNOWLEDGE_BASE = {
    "лаконд": "lakond.ru", "акконд": "akkond.ru", "донко": "donko.su", "тор": "donko.su",
    "рубин": "rubin-2000.ru", "дилявер": "dilaver.ru", "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru", "коммунарка": "kommunarka.by", "спартак": "spartak.by",
    "рахат": "rakhat.kz", "лоте рахат": "rakhat.kz", "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru", "тореро": "torero.ru", "победа": "pobeda.market", "славянка": "slavyanka.ru"
}

BAD_WORDS = ["медицина", "врач", "хоккей", "stock", "finance", "согласие", "политика"]

# --- УМНЫЕ ФУНКЦИИ ---

def find_site(query):
    if query in KNOWLEDGE_BASE: return KNOWLEDGE_BASE[query]
    try:
        with DDGS() as ddgs:
            q = f'"{query}" кондитерская фабрика официальный сайт -wiki'
            res = list(ddgs.text(q, region='ru-ru', max_results=3))
            for r in res:
                if not any(bad in r['href'] for bad in ["wikipedia", "checko", "list-org"]):
                    return urllib.parse.urlparse(r['href']).netloc
    except: return None

def scan_for_files(url):
    files = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"http://{url}", headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        for a in soup.find_all("a", href=True):
            h, t = a['href'].lower(), a.get_text().lower()
            if any(ext in h for ext in [".pdf", ".xlsx", ".xls"]) or "каталог" in t or "прайс" in t:
                if not any(bad in t for bad in BAD_WORDS):
                    files.append({"title": a.get_text().strip() or "Файл", "link": urllib.parse.urljoin(f"http://{url}", a['href'])})
    except: pass
    return files

def scrape_products(url):
    """Пытается собрать список товаров, если нет PDF"""
    products = []
    try:
        res = requests.get(f"http://{url}", headers={"User-Agent": "Mozilla/5.0"}, timeout=7)
        soup = BeautifulSoup(res.text, "html.parser")
        # Ищем типичные блоки товаров (h2, h3, h4 или блоки с классом product/item)
        tags = soup.find_all(['h2', 'h3', 'h4', 'p', 'div'], string=True)
        for tag in tags:
            txt = tag.get_text().strip()
            if 5 < len(txt) < 60 and any(keyword in txt.lower() for keyword in ["подарок", "набор", "конфет", "грамм", "г."]):
                products.append({"Наименование": txt})
    except: pass
    return pd.DataFrame(products).drop_duplicates() if products else None

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании:", placeholder="Например: Баян Сулу")

if st.button("🚀 НАЙТИ И ВЫГРУЗИТЬ ДАННЫЕ", type="primary"):
    if company_query:
        q = company_query.lower().strip()
        site = find_site(q)
        
        if site:
            st.info(f"🌐 Работаем с сайтом: `{site}`")
            
            # Разделяем экран на две части
            col_files, col_web = st.columns(2)
            
            with col_files:
                st.subheader("📥 Готовые файлы (PDF/XLS)")
                links = scan_for_files(site)
                if links:
                    for l in links:
                        st.markdown(f"<div class='catalog-card'><b>{l['title']}</b><br><a href='{l['link']}' target='_blank'>📥 Скачать файл</a></div>", unsafe_allow_html=True)
                else: st.warning("Прямых файлов не найдено.")
            
            with col_web:
                st.subheader("📑 Состав каталога с сайта")
                prod_df = scrape_products(site)
                if prod_df is not None:
                    st.write(f"Найдено позиций: {len(prod_df)}")
                    st.dataframe(prod_df, use_container_width=True)
                    csv = prod_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("💾 Скачать этот перечень в Excel (CSV)", csv, f"{q}_products.csv", "text/csv")
                else: st.info("Не удалось автоматически выделить список товаров со страницы.")
            
        else: st.error("Не удалось найти официальный сайт. Уточните название.")

st.divider()
st.write("### 🔍 Резервный поиск")
c1, c2, c3 = st.columns(3)
with c1: st.link_button("Google PDF", f"https://www.google.com/search?q={company_query}+каталог+{target_year}+filetype:pdf")
with c2: st.link_button("Яндекс Прайсы", f"https://yandex.ru/search/?text={company_query}+прайс+новогодний+{target_year}+xls")
with c3: st.link_button("Поиск в VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={company_query}+подарки+{target_year}")
