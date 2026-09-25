import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Обязательный Pillow для физической фильтрации баннеров
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА
# -----------------------------

st.set_page_config(
    page_title="Навигатор Каталогов & Упаковки 2026",
    page_icon="🎁",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    .product-box {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: 0.2s;
    }
    .product-box:hover { border-color: #3b82f6; transform: translateY(-3px); }
    .doc-box {
        background-color: #ffffff; border-left: 6px solid #10b981;
        padding: 16px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    }
    .btn-doc {
        background-color: #10b981; color: white !important;
        font-weight: bold; padding: 10px 20px; border-radius: 8px;
        text-decoration: none; display: inline-block; margin-top: 8px;
    }
    .product-title {
        font-weight: 700; font-size: 13px; color: #1e293b;
        margin-top: 8px; min-height: 36px; line-height: 1.3;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title(f"🎁 Навигатор Каталогов & Упаковки {TARGET_YEAR}")
st.caption(
    "Поиск официальных файлов (PDF/Excel) и точный выборка фотографий коробок и подарков (без баннеров и декоров сайта)."
)

# -----------------------------
# БАЗА ЗНАНИЙ
# -----------------------------

KNOWLEDGE_BASE = {
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
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
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "униконф": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
    "красный мозырянин": "mozyrconfectionery.by",
}

JUNK_WORDS = [
    "политика",
    "согласие",
    "соглашение",
    "вакансии",
    "акции",
    "инвесторам",
    "реквизиты",
    "устав",
]
CATALOG_WORDS = [
    "каталог",
    "подарки",
    "упаковка",
    "продукц",
    "catalog",
    "нг",
    "новогод",
    "наборы",
    "коробки",
]
BANNER_KEYWORDS = [
    "banner",
    "slide",
    "slider",
    "bg-",
    "background",
    "header",
    "footer",
    "decor",
    "fon-",
    "hero",
    "main-img",
    "logo",
    "icon",
]

PROBE_PATHS = [
    "",
    "/catalog/",
    "/katalog/",
    "/podarki/",
    "/novogodnie-podarki/",
    "/upakovka/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def encode_safe_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        safe_path = urllib.parse.quote(parsed.path)
        return urllib.parse.urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                safe_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    except Exception:
        return url


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.replace("www.", "")


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=7, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


def find_site_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v
    try:
        query = f'"{company_name}" новогодняя упаковка подарки официальный сайт'
        search_url = (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        )
        res = requests.get(search_url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(
                    urllib.parse.urlparse(a["href"]).query
                ).get("uddg", [a["href"]])[0]
                netloc = (
                    urllib.parse.urlparse(target)
                    .netloc.lower()
                    .replace("www.", "")
                )
                if netloc and not any(
                    bad in netloc
                    for bad in ["wikipedia", "otzovik", "avito", "checko", "vk.com"]
                ):
                    return netloc
    except Exception:
        pass
    return None


def is_real_product_box(img_bytes) -> bool:
    """Физическая проверка: Отсекаем баннеры по пропорциям (ширина/высота)"""
    if not HAS_PIL:
        return True
    try:
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size

        # Отсекаем мелкие значки и иконки
        if w < 180 or h < 180:
            return False

        ratio = w / h
        # КОРОБКИ И ПОДАРКИ имеют пропорции от 0.55 (высокие) до 1.5 (квадратные/чуть широкие)
        # Все баннеры с фоном (как на скрине) имеют ratio > 1.8 или < 0.4.
        if ratio > 1.55 or ratio < 0.55:
            return False  # Это БАННЕР или декор сайта, выкидываем!

        return True
    except Exception:
        return False


def extract_assets(domain: str):
    base_protocol = f"https://{domain}"
    urls_to_check = [base_protocol + p for p in PROBE_PATHS]

    docs, products = [], []
    seen_links = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        pages_data = list(executor.map(get_html, urls_to_check))

        for p_url, p_html in pages_data:
            if not p_html:
                continue
            p_soup = BeautifulSoup(p_html, "html.parser")

            # 1. Поиск PDF / Excel каталогов
            for a in p_soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        if any(
                            good in text.lower() or good in href
                            for good in [
                                "каталог",
                                "прайс",
                                "подарки",
                                "2026",
                                "2025",
                                "price",
                                "catalog",
                            ]
                        ):
                            full_link = urllib.parse.urljoin(p_url, a["href"])
                            if full_link not in seen_links:
                                seen_links.add(full_link)
                                docs.append(
                                    {
                                        "title": text
                                        or "Официальный каталог / прайс-лист",
                                        "url": encode_safe_url(full_link),
                                    }
                                )

            # 2. Извлечение ТОЛЬКО карточек товаров (контейнеры карточек)
            card_containers = p_soup.find_all(
                lambda tag: tag.name in ["div", "li", "article"]
                and tag.get("class")
                and any(
                    c in " ".join(tag.get("class")).lower()
                    for c in [
                        "product",
                        "catalog-item",
                        "card",
                        "goods-item",
                        "item",
                    ]
                )
            )

            # Если явных контейнеров не нашли — берём все картинки с каталожной страницы
            target_elements = (
                card_containers if card_containers else p_soup.find_all("img")
            )

            for elem in target_elements:
                img_tag = elem if elem.name == "img" else elem.find("img")
                if not img_tag:
                    continue

                src = (
                    img_tag.get("data-src")
                    or img_tag.get("data-original")
                    or img_tag.get("src")
                )
                if not src:
                    continue

                full_img_url = urllib.parse.urljoin(p_url, src)
                img_url_low = full_img_url.lower()

                # Жесткий фильтр баннеров и иконок по имени файла
                if any(bad in img_url_low for bad in BANNER_KEYWORDS):
                    continue

                full_img_url = encode_safe_url(full_img_url)

                title = ""
                if elem.name != "img":
                    title = elem.get_text(" ", strip=True)[:100]
                if not title or len(title) < 4:
                    title = (
                        img_tag.get("alt")
                        or img_tag.get("title")
                        or "Подарок / Упаковка"
                    )

                title = re.sub(r"\s+", " ", title).strip()

                if full_img_url not in seen_links and len(title) > 2:
                    if not any(bad in title.lower() for bad in JUNK_WORDS):
                        seen_links.add(full_img_url)
                        products.append({"title": title, "img": full_img_url})

    return docs, products


# -----------------------------
# ВВОД ДАННЫХ И ИНТЕРФЕЙС
# -----------------------------

col_search, col_mode = st.columns([3, 1])

with col_search:
    company_input = st.text_input(
        "Введите название заказчика или адрес его сайта:",
        placeholder="Например: Рубин, Академия шоколада, lakond.ru, rubin-2000.ru...",
    )

with col_mode:
    search_type = st.selectbox(
        "Режим работы:", ["Авто-поиск по названию", "Прямой ввод сайта"]
    )

if st.button(
    "🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True
):
    if not company_input.strip():
        st.error("Пожалуйста, введите название компании или сайт.")
        st.stop()

    input_str = company_input.strip()
    domain = None

    if search_type == "Прямой ввод сайта" or (
        "." in input_str and " " not in input_str
    ):
        domain = normalize_domain(input_str)
    else:
        with st.spinner(f"Определяем официальный сайт для '{input_str}'..."):
            domain = find_site_dynamic(input_str)

    if domain:
        st.session_state["current_domain"] = domain
        with st.spinner(
            f"Сканируем сайт {domain} и фильтруем баннеры..."
        ):
            docs, products = extract_assets(domain)
            st.session_state["current_docs"] = docs
            st.session_state["current_products"] = products
    else:
        st.error(
            "Не удалось определить сайт. Выберите 'Прямой ввод сайта' и вставьте домен вручную (например: rubin-2000.ru)."
        )

# -----------------------------
# ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ
# -----------------------------

if "current_domain" in st.session_state:
    domain = st.session_state["current_domain"]
    docs = st.session_state.get("current_docs", [])
    products = st.session_state.get("current_products", [])

    st.success(f"🌐 Активный сайт заказчика: `{domain}`")

    tab1, tab2 = st.tabs(
        [
            "📄 Официальные Файлы (PDF/XLS)",
            "📦 Галерея Упаковки & Подарков (Фото)",
        ]
    )

    # ВКЛАДКА 1: Файлы
    with tab1:
        if docs:
            st.success(
                f"Найдено официально опубликованных файлов: **{len(docs)}**"
            )
            for d in docs:
                icon = "📕 PDF" if ".pdf" in d["url"].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-box">
                        <b>{icon} | {d['title']}</b><br>
                        <small style="color:gray;">Ссылка: {d['url']}</small><br>
                        <a href="{d['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info(
                "Открытых PDF/Excel файлов на страницах не найдено. Настоящие фото коробок смотрите во 2-й вкладке."
            )

    # ВКЛАДКА 2: Изображения коробок (Только реальная упаковка без баннеров)
    with tab2:
        if products:
            st.write(
                "Проверяем изображения и фильтруем баннеры сайта..."
            )

            # Скачиваем и физически фильтруем баннеры по пропорциям
            valid_products = []

            def download_and_filter(p):
                try:
                    res = requests.get(
                        p["img"], timeout=4, headers=HEADERS, verify=False
                    )
                    if res.status_code == 200:
                        if is_real_product_box(res.content):
                            p["bytes"] = res.content
                            return p
                except Exception:
                    pass
                return None

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=8
            ) as executor:
                results = list(
                    executor.map(download_and_filter, products[:60])
                )
                valid_products = [r for r in results if r is not None]

            if valid_products:
                st.success(
                    f"Найдено оригинальных коробок и подарков: **{len(valid_products)} шт.**"
                )

                # Выгрузка архивного файла (ZIP)
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(valid_products):
                        zf.writestr(f"box_{i+1:03d}.jpg", p["bytes"])

                st.download_button(
                    "📥 СКАЧАТЬ ВСЕ КОРОБКИ В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_boxes_catalog.zip",
                    mime="application/zip",
                )

                st.markdown("---")

                # Сетка (4 в ряд)
                cols = st.columns(4)
                for i, p in enumerate(valid_products):
                    with cols[i % 4]:
                        st.markdown(
                            '<div class="product-box">', unsafe_allow_html=True
                        )
                        st.image(p["bytes"], use_container_width=True)
                        st.markdown(
                            f'<div class="product-title">{p["title"][:65]}</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning(
                    "Товарные коробки не прошли фильтрацию или спрятаны во внутреннем каталоге."
                )

        else:
            st.warning("На страницах не найдено карточек товаров.")

    # Резервные кнопки
    st.markdown("---")
    st.write("### 🔍 Быстрый доступ к внешним поискам:")
    c1, c2, c3 = st.columns(3)
    clean_q = urllib.parse.quote(
        f'"{domain}" новогодние подарки упаковка {TARGET_YEAR}'
    )
    with c1:
        st.link_button(
            "📕 PDF в Google",
            f"https://www.google.com/search?q={clean_q}+filetype:pdf",
        )
    with c2:
        st.link_button(
            "📊 Прайсы XLS в Яндекс",
            f"https://yandex.ru/search/?text={clean_q}+прайс+xls",
        )
    with c3:
        st.link_button(
            "📱 Поиск в VK",
            f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={clean_q}",
        )

st.divider()
st.caption(
    f"Автоматический фильтр баннеров отсекает декоративные картинки сайта. На экран выводятся только пропорциональные фото коробок и подарков."
)
