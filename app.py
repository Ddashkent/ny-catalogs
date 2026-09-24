import io
import re
import zipfile
import urllib.parse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from PIL import Image


# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Визуальный Экстрактор Подарков",
    page_icon="🖼️",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f7f8fa;
    }

    .catalog-card {
        background-color: #ffffff;
        border-left: 6px solid #e91e63;
        padding: 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        box-shadow: 0 2px 7px rgba(0,0,0,0.06);
    }

    .source-card {
        background-color: #ffffff;
        border-left: 5px solid #1976d2;
        padding: 13px;
        border-radius: 9px;
        margin-bottom: 10px;
    }

    .image-caption {
        font-size: 12px;
        color: #666666;
        margin-top: 5px;
        word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"🖼️ Визуальный Экстрактор Новогодних Подарков {TARGET_YEAR}")
st.caption(
    "Поиск официального сайта, каталогов, карточек подарков и изображений упаковки."
)


# -----------------------------
# ФИЛЬТРЫ
# -----------------------------

JUNK_WORDS = [
    "политика",
    "конфиденциаль",
    "персональн",
    "согласие",
    "соглашение",
    "cookies",
    "cookie",
    "обработк",
    "ваканс",
    "инвестор",
    "акции",
    "stock",
    "finance",
    "медицина",
    "врач",
    "хоккей",
    "hockey",
    "рейтинг",
    "отзывы",
    "реклама",
]

JUNK_DOMAINS = [
    "wikipedia.org",
    "otzovik",
    "avito",
    "checko",
    "list-org",
    "audit-it",
    "synapsenet",
    "hh.ru",
    "rabota.ru",
    "pravo",
    "pravoved",
    "consultant",
    "garant",
    "krasotaimedicina",
    "espn",
    "365scores",
    "youtube",
]

# Страницы, на которых вероятнее всего лежат нужные товары
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
    "podarki",
    "new-year",
    "newyear",
    "horse",
    "лошад",
]

# Признаки технических картинок: их не надо брать в каталог
BAD_IMAGE_WORDS = [
    "logo",
    "icon",
    "sprite",
    "social",
    "facebook",
    "instagram",
    "telegram",
    "youtube",
    "vk.",
    "vkontakte",
    "favicon",
    "loader",
    "loading",
    "banner",
    "background",
    "header",
    "footer",
    "arrow",
    "search",
    "close",
    "menu",
    "placeholder",
    "spacer",
    "pixel",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# -----------------------------
# БАЗОВЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    """Возвращает чистый домен без http, https, www и путей."""
    value = value.strip()

    if not value.startswith("http"):
        value = "https://" + value

    parsed = urllib.parse.urlparse(value)
    domain = parsed.netloc.lower().replace("www.", "")

    return domain


def make_site_url(domain: str) -> str:
    """Создает стартовый URL сайта."""
    return f"https://{domain}"


def is_junk_text(text: str) -> bool:
    text = text.lower()
    return any(word in text for word in JUNK_WORDS)


def has_catalog_words(text: str) -> bool:
    text = text.lower()
    return any(word in text for word in CATALOG_WORDS)


def is_junk_domain(url: str) -> bool:
    url_low = url.lower()
    return any(domain in url_low for domain in JUNK_DOMAINS)


def same_domain(url: str, domain: str) -> bool:
    """Проверяет, принадлежит ли ссылка текущему сайту."""
    parsed = urllib.parse.urlparse(url)
    link_domain = parsed.netloc.lower().replace("www.", "")
    domain = domain.lower().replace("www.", "")
    return link_domain == domain or link_domain.endswith("." + domain)


def get_html(url: str):
    """Безопасно получает HTML сайта."""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=12,
            allow_redirects=True,
        )

        if response.status_code == 200:
            return response.url, response.text

    except requests.RequestException:
        return None, None

    return None, None


# -----------------------------
# ПОИСК ОФИЦИАЛЬНОГО САЙТА
# -----------------------------

def find_official_site(company_name: str):
    """
    Ищет официальный сайт компании.
    Если пользователь ввел домен — используем его сразу.
    """

    possible_domain = company_name.strip()

    if "." in possible_domain and " " not in possible_domain:
        return normalize_domain(possible_domain)

    try:
        with DDGS() as ddgs:
            search_query = (
                f'"{company_name}" '
                f'кондитерская фабрика подарки упаковка официальный сайт '
                f'-отзывы -вакансии -медицина -хоккей -финансы'
            )

            results = list(
                ddgs.text(
                    search_query,
                    region="ru-ru",
                    max_results=8,
                )
            )

            for item in results:
                link = item.get("href", "")

                if not link:
                    continue

                if is_junk_domain(link):
                    continue

                title = item.get("title", "")
                snippet = item.get("body", "")
                all_text = f"{title} {snippet} {link}".lower()

                if is_junk_text(all_text):
                    continue

                domain = normalize_domain(link)

                if domain:
                    return domain

    except Exception:
        return None

    return None


# -----------------------------
# ПОИСК СТРАНИЦ КАТАЛОГА
# -----------------------------

def find_catalog_pages(domain: str, max_pages: int = 20):
    """
    Ищет на сайте страницы вида:
    /podarki/
    /catalog/
    /novogodnie-podarki/
    /produkciya/
    /upakovka/
    и т.п.
    """

    root_url = make_site_url(domain)
    final_url, html = get_html(root_url)

    if not html:
        # Иногда сайт доступен только по HTTP
        root_url = f"http://{domain}"
        final_url, html = get_html(root_url)

    if not html:
        return [], None

    soup = BeautifulSoup(html, "html.parser")

    found_pages = []
    checked = set()

    # Главную страницу также добавляем: иногда каталог расположен прямо на ней
    found_pages.append(final_url)
    checked.add(final_url)

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True)

        if not href:
            continue

        full_url = urllib.parse.urljoin(final_url, href)

        if not full_url.startswith("http"):
            continue

        if not same_domain(full_url, domain):
            continue

        link_context = f"{href} {text}".lower()

        if is_junk_text(link_context):
            continue

        if has_catalog_words(link_context):
            clean_url = full_url.split("#")[0]

            if clean_url not in checked:
                found_pages.append(clean_url)
                checked.add(clean_url)

        if len(found_pages) >= max_pages:
            break

    return found_pages[:max_pages], final_url


def expand_catalog_pages(domain: str, initial_pages: list, max_pages: int = 25):
    """
    Дополнительно обходит каталоговые страницы первого уровня.
    Нужен, если на главной странице есть только пункт «Каталог»,
    а реальные подарки лежат внутри подразделов.
    """

    result_pages = list(initial_pages)
    checked = set(initial_pages)

    for page_url in initial_pages[:10]:
        final_url, html = get_html(page_url)

        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            text = a.get_text(" ", strip=True)

            full_url = urllib.parse.urljoin(final_url, href)

            if not same_domain(full_url, domain):
                continue

            context = f"{href} {text}".lower()

            if is_junk_text(context):
                continue

            if has_catalog_words(context):
                clean_url = full_url.split("#")[0]

                if clean_url not in checked:
                    checked.add(clean_url)
                    result_pages.append(clean_url)

            if len(result_pages) >= max_pages:
                return result_pages[:max_pages]

    return result_pages[:max_pages]


# -----------------------------
# ДОКУМЕНТЫ: PDF / XLS / XLSX
# -----------------------------

def extract_documents(page_url: str):
    docs = []

    final_url, html = get_html(page_url)

    if not html:
        return docs

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True)

        if not href:
            continue

        lower_href = href.lower()
        context = f"{text} {href}".lower()

        if is_junk_text(context):
            continue

        is_file = any(
            lower_href.endswith(ext)
            or f"{ext}?" in lower_href
            for ext in [".pdf", ".xls", ".xlsx", ".doc", ".docx"]
        )

        if not is_file:
            continue

        full_link = urllib.parse.urljoin(final_url, href)

        docs.append(
            {
                "title": text or "Скачать документ",
                "link": full_link,
                "source_page": final_url,
            }
        )

    return docs


# -----------------------------
# ИЗОБРАЖЕНИЯ ТОВАРОВ
# -----------------------------

def get_image_url(img_tag, page_url: str):
    """
    Берет картинку в том числе с lazy-load атрибутов:
    data-src, data-original, data-lazy-src, srcset.
    """

    candidates = [
        img_tag.get("data-src"),
        img_tag.get("data-original"),
        img_tag.get("data-lazy-src"),
        img_tag.get("data-image"),
        img_tag.get("src"),
    ]

    for src in candidates:
        if src and src.strip():
            return urllib.parse.urljoin(page_url, src.strip())

    srcset = img_tag.get("srcset")

    if srcset:
        first_src = srcset.split(",")[0].strip().split(" ")[0]
        if first_src:
            return urllib.parse.urljoin(page_url, first_src)

    return None


def is_good_image_candidate(img_tag, image_url: str, page_context: str):
    """
    Отсекает лого, иконки, баннеры и технические изображения.
    Оставляет товарные изображения на страницах каталога.
    """

    url_low = image_url.lower()

    if any(word in url_low for word in BAD_IMAGE_WORDS):
        return False

    alt = img_tag.get("alt", "")
    title = img_tag.get("title", "")
    class_name = " ".join(img_tag.get("class", []))

    context = f"{url_low} {alt} {title} {class_name} {page_context}".lower()

    if is_junk_text(context):
        return False

    # Если картинка расположена в блоке товара / подарка / упаковки,
    # считаем ее релевантной.
    parent_text = ""

    current = img_tag

    for _ in range(5):
        if current.parent is None:
            break

        current = current.parent

        parent_class = " ".join(current.get("class", []))
        parent_id = current.get("id", "")
        parent_text += f" {parent_class} {parent_id}"

    product_context = f"{context} {parent_text}".lower()

    strong_product_words = [
        "product",
        "product-card",
        "product-item",
        "catalog",
        "item",
        "товар",
        "подар",
        "набор",
        "упаков",
        "конфет",
        "сладк",
        "новогод",
    ]

    # Если страница каталоговая, допускаем картинку,
    # но все равно отсекаем технические изображения.
    if has_catalog_words(page_context):
        return True

    return any(word in product_context for word in strong_product_words)


def download_image(image_url: str):
    """
    Скачивает картинку, проверяет, что это реальное изображение,
    отсекает очень маленькие и слишком широкие баннеры.
    """

    try:
        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=10,
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get("Content-Type", "").lower()

        if "image" not in content_type:
            return None

        image_data = response.content

        if len(image_data) < 4000:
            return None

        image = Image.open(io.BytesIO(image_data))
        width, height = image.size

        # Иконки и мелкие картинки
        if width < 180 or height < 180:
            return None

        # Очень широкие/узкие баннеры
        ratio = width / height

        if ratio > 3.5 or ratio < 0.28:
            return None

        image_format = (image.format or "JPEG").lower()

        if image_format == "jpeg":
            extension = "jpg"
        elif image_format in ["png", "webp", "gif"]:
            extension = image_format
        else:
            extension = "jpg"

        return {
            "bytes": image_data,
            "width": width,
            "height": height,
            "extension": extension,
        }

    except Exception:
        return None


def extract_product_images(page_url: str, max_images_per_page: int = 20):
    """
    Собирает именно изображения продукции с одной страницы каталога.
    """

    final_url, html = get_html(page_url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""

    page_context = f"{final_url} {page_title} {h1_text}"

    images = []
    processed = set()

    for img_tag in soup.find_all("img"):
        image_url = get_image_url(img_tag, final_url)

        if not image_url:
            continue

        if image_url in processed:
            continue

        processed.add(image_url)

        if not is_good_image_candidate(img_tag, image_url, page_context):
            continue

        downloaded = download_image(image_url)

        if not downloaded:
            continue

        alt = img_tag.get("alt", "").strip()

        images.append(
            {
                "image_url": image_url,
                "bytes": downloaded["bytes"],
                "extension": downloaded["extension"],
                "width": downloaded["width"],
                "height": downloaded["height"],
                "alt": alt or "Изображение подарка / упаковки",
                "source_page": final_url,
            }
        )

        if len(images) >= max_images_per_page:
            break

    return images


# -----------------------------
# ZIP-АРХИВ ИЗОБРАЖЕНИЙ
# -----------------------------

def make_images_zip(images: list):
    """Формирует ZIP-архив из найденных товарных картинок."""

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for index, item in enumerate(images, start=1):
            file_name = f"gift_{index:03d}.{item['extension']}"
            zip_file.writestr(file_name, item["bytes"])

    zip_buffer.seek(0)

    return zip_buffer.getvalue()


# -----------------------------
# ОСНОВНОЙ ИНТЕРФЕЙС
# -----------------------------

company_query = st.text_input(
    "Введите название компании, фабрики или бренда:",
    placeholder="Например: Рубин, Лаконд, Баян Сулу, Акконд...",
)

if st.button("🚀 НАЙТИ КАТАЛОГИ И ИЗОБРАЖЕНИЯ", type="primary"):
    if not company_query.strip():
        st.warning("Введите название компании.")
        st.stop()

    company_name = company_query.strip()

    with st.spinner("Определяю официальный сайт компании..."):
        domain = find_official_site(company_name)

    if not domain:
        st.error(
            "Официальный сайт определить не удалось. "
            "Попробуйте написать название подробнее: например, «Баян Сулу Казахстан»."
        )
        st.stop()

    st.success(f"🌐 Найден официальный сайт: `{domain}`")

    with st.spinner("Ищу страницы с каталогами, подарками и упаковкой..."):
        pages, main_page = find_catalog_pages(domain)
        catalog_pages = expand_catalog_pages(domain, pages)

    st.write(f"Найдено потенциальных каталоговых страниц: **{len(catalog_pages)}**")

    all_docs = []
    all_images = []

    progress = st.progress(0)
    status = st.empty()

    for index, page_url in enumerate(catalog_pages):
        status.write(
            f"Проверяю страницу {index + 1} из {len(catalog_pages)}: `{page_url}`"
        )

        all_docs.extend(extract_documents(page_url))
        all_images.extend(extract_product_images(page_url))

        progress.progress((index + 1) / len(catalog_pages))

    status.empty()
    progress.empty()

    # Убираем повторы документов
    unique_docs_dict = {}
    for doc in all_docs:
        unique_docs_dict[doc["link"]] = doc

    unique_docs = list(unique_docs_dict.values())

    # Убираем повторы изображений
    unique_images_dict = {}
    for image in all_images:
        unique_images_dict[image["image_url"]] = image

    unique_images = list(unique_images_dict.values())

    tab1, tab2, tab3 = st.tabs(
        [
            "📄 Каталоги и прайсы",
            "🖼️ Подарки и упаковка",
            "🌐 Найденные страницы",
        ]
    )

    # -------------------------
    # ВКЛАДКА: ДОКУМЕНТЫ
    # -------------------------
    with tab1:
        if unique_docs:
            st.success(f"Найдено файлов: {len(unique_docs)}")

            for doc in unique_docs:
                st.markdown(
                    f"""
                    <div class="catalog-card">
                        <b>📄 {doc['title']}</b><br>
                        <small>Найдено на странице: {doc['source_page']}</small><br><br>
                        <a href="{doc['link']}" target="_blank">
                            📥 Скачать / открыть файл
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.warning(
                "На найденных страницах нет открытых PDF, Excel или Word-файлов."
            )

    # -------------------------
    # ВКЛАДКА: ИЗОБРАЖЕНИЯ
    # -------------------------
    with tab2:
        if unique_images:
            st.success(
                f"Найдено изображений подарков и упаковки: {len(unique_images)}"
            )

            zip_data = make_images_zip(unique_images)

            st.download_button(
                label="📥 Скачать все изображения подарков и упаковки ZIP-архивом",
                data=zip_data,
                file_name=f"{company_name}_gifts_and_packaging.zip",
                mime="application/zip",
            )

            st.markdown("---")

            columns = st.columns(4)

            for index, image in enumerate(unique_images):
                with columns[index % 4]:
                    st.image(
                        image["bytes"],
                        use_container_width=True,
                    )

                    st.caption(image["alt"])

                    st.markdown(
                        f"""
                        <div class="image-caption">
                            <b>Страница:</b><br>
                            <a href="{image['source_page']}" target="_blank">
                                Открыть источник
                            </a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.warning(
                "Товарные изображения на каталоговых страницах автоматически не найдены."
            )
            st.info(
                "Это может означать, что сайт загружает изображения через JavaScript, "
                "или каталог доступен только после входа/запроса менеджеру."
            )

    # -------------------------
    # ВКЛАДКА: СТРАНИЦЫ
    # -------------------------
    with tab3:
        st.write(
            "Ниже страницы, которые приложение признало связанными с подарками, "
            "упаковкой или каталогом."
        )

        for page in catalog_pages:
            st.markdown(
                f"""
                <div class="source-card">
                    <a href="{page}" target="_blank">🌐 {page}</a>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()

st.caption(
    "Инструмент собирает изображения с каталоговых страниц: подарки, наборы, упаковку "
    "и карточки товаров. Логотипы, баннеры, иконки и юридические документы отфильтровываются."
)
