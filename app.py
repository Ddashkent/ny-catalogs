import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Отключаем предупреждения SSL
requests.packages.urllib3.disable_warnings()

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Парсер Каталогов",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    
    /* Брендовый логотип Первый Снег */
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 15px; padding: 8px 18px;
        border-radius: 8px; border: 2px solid #ffffff;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        letter-spacing: 1px;
    }
    
    /* Нежный редкий снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px) translateX(0); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh) translateX(20px); opacity: 0.05; }
    }
    .snowflake {
        position: fixed; top: -10px; color: #93c5fd; font-size: 11px;
        user-select: none; pointer-events: none; z-index: 1;
    }
    .s1 { left: 10%; animation: snowfall 16s linear infinite 0s; }
    .s2 { left: 35%; animation: snowfall 20s linear infinite 3s; }
    .s3 { left: 65%; animation: snowfall 18s linear infinite 1s; }
    .s4 { left: 88%; animation: snowfall 22s linear infinite 5s; }

    .doc-card {
        background-color: #ffffff; border-left: 6px solid #dc2626;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #dc2626; color: white !important; font-weight: bold;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        display: inline-block; margin-top: 8px;
    }
    .btn-doc:hover { background-color: #b91c1c; }

    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 12px; margin-bottom: 15px;
        text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .badge-weight {
        background-color: #dc2626; color: white; font-weight: bold;
        padding: 3px 10px; font-size: 11px; border-radius: 12px;
        display: inline-block; margin-top: 4px;
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 6px;
        display: inline-block; margin-top: 4px; margin-right: 4px;
    }
    .product-title { font-weight: 700; font-size: 13px; color: #1e293b; margin: 8px 0; line-height: 1.3; }
    </style>
    
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="snowflake s1">❄</div><div class="snowflake s2">❅</div>
    <div class="snowflake s3">❆</div><div class="snowflake s4">❄</div>
""",
    unsafe_allow_html=True,
)

st.title(f"📦 Анализ Каталогов & Упаковки {TARGET_YEAR}")
st.caption(
    "Приоритетный поиск официальных PDF/Excel каталогов. Автоматическое извлечение карточек товаров и коробок."
)

# -----------------------------
# ВНУТРЕННЯЯ КАРТА ДОМЕНОВ
# -----------------------------

DOMAIN_MAP = {
    "рубин": "rubin-2000.ru",
    "rubin": "rubin-2000.ru",
    "рэйд": "podarki-reid21.ru",
    "reid": "podarki-reid21.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "академия шоколада": "chocolate-academy.ru",
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
    "победа": "pobeda.market",
    "униконф": "uniconf.ru",
    "спартак": "spartak.by",
    "коммунарка": "kommunarka.by",
    "рахат": "rakhat.kz",
}

SPECIAL_PATHS = {
    "rubin-2000.ru": [
        "https://rubin-2000.ru/catalog/",
        "https://rubin-2000.ru/catalog/upakovka/",
    ],
    "podarki-reid21.ru": [
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/",
        "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarochnye-nabory-novogodnie-podarki-2027/",
    ],
    "chocolate-academy.ru": [
        "https://chocolate-academy.ru/catalog/novogodnie-podarki/",
        "https://chocolate-academy.ru/catalog/",
    ],
    "lakond.ru": ["https://lakond.ru/products/", "https://lakond.ru/catalog/"],
}

# -----------------------------
# ФИЛЬТРЫ И МАРКЕРЫ
# -----------------------------

JUNK_DOC_WORDS = [
    "презентация",
    "соглашение",
    "политика",
    "договор",
    "оферта",
    "вакансии",
    "реквизиты",
    "cookies",
    "устав",
    "инвесторам",
]
GOOD_DOC_WORDS = [
    "каталог",
    "прайс",
    "подарки",
    "упаковка",
    "2026",
    "2025",
    "2027",
    "catalog",
    "price",
]

JUNK_IMAGE_WORDS = [
    "logo",
    "icon",
    "banner",
    "slider",
    "bg-",
    "social",
    "avatar",
    "payment",
    "delivery",
    "vk",
    "facebook",
    "instagram",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
WEIGHT_REGEX = re.compile(
    r"(\d+(?:[\.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE
)

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def resolve_domain(query: str) -> str:
    q_low = query.strip().lower()
    for key, dom in DOMAIN_MAP.items():
        if key in q_low:
            return dom
    if "." in q_low and " " not in q_low:
        return (
            q_low.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )
    return None


def fix_url(base_url: str, src: str) -> str:
    src = src.strip()
    if src.startswith("//"):
        src = "https:" + src
    return urllib.parse.urljoin(base_url, src)


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


# --- ШАГ 1: ПОИСК ТОЛЬКО КАТАЛОГОВ (БЕЗ ПРЕЗЕНТАЦИЙ И ЮР. МУСОРА) ---


def scan_for_documents(domain: str):
    docs, seen = [], set()
    base = f"https://{domain}"

    urls = [base, f"{base}/catalog/", f"{base}/podarki/"]
    if domain in SPECIAL_PATHS:
        urls = SPECIAL_PATHS[domain] + urls

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"]).lower()
            text = a.get_text().strip().lower()
            full_link = fix_url(url, a["href"])

            if any(ext in href for ext in [".pdf", ".xlsx", ".xls"]):
                combined = f"{text} {href}"
                # БЛОКИРУЕМ ПРЕЗЕНТАЦИИ И СОГЛАШЕНИЯ
                if any(bad in combined for bad in JUNK_DOC_WORDS):
                    continue
                # ТРЕБУЕМ КАТАЛОГ ИЛИ ПРАЙС
                if any(good in combined for good in GOOD_DOC_WORDS):
                    if full_link not in seen:
                        seen.add(full_link)
                        docs.append(
                            {
                                "title": a.get_text().strip()
                                or "Официальный каталог",
                                "url": full_link,
                            }
                        )
    return docs


# --- ШАГ 2: ПАРСИНГ КАРТОЧЕК ТОВАРОВ С САЙТА ---


def clean_image_url(url: str) -> str:
    """Очищает ссылки от Битрикс-ресайзов для высокого качества"""
    cleaned = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", url)
    cleaned = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", cleaned)
    return cleaned


def scan_product_cards(domain: str):
    base = f"https://{domain}"

    urls = [f"{base}/catalog/", f"{base}/podarki/", base]
    if domain in SPECIAL_PATHS:
        urls = SPECIAL_PATHS[domain] + urls

    products = []
    seen_imgs = set()

    for url in urls:
        _, html = get_html(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Удаляем служебные блоки
        for junk in soup.find_all(
            ["footer", "header", "nav"],
            class_=re.compile(r"footer|header|partners|slider", re.I),
        ):
            junk.decompose()

        # Ищем карточки товаров
        cards = soup.find_all(
            lambda t: t.name in ["div", "li", "article", "section"]
            and t.get("class")
            and any(
                c in " ".join(t.get("class")).lower()
                for c in [
                    "product",
                    "catalog-item",
                    "card",
                    "item",
                    "goods",
                    "element",
                    "b-catalog",
                ]
            )
        )
        if not cards:
            cards = soup.find_all("img")

        for card in cards:
            img = card if card.name == "img" else card.find("img")
            if not img:
                continue

            # Считываем изображение с поддержкой Lazy-Load
            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
            )
            if not src:
                continue

            if any(bad in src.lower() for bad in JUNK_IMAGE_WORDS):
                continue

            full_img_url = fix_url(url, src)
            full_img_url = clean_image_url(full_img_url)

            if full_img_url in seen_imgs:
                continue

            text = card.get_text(" ", strip=True) if card.name != "img" else ""

            weight_match = WEIGHT_REGEX.search(text)
            weight = weight_match.group(1) if weight_match else None

            title = img.get("alt") or img.get("title") or text[:60]
            title = re.sub(r"\s+", " ", title).strip()

            if len(title) > 2:
                seen_imgs.add(full_img_url)
                products.append(
                    {
                        "title": title,
                        "weight": weight,
                        "img_url": full_img_url,
                    }
                )

    return products


# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название компании или адрес её сайта:",
    placeholder="Например: Рубин, Академия шоколада, Лаконд, Акконд, rubin-2000.ru...",
)

if st.button(
    "🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary", use_container_width=True
):
    if not company_input.strip():
        st.stop()

    domain = resolve_domain(company_input)

    if domain:
        st.success(f"🌐 Официальный сайт подключен: `{domain}`")

        # ШАГ 1: ПОИСК PDF / EXCEL ФАЙЛОВ
        with st.spinner("ШАГ 1: Проверяем наличие PDF/Excel каталогов..."):
            documents = scan_for_documents(domain)

        if documents:
            st.markdown("---")
            st.success(
                f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ (ФАЙЛОВ: {len(documents)})!**"
            )
            st.info("💡 Скачайте полный официальный файл каталога ниже.")
            for doc in documents:
                icon = (
                    "📕 PDF"
                    if ".pdf" in doc["url"].lower()
                    else "📊 EXCEL / DOC"
                )
                st.markdown(
                    f"""
                    <div class="doc-card">
                        <h4 style="margin:0; color:#1e293b;">{icon} | {doc['title']}</h4>
                        <small style="color:gray;">Ссылка: {doc['url']}</small><br>
                        <a href="{doc['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            # ШАГ 2: ВЫГРУЗКА КАРТОЧЕК ТОВАРОВ ПРЯМО С САЙТА
            with st.spinner(
                "ШАГ 2: Прямых PDF нет. Считываем карточки коробок с сайта..."
            ):
                products = scan_product_cards(domain)

            st.markdown("---")
            if products:
                st.success(
                    f"Найдено карточек упаковки и подарков: **{len(products)} шт.**"
                )

                # Формирование ZIP архива
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(
                    zip_buffer, "w", zipfile.ZIP_DEFLATED
                ) as zf:
                    for i, prod in enumerate(products, start=1):
                        try:
                            res_img = requests.get(
                                prod["img_url"],
                                timeout=5,
                                headers=HEADERS,
                                verify=False,
                            )
                            if res_img.status_code == 200:
                                safe_name = re.sub(
                                    r"[^\w\s-]", "", prod["title"]
                                )[:30]
                                zf.writestr(
                                    f"box_{i:02d}_{safe_name}.jpg",
                                    res_img.content,
                                )
                        except Exception:
                            continue

                st.download_button(
                    f"📦 СКАЧАТЬ ВСЕ {len(products)} КОРОБОК В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_boxes_catalog.zip",
                    mime="application/zip",
                )

                st.markdown("---")

                # Отображение сетки карт 4 в ряд
                cols = st.columns(4)
                for idx, prod in enumerate(products):
                    with cols[idx % 4]:
                        st.markdown(
                            f"""
                            <div class="product-card">
                                <div class="product-title">{prod['title']}</div>
                                <span class="badge-cardboard">📦 КАРТОН / УПАКОВКА</span>
                                {f'<br><span class="badge-weight">⚖️ {prod["weight"]}</span>' if prod["weight"] else ''}
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.image(prod["img_url"], use_container_width=True)
            else:
                st.error("На сайте не удалось найти карточки товаров.")
    else:
        st.error(
            "Не удалось определить сайт. Введите адрес напрямую (например, rubin-2000.ru)"
        )

st.divider()
st.caption(
    f"Инструмент компании «Первый Снег». Сезон {TARGET_YEAR}. Сбор данных прямо из каталога сайта."
)
