import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Отключаем предупреждения
requests.packages.urllib3.disable_warnings()

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(page_title="Первый Снег | Экстрактор Коробок", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 10px 20px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
    }
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #93c5fd; pointer-events: none; z-index: 0; }
    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.03); margin-bottom: 20px;
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 4px;
        display: inline-block; margin-bottom: 5px;
    }
    </style>
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake" style="left:15%; animation: snowfall 18s linear infinite;">❄</div>
    <div class="flake" style="left:50%; animation: snowfall 22s linear infinite 4s;">❅</div>
    <div class="flake" style="left:85%; animation: snowfall 20s linear infinite 2s;">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Сбор Картонной Упаковки {TARGET_YEAR}")
st.caption("Система настроена на глубокий поиск в категориях 'Подарки в картонной упаковке'.")

# -----------------------------
# ЛОГИКА
# -----------------------------

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def scan_page_for_items(url):
    """Парсит карточки товаров с конкретной страницы"""
    items = []
    curr_url, html = get_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Ищем картинки товаров (на Рэйд-21 это обычно внутри a или div с классом product)
    containers = soup.find_all(["div", "li"], class_=re.compile(r"product|item|card", re.I))
    if not containers: containers = soup.find_all("img")

    seen_imgs = set()
    for card in containers:
        img = card if card.name == "img" else card.find("img")
        if not img: continue
        
        src = img.get("data-src") or img.get("src")
        if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg-", "delivery", "payment"]): continue
        
        full_img = urllib.parse.urljoin(curr_url, src)
        # Улучшаем качество (убираем ресайзы)
        full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img)
        
        if full_img in seen_imgs: continue
        
        text = card.get_text(" ", strip=True) if card.name != "img" else ""
        title = img.get("alt") or img.get("title") or text[:50]
        
        # Если в названии "Текстиль", "Мягкая" - пропускаем
        if any(bad in title.lower() for bad in ["текстиль", "мягкая", "игрушка", "плюш", "рюкзак"]): continue
        
        seen_imgs.add(full_img)
        items.append({"title": title.strip(), "img": full_img})
    return items

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

user_input = st.text_input("Введите название фабрики или ССЫЛКУ на раздел каталога:", 
                           placeholder="Например: Рэйд-21 или вставьте полную ссылку на раздел...")

if st.button("🚀 НАЙТИ КОРОБКИ", type="primary"):
    if user_input:
        target_url = user_input.strip()
        
        # Если ввели просто "Рэйд 21" - подставляем вашу ссылку
        if "рэйд" in target_url.lower() or "reid" in target_url.lower():
            if not target_url.startswith("http"):
                target_url = "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"
        
        # Если ввели не ссылку, а название - пробуем найти сайт (упрощенно)
        if not target_url.startswith("http"):
            st.warning("Для точности лучше вставьте ссылку на раздел сайта. Пробую искать...")
            # Тут можно оставить старую логику поиска домена, но для Рэйд уже сработало условие выше.

        st.info(f"🔎 Сканирую страницу: `{target_url}`")
        
        with st.spinner("Загружаю карточки товаров..."):
            items = scan_page_for_items(target_url)
        
        if items:
            st.success(f"Найдено коробок: **{len(items)} шт.**")
            
            # ZIP
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for i, it in enumerate(items):
                    try:
                        res = requests.get(it['img'], timeout=5)
                        if res.status_code == 200:
                            zf.writestr(f"box_{i+1:02d}.jpg", res.content)
                    except: continue
            
            st.download_button("📥 СКАЧАТЬ ВСЕ В ZIP", zip_buf.getvalue(), "catalog_boxes.zip", "application/zip")

            st.markdown("---")
            cols = st.columns(4)
            for i, it in enumerate(items):
                with cols[i % 4]:
                    st.markdown('<div class="product-card">', unsafe_allow_html=True)
                    st.image(it['img'], use_container_width=True)
                    st.markdown(f'<span class="badge-cardboard">📦 КАРТОН</span><br><b>{it["title"][:50]}</b></div>', unsafe_allow_html=True)
        else:
            st.error("Не удалось найти коробки по этому адресу. Проверьте, что ссылка ведет на страницу с товарами.")
