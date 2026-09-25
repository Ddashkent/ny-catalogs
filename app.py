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
# НАСТРОЙКИ ПРИЛОЖЕНИЯ И ДИЗАЙН
# -----------------------------

st.set_page_config(
    page_title="Навигатор Подарков 2026",
    page_icon="🎄",
    layout="wide",
)

TARGET_YEAR = 2026

# Праздничный CSS (Зимний фон, Glassmorphism, Красивые кнопки)
st.markdown(
    """
    <style>
    /* Зимний морозный фон */
    .stApp { 
        background: linear-gradient(135deg, #f0f4f8 0%, #e0f2fe 100%);
    }
    
    /* Эффект стекла для карточек с документами */
    .doc-card {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(10px);
        border-left: 6px solid #d32f2f;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 15px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.05);
        transition: transform 0.2s ease;
    }
    .doc-card:hover {
        transform: translateY(-3px);
    }
    
    /* Кнопки документов (Новогодний красный) */
    .btn-doc {
        background-color: #d32f2f;
        color: white !important;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        margin-top: 10px;
        box-shadow: 0 4px 10px rgba(211, 47, 47, 0.3);
        transition: 0.3s;
    }
    .btn-doc:hover { background-color: #b71c1c; transform: scale(1.02); }
    
    /* Карточки товаров (Эффект стекла) */
    .product-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 16px;
        padding: 15px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 8px 25px rgba(0,0,0,0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .product-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 30px rgba(0,0,0,0.08);
        border: 1px solid #90caf9;
    }
    
    /* Плашка веса (Еловый зеленый) */
    .badge-weight {
        background: linear-gradient(45deg, #2e7d32, #43a047);
        color: white;
        font-weight: bold;
        padding: 4px 12px;
        font-size: 13px;
        border-radius: 20px;
        display: inline-block;
        margin-top: 8px;
        box-shadow: 0 2px 5px rgba(46, 125, 50, 0.4);
    }
    
    .product-title {
        font-weight: 800;
        font-size: 14px;
        color: #1e293b;
        margin: 10px 0;
        line-height: 1.4;
    }
    
    /* Стилизация заголовков */
    h1 { color: #1e3a8a !important; font-weight: 900 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Запускаем новогодний снег!
st.snow()

st.title(f"🎄 Универсальный Навигатор Подарков {TARGET_YEAR}")
st.write(
    "**Инструмент менеджера:** Приоритетный поиск официальных PDF/Excel. Если их нет — автоматический сбор всех карточек товаров."
)

# -----------------------------
# ЛОГИКА И ПАРСЕРЫ (Ваш рабочий код)
# -----------------------------

JUNK_WORDS = [
    "политика", "персональных", "согласие", "cookies", 
    "вакансии", "акции", "stock", "finance",
]
CATALOG_WORDS = [
    "новогод", "подар", "набор", "упаков", "каталог", 
    "продукц", "сладк", "конфет", "gift", "catalog", 
    "product", "фасовк", "page", "pagen", "p=",
]
JUNK_DOMAINS = [
    "wikipedia.org", "otzovik", "avito", "checko", "list-org", 
    "synapse", "hh.ru", "rabota", "vk.com", "youtube", 
    "instagram", "facebook", "google", "yandex", "duckduckgo", 
    "bing", "kartoteka", "audit-it", "e-disclosure", 
    "krasotaimedicina", "pravo",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

WEIGHT_REGEX = re.compile(
    r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE
)


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.lower().replace("www.", "")


def extract_valid_domain(url: str) -> str:
    if not url or not url.startswith("http"):
        return None
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")

    if any(bad in netloc for bad in JUNK_DOMAINS):
        return None
    if len(netloc) < 3 or "." not in netloc:
        return None
    return netloc


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=7)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


def find_official_site_dynamic(company_name: str) -> str:
    query = f'"{company_name}" подарки упаковка конфеты фасовка официальный сайт'

    if HAS_DDGS:
        try:
            with DDGS() as ddgs:
                res = list(ddgs.text(query, region="ru-ru", max_results=6))
                for r in res:
                    domain = extract_valid_domain(r.get("href", ""))
                    if domain: return domain
        except Exception:
            pass

    try:
        html_url = "https://html.duckduckgo.com/html/"
        resp = requests.post(html_url, data={"q": query}, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                href = a.get("href", "")
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                target = parsed_qs.get("uddg", [href])[0]
                domain = extract_valid_domain(target)
                if domain: return domain
    except Exception:
        pass

    return None


def scan_for_documents_only(domain: str):
    docs = []
    seen = set()

    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    scan_urls = [final_url] if final_url else []

    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text().strip()
            full_url = urllib.parse.urljoin(final_url, href)

            if any(ext in href.lower() for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                if not any(bad in text.lower() for bad in JUNK_WORDS):
                    if full_url not in seen:
                        seen.add(full_url)
                        docs.append({"title": text or "Скачать каталог / прайс", "link": full_url})

            elif domain in full_url and any(cw in text.lower() or cw in href.lower() for cw in CATALOG_WORDS):
                if full_url not in scan_urls and len(scan_urls) < 12:
                    scan_urls.append(full_url)

    for page in scan_urls[1:]:
        p_url, p_html = get_html(page)
        if p_html:
            p_soup = BeautifulSoup(p_html, "html.parser")
            for a in p_soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text().strip()
                full_url = urllib.parse.urljoin(p_url, href)

                if any(ext in href.lower() for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        if full_url not in seen:
                            seen.add(full_url)
                            docs.append({"title": text or "Скачать каталог / прайс", "link": full_url})

    return docs


def get_high_res_url(img_url: str) -> str:
    img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)
    return img_url


def download_product_image(img_url: str):
    try:
        img_url = get_high_res_url(img_url)
        res = requests.get(img_url, headers=HEADERS, timeout=6)
        if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""):
            data = res.content
            if len(data) < 2500: return None

            if HAS_PIL:
                img = Image.open(io.BytesIO(data))
                w, h = img.size
                if w < 100 or h < 100: return None
                ratio = w / h
                if ratio > 4.0 or ratio < 0.25: return None
                ext = (img.format or "JPEG").lower().replace("jpeg", "jpg")
            else:
                ext = "jpg"

            return {"bytes": data, "ext": ext}
    except Exception:
        pass
    return None


def parse_page_for_products(page_url):
    final_url, html = get_html(page_url)
    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    products = []

    containers = soup.find_all(
        lambda tag: tag.name in ["div", "li", "article"]
        and tag.get("class")
        and any(c in " ".join(tag.get("class")).lower() for c in ["product", "catalog-item", "card", "goods-item", "item", "element", "box"])
    )

    for card in containers:
        img_tag = card.find("img")
        if not img_tag: continue
        src = img_tag.get("data-src") or img_tag.get("data-original") or img_tag.get("data-lazy-src") or img_tag.get("src")
        if not src: continue

        full_img = urllib.parse.urljoin(final_url, src)
        card_text = card.get_text(" ", strip=True)

        weight_match = WEIGHT_REGEX.search(card_text)
        weight = weight_match.group(1) if weight_match else None

        title_tag = card.find(["h2", "h3", "h4", "a", "div"], class_=re.compile(r"title|name|heading|product|caption", re.I))
        title = title_tag.get_text(" ", strip=True) if title_tag else (img_tag.get("alt") or card_text[:60])
        title = re.sub(r"\s+", " ", title).strip()

        if len(title) > 2 and not any(bad in title.lower() for bad in JUNK_WORDS):
            products.append({"title": title, "weight": weight, "img_url": full_img})

    return products


def scan_products_fallback(domain):
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    if not html: return []

    soup = BeautifulSoup(html, "html.parser")
    pages = [final_url]
    seen_pages = {final_url}

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        full = urllib.parse.urljoin(final_url, href)

        if domain in full and any(cw in text or cw in href.lower() for cw in CATALOG_WORDS):
            if full not in seen_pages:
                seen_pages.add(full)
                pages.append(full)
        if len(pages) >= 20: break

    raw_products = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(parse_page_for_products, pages)
        for res in results: raw_products.extend(res)

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
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        res = executor.map(fetch_img, unique_prods)
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
        "Введите название ЛЮБОЙ компании:",
        placeholder="Например: Академия Шоколада, Конфетный Двор, Фабрика Упаковки...",
    )
    if company_input.strip():
        if "." in company_input and " " not in company_input:
            domain = normalize_domain(company_input)
        else:
            with st.spinner(f"Ищу официальный сайт для '{company_input.strip()}'..."):
                domain = find_official_site_dynamic(company_input.strip())
else:
    site_input = st.text_input(
        "Введите адрес сайта напрямую:",
        placeholder="Например: rubin-2000.ru, lakond.ru...",
    )
    if site_input.strip():
        domain = normalize_domain(site_input)

if st.button("🚀 ЗАПУСТИТЬ ПОИСК КАТАЛОГА", type="primary", use_container_width=True):
    if not domain:
        st.error("Не удалось определить сайт. Переключите режим на '🌐 Прямой ввод' и укажите его вручную.")
        st.stop()

    st.success(f"🌐 Подключено к официальному сайту: `{domain}`")

    # ==========================================
    # ШАГ 1: ПОИСК ФАЙЛОВ КАТАЛОГОВ
    # ==========================================
    with st.spinner("Проверяю сайт на наличие готовых PDF / Excel прайсов..."):
        documents = scan_for_documents_only(domain)

    if documents:
        st.markdown("---")
        st.success(f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**")
        st.info("💡 Поиск картинок отменен, так как найден официальный файл.")

        for doc in documents:
            icon = "📕 PDF" if ".pdf" in doc["link"].lower() else "📊 EXCEL/DOC"
            st.markdown(
                f"""
                <div class="doc-card">
                    <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                    <p style="font-size:13px; color:#64748b; margin:6px 0;">Ссылка: {doc['link']}</p>
                    <a href="{doc['link']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                </div>
                """,
                unsafe_allow_html=True,
            )

    else:
        # ==========================================
        # ШАГ 2: СБОР КАРТОЧЕК С САЙТА (БЕЗ ЛИМИТОВ)
        # ==========================================
        st.warning("⚠️ **Готовые файлы PDF/Excel не найдены.** Переходим к сбору визуальных карточек...")

        with st.spinner("Собираем ВСЕ карточки подарков с фотографиями и весом..."):
            products = scan_products_fallback(domain)

        st.markdown("---")

        if products:
            st.success(f"Успешно обработано карточек товаров: **{len(products)} шт.**")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, prod in enumerate(products, start=1):
                    safe_name = re.sub(r"[^\w\s-]", "", prod["title"])[:30]
                    weight_str = f"_{prod['weight']}" if prod["weight"] else ""
                    filename = f"{idx:02d}_{safe_name}{weight_str}.{prod['ext']}"
                    zf.writestr(filename, prod["img_bytes"])

            st.download_button(
                f"📦 СКАЧАТЬ ВСЕ {len(products)} ФОТО ПОДАРКОВ (ZIP-АРХИВ)",
                data=zip_buffer.getvalue(),
                file_name=f"{domain}_all_gifts.zip",
                mime="application/zip",
                type="primary"
            )

            st.markdown("---")

            # Сетка товаров (4 в ряд)
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
            st.error("На сайте не удалось выгрузить ни файлы, ни карточки товаров.")

    # Резервные снайперские кнопки
    st.markdown("---")
    st.write("### 🔍 Резервный поиск в поисковиках:")
    c1, c2, c3 = st.columns(3)
    clean_q = urllib.parse.quote(f'"{domain}" новогодние подарки каталог {TARGET_YEAR}')
    with c1: st.link_button("📕 PDF в Google", f"https://www.google.com/search?q={clean_q}+filetype:pdf")
    with c2: st.link_button("📊 Прайсы в Яндекс", f"https://yandex.ru/search/?text={clean_q}+прайс+xls")
    with c3: st.link_button("📱 Группы в VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={clean_q}")

st.divider()
st.caption(f"Универсальный инструмент коммерческого отдела. Оптимизирован под сезон {TARGET_YEAR}.")
