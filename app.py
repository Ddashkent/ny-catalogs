import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт PIL для фильтрации пропорций
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Упаковка", page_icon="📦", layout="wide"
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    .brand-logo {
        position: fixed; top: 15px; right: 20px; z-index: 9999;
        background-color: #dc2626; color: white; font-weight: 900;
        font-size: 15px; padding: 8px 18px; border-radius: 8px;
        border: 2px solid white; box-shadow: 0 4px 15px rgba(220,38,38,0.4);
    }
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.3; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake {
        position: fixed; top: -10px; color: #bae6fd; font-size: 11px;
        pointer-events: none; z-index: 1; user-select: none;
    }
    .f1 { left: 10%; animation: snowfall 16s linear infinite 0s; }
    .f2 { left: 35%; animation: snowfall 20s linear infinite 3s; }
    .f3 { left: 65%; animation: snowfall 18s linear infinite 1s; }
    .f4 { left: 90%; animation: snowfall 22s linear infinite 5s; }

    .doc-card {
        background-color: #ffffff; border-left: 6px solid #dc2626;
        padding: 16px; border-radius: 10px; margin-bottom: 15px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    }
    .btn-doc {
        background-color: #dc2626; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    .btn-download {
        background-color: #16a34a; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin: 15px 0;
    }
    .card-grid {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 10px; text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
        margin-bottom: 15px;
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 2px 8px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-top: 4px;
    }
    .card-title { font-weight: 600; font-size: 12px; color: #1e293b; margin-top: 5px; }
    </style>
    
    <div class="brand-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake f1">❄</div><div class="flake f2">❅</div>
    <div class="flake f3">❆</div><div class="flake f4">❄</div>
""", unsafe_allow_html=True)

st.title("📦 Экстрактор Картонной Упаковки 2026")
st.caption("Автоматический сбор карточек подарков с сайта. Юридические файлы блокируются.")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ЖЕСТКИЕ КОНСТАНТЫ
# -----------------------------

REQUIRED_DOC_WORDS = ["каталог", "прайс", "подарки", "2026", "2025", "новогод", "catalog", "price"]
JUNK_DOC_WORDS = ["политика", "согласие", "презентация", "реквизиты", "вакансии", "устав", "оферта", "договор", "cookies", "инвесторам"]

# Прямые разделы каталогов для известных фабрик (чтобы искать глубоко)
# Для "рэйд 21" добавлена прямая ссылка на раздел упаковки
SITE_ROUTES = {
    "rubin-2000.ru": "https://rubin-2000.ru/catalog/",
    "lakond.ru": "https://lakond.ru/catalog/",
    "akkond.ru": "https://akkond.ru/catalog/novogodnie-podarki/",
    "donko.su": "https://donko.su/catalog/",
    "podarki-reid21.ru": "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"
}

# Слова для исключения изображений (мусор, баннеры, текстиль)
BANNER_KEYWORDS = ["logo", "icon", "slider", "banner", "delivery", "payment", "bg-", "oplate"]
TEXTILE_JUNK = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка"]

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def get_domain_from_input(query: str) -> str:
    """Жесткое сопоставление названий фабрик с их сайтами"""
    q_low = query.lower().strip()
    
    # Прямое сопоставление с доменом
    if "рэйд" in q_low or "рейд" in q_low or "raid" in q_low:
        return "podarki-reid21.ru"
    if "рубин" in q_low or "rubin" in q_low:
        return "rubin-2000.ru"
    if "лаконд" in q_low or "lakond" in q_low:
        return "lakond.ru"
    if "акконд" in q_low or "akkond" in q_low:
        return "akkond.ru"
    if "академия шоколада" in q_low or "chocolate-academy" in q_low:
        return "chocolate-academy.ru"
    if "баян сулу" in q_low or "bayansulu" in q_low:
        return "bayansulu.kz"
    if "конфешн" in q_low or "confashion" in q_low:
        return "confashion.ru"
    
    # Если введен просто сайт
    if "." in query and " " not in query:
        return query.lower().replace("https://", "").replace("http://", "").split("/")[0]
    
    # Общий резервный поиск (не ломает ничего при ошибке)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{query}" кондитерская фабрика официальный сайт', max_results=2))
            if res and res[0].get("href"):
                parsed = urllib.parse.urlparse(res[0]["href"])
                netloc = parsed.netloc.replace("www.", "")
                return netloc
    except Exception:
        pass
    
    return None

def get_high_res(img_url: str) -> str:
    """Преобразует миниатюры в оригиналы высокого разрешения"""
    cleaned = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
    cleaned = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", cleaned)
    return cleaned

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

# -----------------------------
# ШАГ 1: ПОИСК ТОЛЬКО КАТАЛОГОВ (ЖЕСТКИЕ ФИЛЬТРЫ)
# -----------------------------

def scan_for_catalogs(domain: str):
    docs, seen = [], set()
    
    # 1. Проверяем прямой путь категории (если сайт в карте)
    check_paths = [f"https://{domain}"]
    if domain in SITE_ROUTES:
        check_paths.insert(0, SITE_ROUTES[domain])
        check_paths.extend([f"https://{domain}/catalog/", f"https://{domain}/shop/"])

    def check_url(url):
        page_docs = []
        p_url, p_html = get_html(url)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip()
                full_link = urllib.parse.urljoin(p_url, a["href"])
                
                # Фильтруем только файлы
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    # ЖЕСТКАЯ ПРОВЕРКА: нет мусора, но есть ключевые слова
                    combined = (text + " " + href).lower()
                    
                    # Блокируем презентации, соглашения, реквизиты
                    if any(junk in combined for junk in ["презентация", "соглашение", "реквизиты", "договор", "оферта", "политика", "конфиденциаль", "cookies", "вакансии", "инвесторам"]):
                        continue
                    
                    # Требуем наличие слов о товарах или сезоне
                    if any(good in combined for good in ["каталог", "прайс", "подарки", "новогод", "catalog", "price", "2026", "2025", "ассортимент"]):
                        page_docs.append({
                            "title": text or "Официальный каталог упаковки 2026",
                            "link": full_link
                        })
        return page_docs

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for res in executor.map(check_url, check_paths):
            for d in res:
                if d["link"] not in seen:
                    seen.add(d["link"])
                    docs.append(d)
    return docs

# -----------------------------
# ШАГ 2: ГЛУБОКИЙ ВИЗУАЛЬНЫЙ СБОР КОРОБОК (БЕЗ МУСОРА)
# -----------------------------

def is_real_product_image(img_url: str, text_context: str) -> bool:
    """Проверка: это фото коробки или баннер с инфографикой?"""
    try:
        url_low = img_url.lower()
        # Отсекаем иконки и сервисные картинки
        if any(bad in url_low for bad in ["logo", "icon", "avatar", "social", "vk", "youtube", "telegram"]):
            return False
        
        # Скачиваем миниатюру для анализа пропорций
        res = requests.get(img_url, headers=HEADERS, timeout=5, verify=False)
        if res.status_code == 200:
            # Если это текстовая страница или PDF, пропускаем
            content_type = res.headers.get("Content-Type", "").lower()
            if "text/html" in content_type or "application/pdf" in content_type:
                return False
            
            # Проверяем пропорции картинки для исключения баннеров
            if HAS_PIL and len(res.content) > 3000:
                img = Image.open(io.BytesIO(res.content))
                w, h = img.size
                if w < 140 or h < 140:
                    return False  # Мелкие иконки
                
                ratio = w / h
                # Баннеры с инфографикой (как на скрине) очень широкие или очень узкие
                # Коробки: от квадратных до вытянутых чуть-чуть
                if ratio > 1.8 or ratio < 0.35:
                    return False  # Баннер или инфографика с текстом
                
                # Исключаем картинки с очень длинными названиями, похожими на списки ингредиентов или описания баннеров
                if len(text_context) > 500:
                    return False
                    
                return True
    except Exception:
        pass
    return False

def scan_cardboard_products(domain: str):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        return []

    # 1. ГЛУБОКИЙ СБОР ССЫЛОК НА КАТЕГОРИИ
    pages = [final_url]
    soup = BeautifulSoup(html, "html.parser")
    
    # Добавляем прямые пути из карты, если это Рэйд-21 или другие
    if domain in SITE_ROUTES:
        for direct_path in SITE_ROUTES[domain]:
            if direct_path.startswith("https://"):
                direct_path = direct_path.replace("https://", "").replace("http://", "")
            pages.append(f"https://{domain}" + direct_path if not direct_path.startswith("/") else direct_path)
    
    # Также ищем любые ссылки на подкатегории в меню
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(" ", strip=True).lower()
        full = urllib.parse.urljoin(final_url, a["href"])
        # Берем только страницы каталога этого сайта
        if domain in full and not any(bad in href or bad in text for bad in ["oplate", "dostavka", "news", "contacts", "payment", "shipping", "textil"]):
            if any(good in href or good in text for good in ["catalog", "katalog", "podarki", "product", "category", "shop"]):
                if full not in pages:
                    pages.append(full)

    products = []
    seen_imgs = set()

    # 2. ПАРАЛЛЕЛЬНЫЙ СБОР КАРТОЧЕК СО ВСЕХ СТРАНИЦ
    def parse_page(p_url):
        p_items = []
        _, p_html = get_html(p_url)
        if not p_html:
            return []
        p_soup = BeautifulSoup(p_html, "html.parser")
        
        # Находим контейнеры с товарами
        containers = p_soup.find_all(["div", "li", "article"], class_=re.compile(r"product|catalog-item|card|item|goods|catalog|entry", re.I))
        if not containers:
            containers = p_soup.find_all("img")

        for card in containers:
            img = card if card.name == "img" else card.find("img")
            if not img:
                continue
            
            src = img.get("data-src") or img.get("data-original") or img.get("src")
            if not src or any(bad in src.lower() for bad in ["logo", "icon", "avatar"]):
                continue
            
            full_img = urllib.parse.urljoin(p_url, src)
            
            # Очищаем ссылку
            full_img = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", full_img)
            full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img)

            # Фильтруем текстиль и игрушки по названию карточки и описанию
            card_text = card.get_text(" ", strip=True) if card.name != "img" else ""
            combined_text = (card_text + " " + (img.get("alt") or "")).lower()
            
            # ЖЕСТКИЙ ФИЛЛЕР: Убираем мягкие игрушки и текстиль
            if any(bad in combined_text for bad in ["текстиль", "мягкая", "плюш", "игрушка", "ткань"]):
                continue
            
            # Фильтруем баннеры по пропорциям изображения (используем HTTP заголовки для быстрой проверки)
            try:
                img_check = requests.get(full_img, headers=HEADERS, timeout=4, verify=False)
                if img_check.status_code == 200 and len(img_check.content) > 3500:
                    if HAS_PIL:
                        img_pil = Image.open(io.BytesIO(img_check.content))
                        w, h = img_pil.size
                        if w < 140 or h < 140:
                            continue
                        ratio = w / h
                        if ratio > 1.55 or ratio < 0.38:
                            # Это баннер или инфографика с текстом — пропускаем
                            continue
                    
                    # Если прошли все фильтры — берем товар
                    weight_match = WEIGHT_REGEX.search(card_text)
                    weight = weight_match.group(1) if weight_match else None
                    
                    title = img.get("alt") or img.get("title") or card_text[:60]
                    title = re.sub(r"\s+", " ", title).strip()
                    
                    if len(title) > 3 and full_img not in seen_imgs:
                        seen_imgs.add(full_img)
                        p_items.append({
                            "title": title,
                            "weight": weight,
                            "img_url": full_img,
                            "img_bytes": img_check.content,
                        })
            except Exception:
                pass
                
        return p_items

    # Параллельный сбор
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(parse_page, pages)
        for res in results:
            products.extend(res)

    return products

# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input("Введите название фабрики или её сайт:", placeholder="Например: Рубин, Академия Шоколада, Лаконд, rubin-2000.ru...")

if st.button("🚀 НАЙТИ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.stop()
    
    input_str = company_input.strip()
    # Автоматическое определение домена
    domain = normalize_domain(input_str) if (".ru" in input_str or ".com" in input_str) else find_domain_dynamic(input_str)
    
    if not domain:
        # Если автоматически не определился — даем пользователю ввести напрямую
        st.info("Не удалось автоматически найти сайт. Если вы знаете прямой адрес, введите его в поле выше.")
        st.stop()
    
    st.success(f"🌐 Официальный источник найден: `{domain}`")
    
    # 1. Поиск официальных PDF/Excel файлов
    with st.spinner("ШАГ 1: Сканирую сайт на наличие официальных каталогов и прайсов..."):
        docs = scan_for_documents(domain)
    
    st.markdown("---")
    
    # Вывод PDF файлов
    if docs:
        st.subheader("📄 Официальные Каталоги и Прайсы")
        st.info("Найдены готовые PDF или Excel файлы. Вы можете скачать их ниже.")
        for d in docs:
            icon = "📕 PDF" if ".pdf" in d["link"].lower() else "📊 EXCEL/WORD"
            st.markdown(f"""
                <div style="background: white; border-left: 5px solid #28a745; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.05);">
                    <h4 style="margin: 0;">{icon} | {d['title']}</h4>
                    <a href="{d['link']}" target="_blank" style="display: inline-block; background: #dc2626; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 8px;">📥 СКАЧАТЬ ФАЙЛ</a>
                </div>
            """, unsafe_allow_html=True)
        st.markdown("---")
    
    else:
        st.info("Открытых PDF/Excel каталогов не обнаружено.")

    # 2. Сбор визуальных карточек упаковки
    with st.spinner("ШАГ 2: Извлекаю карточки упаковки, отсекая текстиль и баннеры..."):
        products = scan_cardboard_products(domain)
    
    st.markdown("---")
    
    if products:
        st.subheader(f"📦 Карточки Картонной Упаковки ({len(products)} шт.)")
        st.info("Это оригинальные фото коробок и упаковки с сайта заказчика. Текстиль, инфографика и баннеры отфильтрованы.")
        
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for i, prod in enumerate(products):
                name = re.sub(r"[^\w\s-]", "", prod["title"])[:20]
                zf.writestr(f"cardboard_{i+1:02d}_{name}.jpg", prod["img_bytes"])
        
        st.download_button("📥 СКАЧАТЬ ВСЕ КОРОБКИ В ZIP-АРХИВЕ", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")
        
        # Сетка отображения
        cols = st.columns(4)
        for i, prod in enumerate(products):
            with cols[i % 4]:
                st.markdown(f"""
                    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 20px;">
                        <div style="font-weight: bold; font-size: 12px; color: #1e293b; min-height: 36px;">{prod['title']}</div>
                        <span style="background: green; color: white; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: bold;">📦 КАРТОН</span>
                        {f'<br><span style="font-size: 11px; color: #666;">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                    </div>
                """, unsafe_allow_html=True)
                
                st.image(prod["img_bytes"], use_container_width=True)
    else:
        st.error("На сайте не удалось найти картонную упаковку. Вероятно, каталог закрыт или отсутствует.")

st.divider()
st.caption("Инструмент компании «Первый Снег». Жесткая фильтрация текстиля, игрушек и инфографики.")
