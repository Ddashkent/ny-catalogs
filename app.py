import concurrent.futures
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

st.set_page_config(page_title="Навигатор Подарков 2026", page_icon="🎁", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .snapshot-card {
        background-color: #ffffff; border: 1px solid #e0e0e0;
        border-radius: 12px; padding: 10px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .product-title { font-size: 13px; font-weight: bold; color: #333; margin-top: 8px; min-height: 38px; }
    .btn-download {
        background-color: #28a745; color: white !important;
        font-weight: bold; padding: 10px 20px; border-radius: 8px;
        text-decoration: none; display: inline-block; margin-top: 10px;
    }
    .doc-box {
        background-color: #fff1f1; border-left: 6px solid #dc3545;
        padding: 15px; border-radius: 10px; margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

st.title(f"🎁 Универсальный Навигатор Подарков {TARGET_YEAR}")

# --- СПИСКИ ФИЛЬТРАЦИИ ---

# Обязательные слова для КАТАЛОГА
MUST_HAVE_CATALOG = ["каталог", "прайс", "подарки", "новогод", "2026", "price", "catalog", "нг", "лошад"]

# Черный список (полная блокировка)
JUNK_WORDS = [
    "политика", "согласие", "соглашение", "вакансии", "инвесторам", "презентация компании", 
    "реквизиты", "персональных", "данных", "cookies", "устав", "огрн", "инн"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ФУНКЦИИ ПРОВЕРКИ И ПОИСКА
# -----------------------------

def is_actual_catalog(text, link):
    """Проверяет, является ли файл реально КАТАЛОГОМ ПОДАРКОВ"""
    combined = (text + " " + link).lower()
    # 1. Проверяем на мусор (если есть мусор - сразу False)
    if any(junk in combined for junk in JUNK_WORDS):
        return False
    # 2. Проверяем на обязательные слова
    if any(good in combined for good in MUST_HAVE_CATALOG):
        return True
    return False

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_domain_dynamic(company_name):
    try:
        query = f'"{company_name}" кондитерская фабрика подарки официальный сайт'
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(search_url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a['href']).query).get("uddg", [a['href']])[0]
                netloc = urllib.parse.urlparse(target).netloc.lower().replace("www.", "")
                if netloc and not any(bad in netloc for bad in ["google", "yandex", "wiki", "otzovik", "avito"]):
                    return netloc
    except: pass
    return None

def extract_assets(domain):
    base_protocol = f"https://{domain}"
    paths = ["", "/catalog/", "/podarki/", "/novogodnie-podarki/", "/katalog/"]
    urls_to_check = [base_protocol + p for p in paths]

    docs, products = [], []
    seen_links = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        pages_data = list(executor.map(get_html, urls_to_check))

        for p_url, p_html in pages_data:
            if not p_html: continue
            p_soup = BeautifulSoup(p_html, "html.parser")

            # 1. Ищем PDF / Excel
            for a in p_soup.find_all("a", href=True):
                href = a['href'].lower()
                text = a.get_text().strip()
                full_link = urllib.parse.urljoin(p_url, a['href'])
                
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                    # ПРИМЕНЯЕМ СТРОГИЙ ФИЛЬТР
                    if is_actual_catalog(text, href):
                        if full_link not in seen_links:
                            seen_links.add(full_link)
                            docs.append({"title": text or "Каталог подарков 2026", "url": full_link})

            # 2. Ищем карточки товаров
            # (Выполняем всегда, если документов мало)
            if len(docs) < 1:
                for img in p_soup.find_all("img"):
                    src = img.get("data-src") or img.get("src")
                    if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "vk", "social"]): continue
                    
                    img_url = urllib.parse.urljoin(p_url, src)
                    img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
                    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

                    title = img.get("alt") or img.get("title") or (img.parent.get_text(" ", strip=True) if img.parent else "")
                    title = title.strip()[:80]

                    if img_url not in seen_links and len(title) > 5:
                        if not any(junk in title.lower() for junk in JUNK_WORDS):
                            seen_links.add(img_url)
                            products.append({"title": title, "img": img_url})

    return docs, products

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании (например: Рубин или Академия шоколада):")

if st.button("🚀 ПОЛУЧИТЬ ДАННЫЕ 2026", type="primary", use_container_width=True):
    if company_query:
        input_str = company_query.strip()
        with st.spinner(f"Ищу официальный сайт для '{input_str}'..."):
            domain = find_domain_dynamic(input_str)
            if "академия шоколада" in input_str.lower(): domain = "chocolate-academy.ru"
            if "рубин" in input_str.lower(): domain = "rubin-2000.ru"

        if domain:
            st.info(f"🌐 Подключено к источнику: `{domain}`")
            with st.spinner("Фильтруем мусор и сканируем каталоги..."):
                docs, products = extract_assets(domain)

            # ВЫВОД: ДОКУМЕНТЫ
            if docs:
                st.success(f"✅ НАЙДЕНЫ ОФИЦИАЛЬНЫЕ КАТАЛОГИ/ПРАЙСЫ ({len(docs)} шт.)")
                for d in docs:
                    st.markdown(f"""
                        <div class="doc-box">
                            <b>📄 {d['title']}</b><br>
                            <a href="{d['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ КАТАЛОГ</a>
                        </div>
                    """, unsafe_allow_html=True)
            
            # ВЫВОД: КАРТОЧКИ (показываем, если документов нет или их мало)
            if products:
                if docs: st.markdown("---")
                st.subheader(f"🖼️ Снимки карточек подарков с сайта ({len(products)} шт.)")
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(products[:100]):
                        try:
                            img_res = requests.get(p['img'], timeout=5).content
                            zf.writestr(f"gift_{i+1:03d}.jpg", img_res)
                        except: continue
                st.download_button("📥 СКАЧАТЬ ВСЕ СНИМКИ В ZIP", zip_buffer.getvalue(), f"{domain}_catalog.zip", "application/zip")

                cols = st.columns(4)
                for i, p in enumerate(products):
                    with cols[i % 4]:
                        st.markdown('<div class="snapshot-card">', unsafe_allow_html=True)
                        st.image(p['img'], use_container_width=True)
                        st.markdown(f'<div class="product-title">{p["title"]}</div>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
            
            if not docs and not products:
                st.error("На сайте не найдено ни одного каталога 2026 года. Попробуйте ввести адрес сайта напрямую.")
        else:
            st.error("Не удалось найти сайт. Введите адрес вручную (например, lakond.ru)")

st.divider()
st.caption("Система автоматически отфильтровала юридические документы и презентации компании.")
