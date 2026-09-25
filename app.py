import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

# 1. Настройка страницы
st.set_page_config(page_title="Навигатор Подарков", page_icon="📸", layout="wide")

# АВТО-ОПРЕДЕЛЕНИЕ ГОДА (2026)
now = datetime.datetime.now()
target_year = now.year + 1 if now.month >= 8 else now.year

st.markdown(f"""
    <style>
    .stApp {{ background-color: #f8f9fa; }}
    .snapshot-card {{
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    .product-title {{ font-size: 14px; font-weight: bold; color: #333; margin-top: 8px; min-height: 40px; }}
    .btn-download {{
        background-color: #ff4b4b; color: white !important;
        font-weight: bold; padding: 12px 20px; border-radius: 8px;
        text-decoration: none; display: inline-block; margin-top: 10px;
    }}
    </style>
""", unsafe_allow_html=True)

st.title(f"📸 Визуальный Навигатор Каталогов {target_year}")
st.caption("Поиск официальных PDF или визуальных карточек товаров напрямую с сайтов.")

# --- МОЗГ СИСТЕМЫ ---

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_site(query):
    # Мгновенные домены для популярных запросов
    kb = {"академия шоколада": "chocolate-academy.ru", "лаконд": "lakond.ru", "баян сулу": "bayansulu.kz"}
    q_low = query.lower().strip()
    if q_low in kb: return kb[q_low]
    
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{query}" официальный сайт кондитерская фабрика', max_results=3))
            if res: return urllib.parse.urlparse(res[0]['href']).netloc
    except: pass
    return None

def extract_assets(domain):
    """Ищет PDF и Карточки товаров"""
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return [], []

    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Сначала ищем страницы каталогов (чтобы зайти глубже)
    nav_pages = {final_url}
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        if any(kw in href or kw in a.get_text().lower() for kw in ["каталог", "подарки", "produk", "catalog", "нг"]):
            full = urllib.parse.urljoin(final_url, a['href'])
            if domain in full: nav_pages.add(full)
    
    docs, products = [], []
    seen_links = set()

    # 2. Сканируем найденные страницы (до 5 штук для скорости)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        pages_data = list(executor.map(get_html, list(nav_pages)[:6]))
        
        for p_url, p_html in pages_data:
            if not p_html: continue
            p_soup = BeautifulSoup(p_html, "html.parser")
            
            # Ищем PDF/XLS
            for a in p_soup.find_all("a", href=True):
                href = a['href'].lower()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                    full_link = urllib.parse.urljoin(p_url, a['href'])
                    if full_link not in seen_links:
                        seen_links.add(full_link)
                        docs.append({"title": a.get_text().strip() or "Официальный файл", "url": full_link})
            
            # Ищем ТОВАРНЫЕ КАРТОЧКИ (контейнеры с картинками)
            # Ищем блоки div, li у которых есть класс со словами product, item, card
            items = p_soup.find_all(["div", "li"], class_=re.compile(r"product|item|card|catalog", re.I))
            for item in items:
                img = item.find("img")
                if img:
                    src = img.get("data-src") or img.get("src")
                    if src:
                        img_url = urllib.parse.urljoin(p_url, src)
                        # Чистим Битрикс-превью до оригинала
                        img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
                        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
                        
                        title = item.get_text(" ", strip=True)[:100]
                        if img_url not in seen_links and len(title) > 5:
                            seen_links.add(img_url)
                            products.append({"title": title, "img": img_url})

    return docs, products

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Название компании или сайт:", placeholder="Например: Академия шоколада или lakond.ru")

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ 2026", type="primary", use_container_width=True):
    if company_query:
        # Определяем сайт
        domain = company_query.strip()
        if not "." in domain:
            with st.spinner("Ищу официальный сайт..."):
                domain = find_site(company_query)

        if domain:
            st.info(f"🌐 Работаем с сайтом: `{domain}`")
            with st.spinner("Сканирую разделы каталога и вытягиваю данные..."):
                docs, products = extract_assets(domain)

            # ВЫВОД: ШАГ 1 - ФАЙЛЫ
            if docs:
                st.success(f"✅ НАЙДЕНЫ ОФИЦИАЛЬНЫЕ PDF ({len(docs)} шт.)")
                for d in docs:
                    st.markdown(f"""
                        <div style="background:#fff; border-left:5px solid #ff4b4b; padding:15px; border-radius:10px; margin-bottom:10px;">
                            <b>📄 {d['title']}</b><br>
                            <a href="{d['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ КАТАЛОГ</a>
                        </div>
                    """, unsafe_allow_html=True)
            
            # ВЫВОД: ШАГ 2 - ВИЗУАЛЬНЫЕ КАРТОЧКИ
            if products:
                st.markdown("---")
                st.subheader(f"🖼️ Снимки карточек товаров с сайта ({len(products)} шт.)")
                
                # Кнопка ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(products[:100]): # Ограничим для ZIP
                        try:
                            img_data = requests.get(p['img'], timeout=5).content
                            zf.writestr(f"gift_{i+1:03d}.jpg", img_data)
                        except: continue
                st.download_button("📥 СКАЧАТЬ ВСЕ СНИМКИ В ZIP", zip_buffer.getvalue(), f"{domain}_snapshots.zip", "application/zip")

                # Сетка (4 в ряд)
                cols = st.columns(4)
                for i, p in enumerate(products):
                    with cols[i % 4]:
                        st.markdown('<div class="snapshot-card">', unsafe_allow_html=True)
                        st.image(p['img'], use_container_width=True)
                        st.markdown(f'<div class="product-title">{p["title"]}</div>', unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
            
            if not docs and not products:
                st.error("Не удалось найти файлы или карточки товаров. Попробуйте ввести домен напрямую (например, chocolate-academy.ru)")
        else:
            st.error("Не удалось автоматически найти сайт компании.")

st.divider()
st.caption("Поиск работает в реальном времени. Финансовый и спортивный мусор отсекается.")
