import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт Pillow для работы с изображениями
try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Безопасный импорт DuckDuckGo (не вызовет ошибку, если библиотека отсутствует)
try:
    from duckduckgo_search import DDGS

    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

# -----------------------------
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# -----------------------------

st.set_page_config(
    page_title="Навигатор Подарков 2026",
    page_icon="📸",
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

st.title(f"📸 Визуальный Навигатор Каталогов {TARGET_YEAR}")
st.caption(
    "Приоритетный поиск официальных PDF/Excel каталогов. Если файла нет — система строит визуальные карточки товаров."
)

# -----------------------------
# БАЗА ЗНАНИЙ ФАБРИК (Мгновенный поиск)
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
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
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None


def find_site_cascade(company_name: str) -> str:
    """Многоуровневый каскадный поиск сайта"""
    q_low = company_name.lower().strip()

    # 1. Проверка по Базе Знаний
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v

    # 2. Поиск через DDGS (если библиотека доступна)
    if HAS_DDGS:
        try:
            with DDGS() as ddgs:
                res = list(
                    ddgs.text(
                        f'"{company_name}" официальный сайт кондитерская фабрика подарки',
                        region="ru-ru",
                        max_results=5,
                    )
                )
                for r in res:
                    link = r.get("href", "")
                    if link and not any(bad in link for bad in JUNK_DOMAINS):
                        return normalize_domain(link)
        except Exception:
            pass

    # 3. Резервный HTML-поиск
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={
                "q": f'"{company_name}" кондитерская фабрика официальный сайт'
            },
            headers=HEADERS,
            timeout=6,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                href = a.get("href", "")
                parsed_qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(href).query
                )
                target = parsed_qs.get("uddg", [href])[0]
                if target and not any(bad in target for bad in JUNK_DOMAINS):
                    return normalize_domain(target)
    except Exception:
        pass

    return None


def extract_assets(domain: str):
    """Ищет файлы PDF/XLS и карточки товаров"""
    base_url = f"https://{domain}"
    final_url, html = get_html(base_url)
    if not html:
        base_url = f"http://{domain}"
        final_url, html = get_html(base_url)

    if not html:
        return [], []

    soup = BeautifulSoup(html, "html.parser")

    # Ищем каталоговые страницы сайта
    nav_pages = {final_url}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text().lower()
        if any(kw in href or kw in text for kw in CATALOG_WORDS):
            full = urllib.parse.urljoin(final_url, a["href"])
            if domain in full:
                nav_pages.add(full)

    docs, products = [], []
    seen_links = set()

    # Парсим выявленные страницы (до 6 штук)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        pages_data = list(executor.map(get_html, list(nav_pages)[:6]))

        for p_url, p_html in pages_data:
            if not p_html:
                continue
            p_soup = BeautifulSoup(p_html, "html.parser")

            # 1. Поиск PDF / Excel / Word
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

            # 2. Поиск товарных карточек (картинка + заголовок)
            items = p_soup.find_all(
                ["div", "li", "article"],
                class_=re.compile(
                    r"product|item|card|catalog|goods|element", re.I
                ),
            )
            for item in items:
                img = item.find("img")
                if img:
                    src = (
                        img.get("data-src")
                        or img.get("data-original")
                        or img.get("src")
                    )
                    if src:
                        img_url = urllib.parse.urljoin(p_url, src)
                        # Преобразуем Битрикс-миниатюры в оригиналы высокаго качества
                        img_url = re.sub(
                            r"/resize_cache/.*?/\d+_\d+_\d+/",
                            "/upload/",
                            img_url,
                        )
                        img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

                        title = item.get_text(" ", strip=True)[:100]
                        if img_url not in seen_links and len(title) > 4:
                            if not any(
                                bad in title.lower() for bad in JUNK_WORDS
                            ):
                                seen_links.add(img_url)
                                products.append(
                                    {"title": title, "img": img_url}
                                )

    return docs, products


# -----------------------------
# ИНТЕРФЕЙС STREAMLIT
# -----------------------------

company_input = st.text_input(
    "Введите название компании или адрес сайта:",
    placeholder="Например: Академия шоколада, Лаконд, Баян Сулу, rubin-2000.ru...",
)

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ 2026", type="primary", use_container_width=True):
    if not company_input.strip():
        st.error("Пожалуйста, введите название компании или сайт.")
    else:
        domain = None
        input_str = company_input.strip()

        # Если ввели сайт напрямую
        if "." in input_str and " " not in input_str:
            domain = normalize_domain(input_str)
        else:
            with st.spinner(
                f"Динамически определяем сайт для '{input_str}'..."
            ):
                domain = find_site_cascade(input_str)

        if domain:
            st.info(f"🌐 Подключено к сайту: `{domain}`")
            with st.spinner("Анализируем каталог и сканируем данные..."):
                docs, products = extract_assets(domain)

            # --- ВЫВОД ШАГ 1: ГОТОВЫЕ ФАЙЛЫ (ПРИОРИТЕТ) ---
            if docs:
                st.success(
                    f"🎉 **НАЙДЕН ОФИЦИАЛЬНЫЙ КАТАЛОГ / ПРАЙС ({len(docs)} шт.)!**"
                )
                st.info(
                    "💡 Поиск карточек отменен, так как найден официальный файл."
                )
                for d in docs:
                    icon = "📕 PDF" if ".pdf" in d["url"].lower() else "📊 EXCEL"
                    st.markdown(
                        f"""
                        <div class="doc-box">
                            <b>{icon} | {d['title']}</b><br>
                            <a href="{d['url']}" target="_blank" class="btn-download">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ КАТАЛОГ</a>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

            # --- ВЫВОД ШАГ 2: ВИЗУАЛЬНЫЕ КАРТОЧКИ (ЕСЛИ ФАЙЛОВ НЕТ) ---
            elif products:
                st.warning("⚠️ **Прямые PDF/Excel файлы на сайте не найдены.**")
                st.subheader(
                    f"🖼️ Визуальные карточки товаров с сайта ({len(products)} шт.)"
                )

                # Скачивание ZIP-архива
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, p in enumerate(products[:100]):
                        try:
                            res_img = requests.get(p["img"], timeout=5)
                            if res_img.status_code == 200:
                                zf.writestr(
                                    f"gift_{i+1:03d}.jpg", res_img.content
                                )
                        except Exception:
                            continue

                st.download_button(
                    "📥 СКАЧАТЬ ВСЕ СНИМКИ В ZIP-АРХИВЕ",
                    data=zip_buffer.getvalue(),
                    file_name=f"{domain}_catalog_2026.zip",
                    mime="application/zip",
                )

                st.markdown("---")

                # Отображение сеткой 4 в ряд
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
                st.error(
                    "На сайте не удалось выгрузить ни файлы, ни карточки товаров."
                )

        else:
            st.error(
                "Не удалось определить сайт. Введите адрес сайта напрямую (например, chocolate-academy.ru)."
            )

st.divider()
st.caption(
    f"Автоматический поиск по сезону {TARGET_YEAR}. Системные ошибки отфильтрованы."
)
