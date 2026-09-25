import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Навигатор Подарков 2026",
    page_icon="🎁",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8f9fa; }
    .snapshot-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .product-title {
        font-size: 13px;
        font-weight: bold;
        color: #333;
        margin-top: 8px;
        min-height: 40px;
        line-height: 1.2;
    }
    .btn-download {
        background-color: #ff4b4b;
        color: white !important;
        font-weight: bold;
        padding: 12px 20px;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        margin-top: 10px;
    }
    .doc-box {
        background-color: #ffffff;
        border-left: 6px solid #28a745;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title(f"🎁 Универсальный Навигатор Подарков {TARGET_YEAR}")
st.caption(
    "Приоритет: Поиск официальных PDF/Excel. Если их нет — автоматический сбор визуальных карточек товаров."
)

# Ключевые слова для глубокого поиска
NAV_WORDS = ["каталог", "подарки", "produk", "catalog", "нг", "новогод", "price", "прайс", "лошад"]
JUNK_WORDS = ["политика", "согласие", "вакансии", "инвесторам", "stock", "finance"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.url, res.text
    except: pass
    return None, None

def find_domain_dynamic(company_name):
    """Находит сайт любой компании через прямой поисковый запрос"""
    query = f"{company_name} кондитерская фабрика официальный сайт подарки"
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    
    # Пытаемся найти домен (простой вариант, если Google не блокирует)
    try:
        res = requests.get(search_url, headers=HEADERS, timeout=7)
        if res.status_code == 200:
            # Ищем ссылки в результатах выдачи
            domains = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', res.text)
            for d in domains:
                netloc = urllib.parse.urlparse(d).netloc.lower().replace("www.", "")
                if netloc and not any(bad in netloc for bad in ["google", "yandex", "wikipedia", "youtube", "vk.com"]):
                    return netloc
    except: pass
    return None

def extract_assets(domain):
    """Глубокий сбор: ищет PDF и Карточки товаров по всем разделам"""
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)
    
    if not html: return [], []

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. СТРАТЕГИЯ "СЛЕДОПЫТ": Ищем все ссылки на разделы каталогов
    nav_pages = {final_url}
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        if any(kw in href or kw in text for kw in NAV_WORDS):
            full = urllib.parse.urljoin(final_url, a['href'])
            if domain in full: nav_pages.add(full)
    
    docs, products = [], []
    seen_links = set()

    # 2. СКАНИРУЕМ ВСЕ НАЙДЕННЫЕ РАЗДЕЛЫ
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        pages_data = list(executor.map(get_html, list(nav_pages)[:10]))
        
        for p_url, p_html in pages_data:
            if not p_html: continue
            p_soup = BeautifulSoup(p_html, "html.parser")
            
            # Ищем PDF / XLSX / XLS / DOC
            for a in p_soup.find_all("a", href=True):
                href = a['href'].lower()
                text = a.get_text().strip()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        full_link = urllib.parse.urljoin(p_url, a['href'])
                        if full_link not in seen_links:
                            seen_links.add(full_link)
                            docs.append({"title": text or "Официальный каталог/прайс", "url": full_link})
            
            # Если PDF еще не найдены, собираем карточки товаров
            if not docs:
                items = p_soup.find_all(["div", "li", "article", "section"], class_=re.compile(r"product|item|card|catalog|goods", re.I))
                for item in items:
                    img = item.find("img")
                    if img:
                        src = img.get("data-src") or img.get("data-original") or img.get("src")
                        if src:
                            img_url = urllib.parse.urljoin(p_url, src)
                            # Очистка Битрикс-ресайзов для высокого качества
                            img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
                            img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
                            
                            title = item.get_text(" ", strip=True)[:150]
                            if img_url not in seen_links and len(title) > 10:
                                if not any(bad in title.lower() for bad in JUNK_WORDS):
                                    seen_links.add(img_url)
                                    products.append({"title": title, "img": img_url})

    return docs, products

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании или адрес сайта:", placeholder="Например: Академия шоколада, Баян Сулу, lakond.ru...")

if st.button("🚀 ПОЛУЧИТЬ ДАННЫЕ 2026", type="primary", use_container_width=True):
    if company_query:
        # Резолвим домен
        input_str = company_query.strip()
        if "." in input_str and " " not in input_str:
            domain = input_str.lower().replace("https://", "").replace("http://", "").split("/")[0]
        else:
            with st.spinner(f"Ищу официальный сайт для '{input_str}'..."):
                domain = find_domain_dynamic(input_str)
                # Поправки для Академии Шоколада (Google иногда прячет домены)
                if "академия шоколада" in input_str.lower(): domain = "chocolate-academy.ru"

        if domain:
            st.info(f"🌐 Подключено к источнику: `{domain}`")
            with st.spinner("Глубокое сканирование каталога..."):
                docs, products = extract_assets(domain)

            # ВЫВОД РЕЗУЛЬТАТОВ
            if docs:
                st.success(f"✅ НАЙДЕНЫ ОФИЦИАЛЬНЫЕ ФАЙЛЫ ({len(docs)} шт.)")
                st.info("💡 Найдены прямые документы, визуальный парсинг сайта пропущен.")
                for d in docs:
                    icon = "📕 PDF" if ".pdf" in d['url'].lower() else "📊 EXCEL"
                    st.markdown(f"""
                        <div class="doc-box">
                            <b>{icon} | {d['title']}</b><br>
                            <a href="{d['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ ФАЙЛ</a>
                        </div>
                    """, unsafe_allow_html=True)
            
            elif products:
                st.warning("⚠️ Прямые файлы не найдены. Создаю визуальную выгрузку карточек...")
                
                # ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(products[:120]):
                        try:
                            img_res = requests.get(p['img'], timeout=5).content
                            zf.writestr(f"product_{i+1:03d}.jpg", img_res)
                        except: continue
                st.download_button("📥 СКАЧАТЬ ВСЕ КАРТОЧКИ В ZIP", zip_buffer.getvalue(), f"{domain}_catalog.zip", "application/zip")

                st.markdown("---")
                cols = st.columns(4)
                for i, p in enumerate(products):
                    with cols[i % 4]:
                        st.markdown('<div class="snapshot-card">', unsafe_allow_html=True)
                        st.image(p['img'], use_container_width=True)
                        st.markdown(f'<div class="product-title">{p["title"]}</div>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
            
            else:
                st.error("На сайте не удалось найти ни файлов, ни карточек товаров. Попробуйте ввести адрес сайта напрямую (например, chocolate-academy.ru)")
        else:
            st.error("Не удалось определить сайт компании. Пожалуйста, введите адрес сайта (домен).")

st.divider()
st.caption(f"Программа автоматически сканирует все вложенные разделы сайта на предмет каталогов {TARGET_YEAR} года.")
