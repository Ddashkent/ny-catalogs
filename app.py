import concurrent.futures
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт Pillow
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Безопасный импорт DuckDuckGo
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Умный Навигатор Каталогов 2026",
    page_icon="🎁",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f4f6f9; }
    .doc-card {
        background-color: #ffffff;
        border-left: 6px solid #28a745;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #28a745;
        color: white !important;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 6px;
        text-decoration: none;
        display: inline-block;
        margin-top: 8px;
    }
    .btn-doc:hover { background-color: #218838; }
    .product-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.03);
    }
    .badge-weight {
        background-color: #007bff;
        color: white;
        font-weight: bold;
        padding: 3px 10px;
        font-size: 13px;
        border-radius: 12px;
        display: inline-block;
        margin-top: 5px;
    }
    .product-title {
        font-weight: 700;
        font-size: 14px;
        color: #1a202c;
        margin: 8px 0;
        line-height: 1.3;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"🎁 Навигатор Каталогов & Прайсов {TARGET_YEAR}")
st.caption(
    "Приоритетный поиск официальных PDF/Excel файлов. Поиск картинок включается только если файла нет."
)

# -----------------------------
# БАЗА ЗНАНИЙ ФАБРИК
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
    "красный мозырянин": "mozyrconfectionery.by",
}

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
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.lower().replace("www.", "")


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


def find_official_site(company_name: str):
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v

    if HAS_DDGS:
        try:
            with DDGS() as ddgs:
                res = list(
                    ddgs.text(
                        f'"{company_name}" кондитерская фабрика подарки официальный сайт',
                        region="ru-ru",
                        max_results=4,
                    )
                )
                for r in res:
                    link = r.get("href", "")
                    if link and not any(
                        bad in link
                        for bad in [
                            "wikipedia",
                            "checko",
                            "list-org",
                            "otzovik",
                            "vk.com",
                        ]
                    ):
                        return normalize_domain(link)
        except Exception:
            pass
    return None


# -----------------------------
# ШАГ 1: ПОИСК ТОЛЬКО ДОКУМЕНТОВ (PDF / EXCEL)
# -----------------------------


def scan_for_documents_only(domain: str):
    """Быстрый поиск готовых файлов каталогов и прайсов"""
    docs = []
    seen = set()

    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    # Сканируем ссылки на главной и в разделах
    scan_urls = [final_url] if final_url else []

    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text().strip()
            full_url = urllib.parse.urljoin(final_url, href)

            # Собираем прямые документы
            if any(ext in href.lower() for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                if not any(bad in text.lower() for bad in JUNK_WORDS):
                    if full_url not in seen:
                        seen.add(full_url)
                        docs.append(
                            {
                                "title": text or "Скачать каталог / прайс-лист",
                                "link": full_url,
                            }
                        )

            # Собираем ссылки на страницы каталогов для глубокой проверки
            elif domain in full_url and any(
                cw in text.lower() or cw in href.lower() for cw in CATALOG_WORDS
            ):
                if full_url not in scan_urls and len(scan_urls) < 6:
                    scan_urls.append(full_url)

    # Проверяем найденные страницы каталогов на наличие PDF/Excel
    for page in scan_urls[1:]:
        p_url, p_html = get_html(page)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text().strip()
                full_url = urllib.parse.urljoin(p_url, href)

                if any(
                    ext in href.lower() for ext in [".pdf", ".xlsx", ".xls", ".doc"]
                ):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        if full_url not in seen:
                            seen.add(full_url)
                            docs.append(
                                {
                                    "title": text or "Скачать каталог / прайс-лист",
                                    "link": full_url,
                                }
                            )

    return docs


# -----------------------------
# ШАГ 2: СБОР КАРТОЧЕК С САЙТА (ЕСЛИ НЕТ ФАЙЛОВ)
# -----------------------------


def get_high_res_url(img_url: str) -> str:
    img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
    return img_url


def download_product_image(img_url: str):
    try:
        img_url = get_high_res_url(img_url)
        res = requests.get(img_url, headers=HEADERS, timeout=5)
        if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""):
            data = res.content
            if len(data) < 6000:
                return None

            if HAS_PIL:
                img = Image.open(io.BytesIO(data))
                w, h = img.size
                if w < 180 or h < 180:
                    return None
                ratio = w / h
                if ratio > 3.2 or ratio < 0.3:
                    return None
                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"

            return {"bytes": data, "ext": ext}
    except Exception:
        pass
    return None


def parse_page_for_products(page_url):
    final_url, html = get_html(page_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products = []

    containers = soup.find_all(
        lambda tag: tag.name in ["div", "li", "article"]
        and tag.get("class")
        and any(
            c in " ".join(tag.get("class")).lower()
            for c in ["product", "catalog-item", "card", "goods-item", "item"]
        )
    )

    for card in containers:
        img_tag = card.find("img")
        if not img_tag:
            continue
        src = (
            img_tag.get("data-src")
            or img_tag.get("data-original")
            or img_tag.get("src")
        )
        if not src:
            continue

        full_img = urllib.parse.urljoin(final_url, src)
        card_text = card.get_text(" ", strip=True)

        weight_match = WEIGHT_REGEX.search(card_text)
        weight = weight_match.group(1) if weight_match else None

        title_tag = card.find(
            ["h2", "h3", "h4", "a"],
            class_=re.compile(r"title|name|heading|product", re.I),
        )
        title = (
            title_tag.get_text(" ", strip=True)
            if title_tag
            else (img_tag.get("alt") or card_text[:50])
        )
        title = re.sub(r"\s+", " ", title).strip()

        if len(title) > 3 and not any(bad in title.lower() for bad in JUNK_WORDS):
            products.append(
                {
                    "title": title,
                    "weight": weight,
                    "img_url": full_img,
                }
            )

    return products


def scan_products_fallback(domain):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    pages = [final_url]
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        full = urllib.parse.urljoin(final_url, href)
        if domain in full and any(cw in text or cw in href for cw in CATALOG_WORDS):
            if full not in pages:
                pages.append(full)
        if len(pages) >= 6:
            break

    raw_products = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(parse_page_for_products, pages)
        for res in results:
            raw_products.extend(res)

    unique_prods = []
    seen = set()
    for p in raw_products:
        if p["img_url"] not in seen:
            seen.add(p["img_url"])
            unique_prods.append(p)

    def fetch_img(p):
        img_info = download_product_image(p["img_url"])
        if img_info:
            p["img_bytes"] = img_info["bytes"]
            p["ext"] = img_info["ext"]
            return p
        return None

    validated = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        res = executor.map(fetch_img, unique_prods[:28])
        validated = [r for r in res if r is not None]

    return validated


# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

mode = st.radio(
    "Режим поиска:",
    ["🔍 По названию компании", "🌐 Прямой ввод сайта/домена"],
    horizontal=True,
)

domain = None

if mode == "🔍 По названию компании":
    company_input = st.text_input(
        "Введите название компании:",
        placeholder="Например: Рубин, Акконд, Лаконд, Баян Сулу...",
    )
    if company_input.strip():
        if "." in company_input and " " not in company_input:
            domain = normalize_domain(company_input)
        else:
            domain = find_official_site(company_input.strip())
else:
    site_input = st.text_input(
        "Введите домен напрямую:", placeholder="Например: rubin-2000.ru, lakond.ru"
    )
    if site_input.strip():
        domain = normalize_domain(site_input)

if st.button("🚀 ЗАПУСТИТЬ ПОИСК КАТАЛОГА", type="primary"):
    if not domain:
        st.error(
            "Не удалось определить сайт. Переключите режим и введите домен компании напрямую (например, lakond.ru)."
        )
        st.stop()

    st.success(f"🌐 Подключено к официальному сайту: `{domain}`")

    # ==========================================
    # ШАГ 1: ПРИОРИТЕТНЫЙ ПОИСК ФАЙЛОВ КАТАЛОГОВ
    # ==========================================
    with st.spinner(
        "ШАГ 1: Сканируем сайт на наличие официальных файлов (PDF / Excel)..."
    ):
        documents = scan_for_documents_only(domain)

    if documents:
        st.markdown("---")
        st.success(
            f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ / ПРАЙС-ЛИСТ (ФАЙЛОВ: {len(documents)})!**"
        )
        st.info(
            "💡 **Поиск картинок отменен**, так как найден полный официальный файл каталога."
        )

        for doc in documents:
            icon = "📕 PDF" if ".pdf" in doc["link"].lower() else "📊 EXCEL / DOC"
            st.markdown(
                f"""
                <div class="doc-card">
                    <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                    <p style="font-size:12px; color:gray; margin:4px 0;">Ссылка: {doc['link']}</p>
                    <a href="{doc['link']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                </div>
                """,
                unsafe_allow_html=True,
            )

    else:
        # ==========================================
        # ШАГ 2: СБОР КАРТОЧЕК С САЙТА (ЕСЛИ ФАЙЛОВ НЕТ)
        # ==========================================
        st.warning("⚠️ **Прямые файлы PDF/Excel на страницах сайта не найдены.**")
        st.info(
            "🔄 Автоматически переходим к **Сбору карточек товаров, названий и веса с сайта**..."
        )

        with st.spinner("Собираем карточки подарков и упаковки в высоком качестве..."):
            products = scan_products_fallback(domain)

        st.markdown("---")

        if products:
            st.success(f"Обработано карточек товаров с фото: **{len(products)}**")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, prod in enumerate(products, start=1):
                    safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                    weight_str = f"_{prod['weight']}" if prod["weight"] else ""
                    filename = f"{idx:02d}_{safe_name}{weight_str}.{prod['ext']}"
                    zf.writestr(filename, prod["img_bytes"])

            st.download_button(
                "📥 СКАЧАТЬ ВСЕ ФОТО ПОДАРКОВ (ZIP-АРХИВ)",
                data=zip_buffer.getvalue(),
                file_name=f"{domain}_gifts.zip",
                mime="application/zip",
            )

            st.markdown("---")

            cols = st.columns(4)
            for idx, prod in enumerate(products):
                with cols[idx % 4]:
                    st.markdown(
                        f"""
                        <div class="product-card">
                            <div class="product-title">{prod['title']}</div>
                            {f'<span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.image(prod["img_bytes"], use_container_width=True)
        else:
            st.error(
                "На сайте не удалось выгрузить файлы или карточки товаров."
            )

    # Резервные кнопки быстрых переходов
    st.markdown("---")
    st.write("### 🔍 Быстрый доступ к поисковикам:")
    c1, c2, c3 = st.columns(3)
    clean_q = urllib.parse.quote(f'"{domain}" новогодние подарки каталог {TARGET_YEAR}')
    with c1:
        st.link_button(
            "📕 PDF в Google",
            f"https://www.google.com/search?q={clean_q}+filetype:pdf",
        )
    with c2:
        st.link_button(
            "📊 Прайсы в Яндекс",
            f"https://yandex.ru/search/?text={clean_q}+прайс+xls",
        )
    with c3:
        st.link_button(
            "📱 Группы в VK",
            f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={clean_q}",
        )

st.divider()
st.caption(f"Поиск оптимизирован под сезон {TARGET_YEAR}. Сначала ищутся файлы.")
