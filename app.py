import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st
import io
import zipfile

# 1. Настройка страницы
st.set_page_config(page_title="Снайпер Каталогов 2026", page_icon="🍬", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .catalog-card { 
        background-color: #ffffff; border-left: 6px solid #e91e63; 
        padding: 15px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .img-container {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 5px;
        background: white;
        text-align: center;
        margin-bottom: 15px;
    }
    .download-btn {
        background-color: #e91e63; color: white !important;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        font-weight: bold; display: inline-block; margin-top: 8px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🍬 Снайпер-Экстрактор Подарков 2026")
st.caption("Глубокий сканер: находит сайт, переходит в разделы каталога и выгружает реальные изображения упаковок и подарков.")

target_year = 2026

KNOWLEDGE_BASE = {
    "лаконд": "lakond.ru", "акконд": "akkond.ru", "донко": "donko.su", "тор": "donko.su",
    "рубин": "rubin-2000.ru", "дилявер": "dilaver.ru", "главупак": "glavupak.ru",
    "коммунарка": "kommunarka.by", "спартак": "spartak.by", "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz", "славянка": "slavyanka.ru", "победа": "pobeda.market"
}

# Исключаем юридический мусор
JUNK_DOCS = ["политика", "обработка", "персональных", "данных", "согласие", "соглашение", "вакансии"]

# Исключаем баннеры, логотипы, фоны и системные картинки
JUNK_IMAGES = [
    "logo", "icon", "banner", "slide", "bg_", "background", "decor", "spacer", "sprite", 
    "theme", "pattern", "partner", "avatar", "basket", "cart", "system", "header", "footer",
    "instagram", "vk", "facebook", "telegram", "whatsapp"
]

# --- УМНЫЕ ФУНКЦИИ ---

def find_site(query):
    q_low = query.lower().strip()
    if q_low in KNOWLEDGE_BASE: return KNOWLEDGE_BASE[q_low]
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{query}" кондитерская фабрика официальный сайт', max_results=3))
            for r in res:
                if not any(x in r['href'] for x in ["wiki", "otzovik", "checko", "list-org"]):
                    return urllib.parse.urlparse(r['href']).netloc
    except: return None

def deep_scrape_catalog(url):
    """Ищет раздел каталога и парсит картинки товаров оттуда"""
    docs, product_imgs = [], []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    base_url = url if url.startswith("http") else f"http://{url}"
    
    try:
        # Шаг 1. Читаем главную страницу
        res = requests.get(base_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Шаг 2. Ищем ссылки на ПДФ и прайсы на главной
        for a in soup.find_all("a", href=True):
            h, t = a['href'].lower(), a.get_text().lower()
            if any(ext in h for ext in [".pdf", ".xlsx", ".xls"]):
                if not any(junk in t or junk in h for junk in JUNK_DOCS):
                    full_link = urllib.parse.urljoin(base_url, a['href'])
                    docs.append({"title": a.get_text().strip() or "Каталог PDF", "link": full_link})

        # Шаг 3. Ищем ссылки на подразделы КАТАЛОГА (например, /catalog/upakovka)
        catalog_urls = [base_url] # Главную страницу тоже проверяем
        for a in soup.find_all("a", href=True):
            href = a['href'].lower()
            if any(kw in href for kw in ["catalog", "catalog/novogod", "products", "upakovka", "podarki", "magazin", "shop"]):
                full_link = urllib.parse.urljoin(base_url, a['href'])
                if full_link not in catalog_urls:
                    catalog_urls.append(full_link)

        # Шаг 4. Обходим первые 4 найденных раздела каталога и вытягиваем фото товаров
        for cat_url in catalog_urls[:4]:
            try:
                cat_res = requests.get(cat_url, headers=headers, timeout=5)
                cat_soup = BeautifulSoup(cat_res.text, "html.parser")
                
                for img in cat_soup.find_all("img", src=True):
                    src = img['src'].lower()
                    # Жесткий фильтр: исключаем баннеры, логотипы и мелкие иконки
                    if any(bad in src for bad in JUNK_IMAGES):
                        continue
                    
                    # Проверяем, что картинка лежит в папке товаров (обычно upload, products, iblock, images)
                    if any(good in src for good in ["upload", "product", "iblock", "goods", "catalog", "images", "photo"]):
                        full_img_url = urllib.parse.urljoin(base_url, img['src'])
                        if full_img_url not in product_imgs:
                            product_imgs.append(full_img_url)
            except:
                continue
                
    except: pass
    return docs, product_imgs

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании:", placeholder="Например: Рубин, Лаконд, Баян Сулу")

if st.button("🚀 ЗАПУСТИТЬ ГЛУБОКИЙ СБОР ДАННЫХ", type="primary"):
    if company_query:
        site = find_site(company_query)
        if site:
            st.success(f"🌐 Сайт определен: `{site}`. Выполняю глубокое сканирование каталогов...")
            
            # Запуск глубокого парсинга
            with st.spinner("Захожу в разделы продукции и вытаскиваю фото товаров..."):
                docs, imgs = deep_scrape_catalog(site)
            
            tab1, tab2 = st.tabs(["📄 Каталоги и Прайсы (PDF/XLS)", "🎁 Реальные изображения товаров"])
            
            with tab1:
                if docs:
                    st.write("### Найдено файлов:")
                    unique_docs = {d['link']: d for d in docs}.values()
                    for d in unique_docs:
                        st.markdown(f"✅ **{d['title']}** — [Скачать]({d['link']})")
                else: 
                    st.warning("Прямых PDF/XLS файлов на главной странице не обнаружено.")
            
            with tab2:
                if imgs:
                    st.write(f"### Обнаружено реальных упаковок и подарков в каталоге: {len(imgs)}")
                    
                    # Кнопка скачивания всех картинок в ZIP
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
                        for i, img_url in enumerate(imgs[:60]): # Ограничим до 60 картинок
                            try:
                                img_res = requests.get(img_url, timeout=5)
                                if img_res.status_code == 200:
                                    ext = "jpg"
                                    if ".png" in img_url.lower(): ext = "png"
                                    zip_file.writestr(f"gift_package_{i+1}.{ext}", img_res.content)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ВСЕ ИЗОБРАЖЕНИЯ В ZIP", zip_buffer.getvalue(), f"{company_query}_products_2026.zip", "application/zip")
                    
                    # Вывод картинок в сетку
                    cols = st.columns(4)
                    for idx, img_url in enumerate(imgs[:32]): # Выводим первые 32 товара
                        with cols[idx % 4]:
                            st.markdown(f"""
                            <div class="img-container">
                                <img src="{img_url}" style="max-width:100%; max-height:200px; object-fit:contain; border-radius:5px;"><br>
                                <span style="font-size:11px; color:#777;">Товар {idx+1}</span>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.warning("Изображения подарков не найдены. Возможно, сайт требует авторизации или каталог закрыт.")
        else:
            st.error("Не удалось найти официальный сайт фабрики.")

st.divider()
st.info("💡 **Как это работает:** Алгоритм находит разделы `/catalog/` или `/products/` и сканирует именно их, игнорируя баннеры с главной страницы.")
