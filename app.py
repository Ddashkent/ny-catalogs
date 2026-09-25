import concurrent.futures
import datetime
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

# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Навигатор Подарков 2026",
    page_icon="🎁",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f8f9fa; }
    .snapshot-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .product-title {
        font-size: 13px;
        font-weight: bold;
        color: #333;
        margin-top: 8px;
        min-height: 38px;
        line-height: 1.2;
    }
    .btn-download {
        background-color: #ff4b4b;
        color: white !important;
        font-weight: bold;
        padding: 12px 20px;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        margin-top: 10px;
    }
    .doc-box {
        background-color: #ffffff;
        border-left: 6px solid #28a745;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title(f"🎁 Универсальный Навигатор Подарков {TARGET_YEAR}")
st.caption(
    "Приоритетный поиск официальных PDF/Excel каталогов. Если файла нет — автосбор визуальных карточек товаров."
)

# -----------------------------
# БАЗА ЗНАНИЙ (Мгновенное совпадение)
# -----------------------------

KNOWLEDGE_BASE = {
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "рубин": "rubin-2000.ru",
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
    "каталог",
    "подарки",
    "продукц",
    "catalog",
    "нг",
    "новогод",
    "продукция",
    "подарок",
    "упаковка",
]
JUNK_DOMAINS = [
    "wikipedia.org",
    "otzovik",
    "avito",
    "checko",
    "list-org",
    "synapse",
    "hh.ru",
    "rabota",
    "vk.com",
    "youtube",
]

# Важнейшие стандартные пути на сайтах поставщиков
PROBE_PATHS = [
    "",
    "/catalog/",
    "/katalog/",
    "/podarki/",
    "/novogodnie-podarki/",
    "/produkciya/",
    "/catalog/novogodnie-podarki/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.lower().replace("www.", "")


def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=7, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


def find_domain_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()

    # 1. Поиск по базе
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v

    # 2. Прямой поиск сайта через поиск
    try:
        query = f"{company_name} кондитерская фабрика официальный сайт подарки"
        search_url = (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        )
        res = requests.get(search_url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                href = a.get("href", "")
                parsed_qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(href).query
                )
                target = parsed_qs.get("uddg", [href])[0]
                netloc = (
                    urllib.parse.urlparse(target)
                    .netloc.lower()
                    .replace("www.", "")
                )
                if netloc and not any(bad in netloc for bad in JUNK_DOMAINS):
                    return netloc
    except Exception:
        pass

    return None


def extract_assets_multipath(domain: str):
    """Сканирует главную и ключевые разделы каталога параллельно"""
    base_protocol = f"https://{domain}"

    # Формируем список URL для опроса
    urls_to_check = [f"{base_protocol}{path}" for path in PROBE_PATHS]

    docs, products = [], []
    seen_links = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        pages_data = list(executor.map(get_html, urls_to_check))

        for p_url, p_html in pages_data:
            if not p_html:
                continue
            p_soup = BeautifulSoup(p_html, "html.parser")

            # 1. Поиск PDF / Excel / Word документов
            for a in p_soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        full_link = urllib.parse.urljoin(p_url, a["href"])
                        if full_link not in seen_links:
                            seen_links.add(full_link)
                            docs.append(
                                {
                                    "title": text
                                    or "Официальный каталог / прайс-лист",
                                    "url": full_link,
                                }
                            )

            # 2. Извлечение карточек товаров (если PDF нет)
            if not docs:
                # Поиск изображений на страницах каталога
                for img in p_soup.find_all("img"):
                    src = (
                        img.get("data-src")
                        or img.get("data-original")
                        or img.get("src")
                    )
                    if not src:
                        continue

                    img_url = urllib.parse.urljoin(p_url, src)

                    # Игнорируем мелкие иконки и соцсети
                    if any(
                        bad in img_url.lower()
                        for bad in [
                            "logo",
                            "icon",
                            "banner",
                            "facebook",
                            "vk",
                            "telegram",
                            "youtube",
                            "avatar",
                        ]
                    ):
                        continue

                    # Очистка Битрикс-ресайзов для высокого качества
                    img_url = re.sub(
                        r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url
                    )
                    img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

                    # Извлечение заголовка товара из родителей
                    parent = img.parent
                    title = ""
                    if parent:
                        title = parent.get_text(" ", strip=True)[:120]

                    if not title or len(title) < 5:
                        title = (
                            img.get("alt")
                            or img.get("title")
                            or "Подарок / Упаковка"
                        )

                    title = re.sub(r"\s+", " ", title).strip()

                    if img_url not in seen_links and len(title) > 3:
                        if not any(bad in title.lower() for bad in JUNK_WORDS):
                            seen_links.add(img_url)
                            products.append({"title": title, "img": img_url})

    return docs, products


# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_query = st.text_input(
    "Введите название компании или адрес сайта:",
    placeholder="Например: Академия шоколада, Лаконд, Баян Сулу, rubin-2000.ru...",
)

if st.button("🚀 ПОЛУЧИТЬ ДАННЫЕ 2026", type="primary", use_container_width=True):
    if not company_query.strip():
        st.error("Пожалуйста, введите название компании или адрес сайта.")
    else:
        domain = None
        input_str = company_query.strip()

        # Проверка: введен сайт напрямую или название
        if "." in input_str and " " not in input_str:
            domain = normalize_domain(input_str)
        else:
            with st.spinner(
                f"Динамически определяем сайт для '{input_str}'..."
            ):
                domain = find_domain_dynamic(input_str)

        if domain:
            st.info(f"🌐 Подключено к сайту: `{domain}`")
            with st.spinner(
                "Сканируем главную страницу и каталожные разделы..."
            ):
                docs, products = extract_assets_multipath(domain)

            # --- ВЫВОД РЕЗУЛЬТАТОВ: ШАГ 1 (ОФИЦИАЛЬНЫЕ ФАЙЛЫ) ---
            if docs:
                st.success(
                    f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ / ПРАЙС ({len(docs)} шт.)!**"
                )
                st.info(
                    "💡 Найдены официальные файлы, визуальный парсинг сайта пропущен."
                )
                for d in docs:
                    icon = "📕 PDF" if ".pdf" in d["url"].lower() else "📊 EXCEL / DOC"
                    st.markdown(
                        f"""
                        <div class="doc-box">
                            <b>{icon} | {d['title']}</b><br>
                            <a href="{d['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ ФАЙЛ</a>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

            # --- ВЫВОД РЕЗУЛЬТАТОВ: ШАГ 2 (ВИЗУАЛЬНЫЕ КАРТОЧКИ) ---
            elif products:
                st.warning("⚠️ **Прямые PDF/Excel файлы на страницах не найдены.**")
                st.subheader(
                    f"🖼️ Визуальные карточки товаров с сайта ({len(products)} шт.)"
                )

                # Выгрузка ZIP-архива
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(products[:100]):
                        try:
                            img_res = requests.get(p["img"], timeout=5)
                            if img_res.status_code == 200:
                                zf.writestr(f"gift_{i+1:03d}.jpg", img_res.content)
                        except Exception:
                            continue

                st.download_button(
                    "📥 СКАЧАТЬ ВСЕ СНИМКИ В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_catalog_2026.zip",
                    mime="application/zip",
                )

                st.markdown("---")

                # Отображение 4 в ряд
                cols = st.columns(4)
                for i, p in enumerate(products):
                    with cols[i % 4]:
                        st.markdown(
                            '<div class="snapshot-card">', unsafe_allow_html=True
                        )
                        st.image(p["img"], use_container_width=True)
                        st.markdown(
                            f'<div class="product-title">{p["title"]}</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

            else:
                # ВМЕСТО КРАСНОЙ ОШИБКИ -> ВЫДАЕМ СНАЙПЕРСКИЕ ССЫЛКИ
                st.warning(
                    f"⚠️ Сайт `{domain}` защищен антиботом или использует закрытый каталог."
                )
                st.write(
                    "### 🚀 Быстрый доступ к официальным файлам в 1 клик:"
                )

                c1, c2, c3 = st.columns(3)
                clean_q = urllib.parse.quote(
                    f'"{domain}" новогодние подарки каталог {TARGET_YEAR}'
                )
                with c1:
                    st.link_button(
                        "📕 Найти PDF в Google",
                        f"https://www.google.com/search?q={clean_q}+filetype:pdf",
                    )
                with c2:
                    st.link_button(
                        "📊 Найти Прайсы в Яндекс",
                        f"https://yandex.ru/search/?text={clean_q}+прайс+xls",
                    )
                with c3:
                    st.link_button(
                        "📱 Искать в VK",
                        f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={clean_q}",
                    )

        else:
            st.error(
                "Не удалось автоматически определить сайт. Введите домен компании напрямую (например, chocolate-academy.ru)."
            )

st.divider()
st.caption(
    f"Автоматическое многопутевое сканирование сайтов на сезон {TARGET_YEAR}."
)
