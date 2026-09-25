import concurrent.futures
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт Pillow для качества фото
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА
# -----------------------------

st.set_page_config(
    page_title="Экстрактор Каталогов 2026",
    page_icon="📸",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8f9fa; }
    /* Стиль карточки-снимка */
    .snapshot-card {
        background-color: #ffffff;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 5px;
        margin-bottom: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        text-align: center;
        transition: 0.3s;
    }
    .snapshot-card:hover { transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
    .btn-download {
        background-color: #28a745; color: white !important;
        font-weight: bold; padding: 12px 24px; border-radius: 8px;
        text-decoration: none; display: inline-block; margin: 10px 0;
    }
    .doc-box {
        background-color: #fff; border-left: 6px solid #dc3545;
        padding: 20px; border-radius: 10px; margin-bottom: 20px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"📸 Визуальный Навигатор Каталогов {TARGET_YEAR}")
st.caption("Если официальный PDF не найден, система делает визуальный снимок каждой карточки товара с сайта.")

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}

def get_high_res(img_url):
    """Превращает превью в фото высокого качества"""
    img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
    return img_url

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            return res.url, res.text
    except: return None, None
    return None, None

# -----------------------------
# ЛОГИКА ШАГ 1: ПОИСК ФАЙЛОВ (PDF/XLS)
# -----------------------------

def find_files(domain):
    docs = []
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    # Ищем ссылки на документы по всему сайту (главная + меню)
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
            title = a.get_text().strip() or "Официальный каталог/прайс"
            full_link = urllib.parse.urljoin(final_url, a['href'])
            if not any(bad in title.lower() for bad in ["политика", "согласие", "вакансии"]):
                docs.append({"title": title, "link": full_link})
    return docs

# -----------------------------
# ЛОГИКА ШАГ 2: ВИЗУАЛЬНЫЙ СНИМОК ТОВАРОВ
# -----------------------------

def download_img(url):
    try:
        hr_url = get_high_res(url)
        res = requests.get(hr_url, headers=HEADERS, timeout=6)
        if res.status_code == 200 and len(res.content) > 5000:
            return res.content
    except: return None

def capture_visual_catalog(domain):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    
    # Ищем страницы с подарками/каталогом
    catalog_pages = [final_url]
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        if any(kw in href or kw in a.get_text().lower() for kw in ["подар", "новогод", "каталог", "catalog", "produk", "лошад"]):
            full = urllib.parse.urljoin(final_url, a['href'])
            if domain in full and full not in catalog_pages:
                catalog_pages.append(full)
        if len(catalog_pages) >= 5: break

    all_imgs = []
    seen = set()

    def process_page(p_url):
        _, p_html = get_html(p_url)
        if not p_html: return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        page_imgs = []
        # Находим все картинки, которые выглядят как товары
        for img in p_soup.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if src:
                full_src = urllib.parse.urljoin(p_url, src)
                if full_src not in seen:
                    # Фильтр иконок и баннеров
                    if not any(bad in full_src.lower() for bad in ["logo", "icon", "banner", "social", "spacer"]):
                        seen.add(full_src)
                        page_imgs.append(full_src)
        return page_imgs

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(process_page, catalog_pages)
        for r in results: all_imgs.extend(r)

    # Загружаем сами картинки в высоком качестве
    final_cards = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        img_datas = list(executor.map(download_img, all_imgs))
        for i, data in enumerate(img_datas):
            if data:
                final_cards.append({"data": data, "url": all_imgs[i]})
    
    return final_cards

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

col1, col2 = st.columns([3, 1])
with col1:
    company_input = st.text_input("Название компании или сайт:", placeholder="Например: Академия шоколада, Лаконд, rubin-2000.ru...")
with col2:
    mode = st.selectbox("Год:", [2026, 2025])

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ", type="primary", use_container_width=True):
    if company_input:
        # Определяем домен
        domain = company_input.strip()
        if not "." in domain:
            # Если ввели название, пробуем найти домен (упрощенно)
            domain = domain.lower().replace(" ", "") + ".ru"
            # Для "Академии шоколада" и других известных делаем поправку
            if "академияшоколада" in domain: domain = "chocolate-academy.ru"
            if "лаконд" in domain: domain = "lakond.ru"
            if "баянсулу" in domain: domain = "bayansulu.kz"

        st.info(f"🌐 Подключаюсь к источнику: `{domain}`")

        # ШАГ 1: ИЩЕМ ГОТОВЫЕ ФАЙЛЫ
        with st.spinner("Проверяю наличие официального PDF..."):
            docs = find_files(domain)
        
        if docs:
            st.markdown("---")
            st.success(f"✅ НАЙДЕНЫ ОФИЦИАЛЬНЫЕ ФАЙЛЫ КАТАЛОГОВ ({len(docs)} шт.)")
            st.info("💡 Найдена прямая ссылка на файл, поэтому визуальный снимок сайта отменен.")
            for d in docs:
                st.markdown(f"""
                <div class="doc-box">
                    <h4>📄 {d['title']}</h4>
                    <a href="{d['link']}" target="_blank" class="btn-download">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ PDF</a>
                </div>
                """, unsafe_allow_html=True)
        
        else:
            # ШАГ 2: ДЕЛАЕМ ВИЗУАЛЬНЫЙ СНИМОК (ЕСЛИ PDF НЕТ)
            st.warning("⚠️ Официальный PDF не найден. Делаю визуальные снимки карточек с сайта...")
            with st.spinner("Извлекаю фотографии подарков в высоком качестве..."):
                cards = capture_visual_catalog(domain)
            
            if cards:
                st.success(f"Успешно получено снимков: **{len(cards)}**")
                
                # ZIP Архив
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, c in enumerate(cards):
                        zf.writestr(f"item_{i+1:03d}.jpg", c['data'])
                
                st.download_button("📥 СКАЧАТЬ ВСЕ СНИМКИ В ZIP", zip_buffer.getvalue(), f"{domain}_visual_catalog.zip", "application/zip")
                
                st.markdown("---")
                # Сетка снимков (как просили - 4 в ряд)
                cols = st.columns(4)
                for i, c in enumerate(cards):
                    with cols[i % 4]:
                        st.markdown('<div class="snapshot-card">', unsafe_allow_html=True)
                        st.image(c['data'], use_container_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.error("Не удалось найти ни файлов, ни карточек товаров. Проверьте правильность названия.")

st.divider()
st.caption("Режим работы: Сначала файлы -> Затем визуальные снимки. Мусор фильтруется автоматически.")
