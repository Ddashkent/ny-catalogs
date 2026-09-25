import concurrent.futures
import io
import re
import urllib.parse
import zipfile
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from PIL import Image
import requests
import streamlit as st

# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Скоростной Парсер Подарков 2026",
    page_icon="🎁",
    layout="wide",
)

TARGET_YEAR = 2026

# Стилизация карточек точь-в-точь как в каталогах
st.markdown(
    """
    <style>
    .stApp { background-color: #f4f6f9; }
    .product-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.03);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .badge-status {
        background-color: #28a745;
        color: white;
        font-weight: bold;
        padding: 3px 8px;
        font-size: 11px;
        border-radius: 4px;
        display: inline-block;
        margin-bottom: 6px;
    }
    .badge-weight {
        background-color: #007bff;
        color: white;
        font-weight: bold;
        padding: 2px 8px;
        font-size: 12px;
        border-radius: 10px;
        display: inline-block;
        margin-top: 4px;
    }
    .product-title {
        font-weight: 700;
        font-size: 13px;
        color: #1a202c;
        margin: 6px 0;
        line-height: 1.3;
        min-height: 36px;
    }
    .img-container {
        height: 220px;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"🎁 Быстрый Парсер Подарков & Упаковки {TARGET_YEAR}")
st.caption(
    "Высокоскоростной сбор каталогов: мгновенно извлекает фото высочайшего качества, названия и вес подарков."
)

# -----------------------------
# БАЗА ЗНАНИЙ
# -----------------------------

KNOWLEDGE_BASE = {
    "акконд": "akkond.ru",
    "рубин": "rubin-2000.ru",
    "лаконд": "lakond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "баянсулу": "bayansulu.kz",
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
    "фортуна": "fortuna-podarki.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
}

SEARCH_ENGINE_DOMAINS = [
    "bing.com",
    "google.",
    "yandex.",
    "wikipedia.org",
    "otzovik.com",
    "avito.ru",
    "checko.ru",
    "list-org.com",
]
JUNK_WORDS = [
    "политика",
    "персональных",
    "согласие",
    "cookies",
    "вакансии",
    "акции",
    "stock",
    "finance",
]
CATALOG_WORDS = [
    "новогод",
    "подар",
    "набор",
    "упаков",
    "каталог",
    "продукц",
    "сладк",
    "конфет",
    "gift",
    "catalog",
    "product",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

WEIGHT_REGEX = re.compile(
    r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE
)

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def normalize_domain(value: str) -> str:
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.lower().replace("www.", "")


def get_high_res_url(img_url: str) -> str:
    """Преобразует ссылки-превью в полноразмерные оригиналы высокого разрешения"""
    # Удаляем Битрикс-ресайзы (/resize_cache/.../)
    img_url = re.sub(
        r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url
    )
    # Удаляем суффиксы размеров файлов вида -300x300.jpg -> .jpg
    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
    return img_url


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            return res.url, res.text
    except:
        pass
    return None, None


def find_official_site(company_name: str):
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v
    try:
        with DDGS() as ddgs:
            res = list(
                ddgs.text(
                    f'"{company_name}" кондитерская фабрика подарки упаковка официальный сайт',
                    region="ru-ru",
                    max_results=5,
                )
            )
            for r in res:
                link = r.get("href", "")
                if link and not any(bad in link for bad in SEARCH_ENGINE_DOMAINS):
                    return normalize_domain(link)
    except:
        pass
    return None


def scan_catalog_urls(domain: str):
    """Быстрый поиск основных разделов каталогов"""
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    found = [final_url]
    checked = {final_url}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        full_url = urllib.parse.urljoin(final_url, href)

        if domain in full_url and not any(bad in text for bad in JUNK_WORDS):
            if any(cw in text or cw in href.lower() for cw in CATALOG_WORDS):
                clean_url = full_url.split("#")[0]
                if clean_url not in checked:
                    checked.add(clean_url)
                    found.append(clean_url)

        if len(found) >= 12:  # Лимит для высокой скорости
            break

    return found


def download_high_quality_image(image_url: str):
    """Загрузка картинки и жесткая проверка на высокое качество (дизайн)"""
    try:
        image_url = get_high_res_url(image_url)
        res = requests.get(image_url, headers=HEADERS, timeout=6)
        if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""):
            data = res.content
            if len(data) < 8000:  # Пропускаем мелкие иконки (< 8 Кб)
                return None

            img = Image.open(io.BytesIO(data))
            w, h = img.size

            # Игнорируем мелкие картинки и вытянутые баннеры
            if w < 220 or h < 220:
                return None
            ratio = w / h
            if ratio > 3.0 or ratio < 0.3:
                return None

            ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            return {"bytes": data, "ext": ext, "width": w, "height": h}
    except:
        pass
    return None


# -----------------------------
# ПАРСИНГ КАРТОЧЕК ТОВАРОВ
# -----------------------------


def parse_product_card(card_soup, page_url):
    """Умное извлечение товара: Название + Вес + Высококачественное Фото"""
    # 1. Поиск Картинки
    img_tag = card_soup.find("img")
    if not img_tag:
        return None

    src = (
        img_tag.get("data-src")
        or img_tag.get("data-original")
        or img_tag.get("src")
    )
    if not src:
        return None

    full_img_url = urllib.parse.urljoin(page_url, src)

    # 2. Поиск Текста карточки
    card_text = card_soup.get_text(" ", strip=True)

    # Извлечение веса (например "800 г", "1.2 кг")
    weight_match = WEIGHT_REGEX.search(card_text)
    weight = weight_match.group(1) if weight_match else None

    # Поиск нормального Названия (заголовки h2-h4 или ссылки/классы)
    title_tag = card_soup.find(["h2", "h3", "h4", "a", "div"], class_=re.compile(r"title|name|heading|caption|product", re.I))
    if title_tag:
        title = title_tag.get_text(" ", strip=True)
    else:
        title = img_tag.get("alt") or img_tag.get("title") or card_text[:60]

    # Очистка названия от мусора
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) < 3 or any(junk in title.lower() for junk in JUNK_WORDS):
        return None

    # Поиск статуса (например "ПРЕДЗАКАЗ", "В наличии", "Новинка")
    status = "ПРЕДЗАКАЗ" if "предзаказ" in card_text.lower() else ("В НАЛИЧИИ" if "наличи" in card_text.lower() else "НОВЫЙ ГОД")

    return {
        "title": title,
        "weight": weight,
        "status": status,
        "img_url": full_img_url,
        "page_url": page_url,
    }


def parse_catalog_page_parallel(page_url):
    """Быстрый парсинг страницы с товарами"""
    final_url, html = get_html(page_url)
    if not html:
        return [], []

    soup = BeautifulSoup(html, "html.parser")

    # Сбор документов (PDF/XLS)
    docs = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
            if not any(bad in a.get_text().lower() for bad in JUNK_WORDS):
                docs.append({
                    "title": a.get_text().strip() or "Скачать каталог/прайс",
                    "link": urllib.parse.urljoin(final_url, a["href"])
                })

    # Сбор товаров по контейнерам карточек
    products = []
    # Популярные классы карточек товаров в CMS (Битрикс, Tilda, Insales, WooCommerce)
    card_containers = soup.find_all(
        lambda tag: tag.name in ["div", "li", "article"]
        and tag.get("class")
        and any(c in " ".join(tag.get("class")).lower() for c in ["product", "catalog-item", "card", "goods-item", "item"])
    )

    if card_containers:
        for card in card_containers:
            parsed = parse_product_card(card, final_url)
            if parsed:
                products.append(parsed)

    # Запасной вариант: если стандартные карточки не распознаны
    if not products:
        for img in soup.find_all("img"):
            parent = img.parent
            if parent:
                parsed = parse_product_card(parent, final_url)
                if parsed:
                    products.append(parsed)

    return docs, products


# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

mode = st.radio(
    "Режим работы:",
    ["🔍 По названию компании", "🌐 Прямой ввод домена/сайта"],
    horizontal=True,
)

domain = None

if mode == "🔍 По названию компании":
    company_input = st.text_input(
        "Введите название компании:",
        placeholder="Например: Акконд, Рубин, Лаконд, Баян Сулу...",
    )
    if company_input.strip():
        if "." in company_input and " " not in company_input:
            domain = normalize_domain(company_input)
        else:
            with st.spinner("Определяю официальный сайт..."):
                domain = find_official_site(company_input.strip())
else:
    site_input = st.text_input(
        "Введите домен напрямую:", placeholder="Например: akkond.ru, rubin-2000.ru"
    )
    if site_input.strip():
        domain = normalize_domain(site_input)

if st.button("🚀 ЗАПУСТИТЬ УСКОРЕННЫЙ СБОР", type="primary"):
    if not domain:
        st.error("Не удалось найти сайт. Введите верное название или укажите домен напрямую.")
        st.stop()

    st.success(f"🌐 Подключено к сайту: `{domain}`")

    # 1. Быстрый сбор ссылок
    with st.spinner("Сканирую структуру каталога..."):
        catalog_pages = scan_catalog_urls(domain)

    st.write(f"Найдено каталожных разделов: **{len(catalog_pages)}**")

    # 2. МНОГОПОТОЧНЫЙ ПАРСИНГ СТРАНИЦ (ThreadPoolExecutor для скорости)
    all_docs = []
    all_products_raw = []

    progress = st.progress(0)
    status = st.empty()
    status.write("⚡ Запущена многопоточная обработка страниц...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(parse_catalog_page_parallel, url): url for url in catalog_pages}
        completed = 0
        for future in concurrent.futures.as_completed(future_to_url):
            docs, prods = future.result()
            all_docs.extend(docs)
            all_products_raw.extend(prods)
            completed += 1
            progress.progress(completed / len(catalog_pages))

    status.empty()
    progress.empty()

    # Убираем дубликаты товаров
    unique_products = []
    seen_imgs = set()
    for p in all_products_raw:
        if p["img_url"] not in seen_imgs:
            seen_imgs.add(p["img_url"])
            unique_products.append(p)

    # 3. МНОГОПОТОЧНАЯ ЗАГРУЗКА И ВАЛИДАЦИЯ КАРТИНОК В ВЫСОКОМ КАЧЕСТВЕ
    validated_products = []
    if unique_products:
        status.write("🖼️ Загружаю и проверяю фотографии подарков в высоком качестве...")
        
        def download_product_image(product):
            img_data = download_high_quality_image(product["img_url"])
            if img_data:
                product["img_bytes"] = img_data["bytes"]
                product["ext"] = img_data["ext"]
                return product
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(download_product_image, unique_products[:36])) # Лимит 36 лучших товаров
            validated_products = [r for r in results if r is not None]

        status.empty()

    # ВЫВОД РЕЗУЛЬТАТОВ
    tab1, tab2 = st.tabs(["🎁 Визуальный Каталог Подарков (С Названиями и Весом)", "📄 Документы и Прайсы (PDF/XLS)"])

    # ВКЛАДКА 1: Карточки товаров
    with tab1:
        if validated_products:
            st.success(f"Успешно обработано карточек подарков: **{len(validated_products)}**")

            # Скачивание ZIP архива всех картинок
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, prod in enumerate(validated_products, start=1):
                    safe_name = re.sub(r'[^\w\s-]', '', prod['title'])[:30]
                    weight_str = f"_{prod['weight']}" if prod['weight'] else ""
                    filename = f"{idx:02d}_{safe_name}{weight_str}.{prod['ext']}"
                    zf.writestr(filename, prod["img_bytes"])
            
            st.download_button(
                "📥 СКАЧАТЬ ВСЕ ФОТО ПОДАРКОВ (ZIP-АРХИВ)",
                data=zip_buffer.getvalue(),
                file_name=f"{domain}_gifts_catalog.zip",
                mime="application/zip",
            )

            st.markdown("---")

            # Отображение сетки карт (4 карточки в ряд, как на скриншоте)
            cols = st.columns(4)
            for idx, prod in enumerate(validated_products):
                with cols[idx % 4]:
                    st.markdown(
                        f"""
                        <div class="product-card">
                            <div>
                                <span class="badge-status">{prod['status']}</span>
                                <div class="img-container">
                                    <img src="data:image/{prod['ext']};base64,{io.BytesIO(prod['img_bytes']).read().hex()}" style="max-height: 200px; max-width: 100%; object-fit: contain;">
                                </div>
                            </div>
                            <div>
                                <div class="product-title">{prod['title']}</div>
                                {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.image(prod["img_bytes"], use_container_width=True) # Резервное отображение для Streamlit
        else:
            st.warning("Товарные карточки с фотографиями высокаго качества не удалось извлечь автоматически.")

    # ВКЛАДКА 2: Файлы
    with tab2:
        unique_docs = list({d["link"]: d for d in all_docs}.values())
        if unique_docs:
            st.success(f"Найдено PDF / Excel файлов: {len(unique_docs)}")
            for d in unique_docs:
                st.markdown(f"📄 **[{d['title']}]({d['link']})**")
        else:
            st.info("Открытые PDF/Excel файлы на каталоговых страницах не найдены.")
