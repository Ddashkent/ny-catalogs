import io
import urllib.parse
import zipfile
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
    .stApp { background-color: #f8f9fa; }
    .catalog-card {
        background-color: #ffffff; border-left: 6px solid #28a745;
        padding: 16px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 2px 7px rgba(0,0,0,0.06);
    }
    .source-card {
        background-color: #ffffff; border-left: 5px solid #007bff;
        padding: 12px; border-radius: 8px; margin-bottom: 8px;
    }
    .image-caption {
        font-size: 12px; color: #666666; margin-top: 5px; word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"🖼️ Визуальный Экстрактор Подарков {TARGET_YEAR}")
st.caption(
    "Автоматический сбор каталогов, прайсов и картинок упаковки с официальных сайтов."
)

# -----------------------------
# БАЗА ЗНАНИЙ (Мгновенный выбор)
# -----------------------------

KNOWLEDGE_BASE = {
    "рубин": "rubin-2000.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "лоте рахат": "rakhat.kz",
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

# Домены-поисковики и мусорные справочники (ЗАБЛОКИРОВАНЫ!)
SEARCH_ENGINE_DOMAINS = [
    "bing.com",
    "duckduckgo.com",
    "google.com",
    "google.ru",
    "yandex.ru",
    "yandex.com",
    "yahoo.com",
    "wikipedia.org",
    "otzovik.com",
    "avito.ru",
    "checko.ru",
    "list-org.com",
    "audit-it.ru",
    "synapsenet.ru",
    "hh.ru",
    "rabota.ru",
    "pravo.ru",
    "pravoved.ru",
    "krasotaimedicina.ru",
]

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
    "podarki",
]

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
    "favicon",
    "loader",
    "banner",
    "background",
    "header",
    "footer",
    "spacer",
    "pixel",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def unwrap_url(url: str) -> str:
    """Разворачивает редиректные ссылки от Bing/DuckDuckGo"""
    parsed = urllib.parse.urlparse(url)
    if any(se in parsed.netloc for se in ["bing.com", "duckduckgo.com"]):
        qs = urllib.parse.parse_qs(parsed.query)
        for param in ["u", "uddg", "url", "target"]:
            if param in qs and qs[param]:
                target = qs[param][0]
                if target.startswith("http"):
                    return target
    return url


def normalize_domain(value: str) -> str:
    """Вытягивает чистый домен сайта"""
    value = unwrap_url(value).strip()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    domain = parsed.netloc.lower().replace("www.", "")
    return domain


def same_domain(url: str, domain: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    link_domain = parsed.netloc.lower().replace("www.", "")
    domain = domain.lower().replace("www.", "")
    return link_domain == domain or link_domain.endswith("." + domain)


def is_junk_domain(domain: str) -> bool:
    domain_low = domain.lower()
    return any(bad in domain_low for bad in SEARCH_ENGINE_DOMAINS)


def is_junk_text(text: str) -> bool:
    text_low = text.lower()
    return any(word in text_low for word in JUNK_WORDS)


def has_catalog_words(text: str) -> bool:
    text_low = text.lower()
    return any(word in text_low for word in CATALOG_WORDS)


def get_html(url: str):
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=10, allow_redirects=True
        )
        if response.status_code == 200:
            return response.url, response.text
    except Exception:
        pass
    return None, None


# -----------------------------
# ПОИСК ОФИЦИАЛЬНОГО САЙТА
# -----------------------------


def find_official_site(company_name: str):
    q_low = company_name.lower().strip()

    # 1. Проверка по Базе Знаний
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]

    for key, dom in KNOWLEDGE_BASE.items():
        if key in q_low or q_low in key:
            return dom

    # 2. Динамический поиск через DDGS
    try:
        with DDGS() as ddgs:
            q = f'"{company_name}" кондитерская фабрика упаковка подарки официальный сайт -wiki -отзывы'
            results = list(ddgs.text(q, region="ru-ru", max_results=8))

            for item in results:
                raw_link = item.get("href", "")
                if not raw_link:
                    continue

                clean_link = unwrap_url(raw_link)
                domain = normalize_domain(clean_link)

                if domain and not is_junk_domain(domain):
                    return domain
    except Exception:
        pass

    return None


# -----------------------------
# ОБХОД КАТАЛОЖНЫХ СТРАНИЦ
# -----------------------------


def find_catalog_pages(domain: str, max_pages: int = 20):
    root_url = f"https://{domain}"
    final_url, html = get_html(root_url)

    if not html:
        root_url = f"http://{domain}"
        final_url, html = get_html(root_url)

    if not html:
        return [], None

    soup = BeautifulSoup(html, "html.parser")
    found_pages = []
    checked = set()

    found_pages.append(final_url)
    checked.add(final_url)

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = a.get_text(" ", strip=True)

        if not href:
            continue

        full_url = urllib.parse.urljoin(final_url, href)
        if not full_url.startswith("http") or not same_domain(full_url, domain):
            continue

        context = f"{href} {text}".lower()
        if is_junk_text(context):
            continue

        if has_catalog_words(context):
            clean_url = full_url.split("#")[0]
            if clean_url not in checked:
                found_pages.append(clean_url)
                checked.add(clean_url)

        if len(found_pages) >= max_pages:
            break

    return found_pages[:max_pages], final_url


# -----------------------------
# ИЗВЛЕЧЕНИЕ ФАЙЛОВ И ИЗОБРАЖЕНИЙ
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

        if any(
            lower_href.endswith(ext) or f"{ext}?" in lower_href
            for ext in [".pdf", ".xls", ".xlsx", ".doc", ".docx"]
        ):
            full_link = urllib.parse.urljoin(final_url, href)
            docs.append(
                {
                    "title": text or "Скачать каталог / прайс",
                    "link": full_link,
                    "source_page": final_url,
                }
            )

    return docs


def download_image(image_url: str):
    try:
        response = requests.get(image_url, headers=HEADERS, timeout=8)
        if response.status_code != 200:
            return None

        content_type = response.headers.get("Content-Type", "").lower()
        if "image" not in content_type:
            return None

        image_data = response.content
        if len(image_data) < 4000:  # Пропускаем мелкие картинки
            return None

        image = Image.open(io.BytesIO(image_data))
        width, height = image.size

        # Отсекаем иконки и крайние баннеры
        if width < 180 or height < 180:
            return None
        ratio = width / height
        if ratio > 3.5 or ratio < 0.28:
            return None

        ext = (image.format or "JPEG").lower()
        ext = "jpg" if ext == "jpeg" else ext

        return {
            "bytes": image_data,
            "ext": ext,
            "width": width,
            "height": height,
        }
    except Exception:
        return None


def extract_product_images(page_url: str, max_images: int = 15):
    images = []
    final_url, html = get_html(page_url)
    if not html:
        return images

    soup = BeautifulSoup(html, "html.parser")
    processed = set()

    for img_tag in soup.find_all("img"):
        src = (
            img_tag.get("data-src")
            or img_tag.get("data-original")
            or img_tag.get("src")
        )
        if not src:
            continue

        image_url = urllib.parse.urljoin(final_url, src.strip())
        if image_url in processed:
            continue
        processed.add(image_url)

        url_low = image_url.lower()
        if any(bad in url_low for bad in BAD_IMAGE_WORDS):
            continue

        downloaded = download_image(image_url)
        if downloaded:
            alt = img_tag.get("alt", "").strip() or "Подарок / Упаковка"
            images.append(
                {
                    "image_url": image_url,
                    "bytes": downloaded["bytes"],
                    "ext": downloaded["ext"],
                    "alt": alt,
                    "source_page": final_url,
                }
            )

        if len(images) >= max_images:
            break

    return images


def make_images_zip(images: list):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(
        zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for idx, item in enumerate(images, start=1):
            zf.writestr(f"gift_{idx:03d}.{item['ext']}", item["bytes"])
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

mode = st.radio(
    "Режим поиска сайта:",
    ["🔍 По названию компании", "🌐 Прямой ввод адреса сайта / домена"],
    horizontal=True,
)

domain = None

if mode == "🔍 По названию компании":
    company_input = st.text_input(
        "Введите название компании или бренда:",
        placeholder="Например: Рубин, Лаконд, Баян Сулу, Акконд...",
    )
    if company_input.strip():
        # Если случайно вбили домен в поле названия — обрабатываем автоматически
        if "." in company_input and " " not in company_input:
            domain = normalize_domain(company_input)
        else:
            with st.spinner("Определяю сайт фабрики..."):
                domain = find_official_site(company_input.strip())
else:
    site_input = st.text_input(
        "Введите домен или URL сайта компании напрямую:",
        placeholder="Например: rubin-2000.ru, lakond.ru, https://bayansulu.kz/",
    )
    if site_input.strip():
        domain = normalize_domain(site_input)

if st.button("🚀 НАЙТИ КАТАЛОГИ И ИЗОБРАЖЕНИЯ", type="primary"):
    if not domain:
        st.error(
            "Не удалось определить сайт. Введите корректное название или укажите домен напрямую во второй вкладке."
        )
        st.stop()

    if is_junk_domain(domain):
        st.error(
            f"Адрес `{domain}` является поисковиком или справочником. Укажите прямой сайт фабрики."
        )
        st.stop()

    st.success(f"🌐 Работаем с сайтом: `{domain}`")

    with st.spinner("Ищу страницы каталогов, подарков и упаковки..."):
        catalog_pages, main_page = find_catalog_pages(domain)

    st.write(
        f"Найдено разделов для сканирования: **{len(catalog_pages)}**"
    )

    all_docs = []
    all_images = []

    progress = st.progress(0)
    status = st.empty()

    for idx, page_url in enumerate(catalog_pages):
        status.write(
            f"Сканирую страницу {idx + 1} из {len(catalog_pages)}: `{page_url}`"
        )
        all_docs.extend(extract_documents(page_url))
        all_images.extend(extract_product_images(page_url))
        progress.progress((idx + 1) / len(catalog_pages))

    status.empty()
    progress.empty()

    # Убираем дубли
    unique_docs = list({d["link"]: d for d in all_docs}.values())
    unique_images = list({i["image_url"]: i for i in all_images}.values())

    tab1, tab2, tab3 = st.tabs(
        [
            "📄 Каталоги и прайсы (PDF/XLS)",
            "🖼️ Подарки и упаковка (Фото)",
            "🌐 Сканированные страницы",
        ]
    )

    with tab1:
        if unique_docs:
            st.success(f"Найдено файлов: {len(unique_docs)}")
            for doc in unique_docs:
                st.markdown(
                    f"""
                    <div class="catalog-card">
                        <b>📄 {doc['title']}</b><br>
                        <small>Страница: {doc['source_page']}</small><br><br>
                        <a href="{doc['link']}" target="_blank">📥 Скачать / открыть файл</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.warning("Открытых PDF / Excel файлов на страницах не найдено.")

    with tab2:
        if unique_images:
            st.success(f"Найдено фотографий продукции: {len(unique_images)}")

            zip_bytes = make_images_zip(unique_images)
            st.download_button(
                label="📥 Скачать все фото подарков и упаковки ZIP-архивом",
                data=zip_bytes,
                file_name=f"{domain}_gifts_images.zip",
                mime="application/zip",
            )

            st.markdown("---")
            cols = st.columns(4)
            for idx, img in enumerate(unique_images):
                with cols[idx % 4]:
                    st.image(img["bytes"], use_container_width=True)
                    st.caption(img["alt"])
                    st.markdown(
                        f"<div class='image-caption'><a href='{img['source_page']}' target='_blank'>Источник</a></div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.warning("Изображения товаров на найденных страницах не обнаружены.")

    with tab3:
        for p in catalog_pages:
            st.markdown(
                f"<div class='source-card'><a href='{p}' target='_blank'>🌐 {p}</a></div>",
                unsafe_allow_html=True,
            )

st.divider()
st.caption(
    "Инструмент автоматически блокирует поисковики, юридический и финансовый мусор."
)
