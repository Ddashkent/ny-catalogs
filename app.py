import concurrent.futures
import csv
import datetime
import hashlib
import html as html_module
import io
import re
import threading
import urllib.parse
import zipfile
from collections import deque

import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings()

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from curl_cffi import requests as curl_requests

    HAS_CURL = True
except ImportError:
    HAS_CURL = False

try:
    from ddgs import DDGS

    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False


# =========================================================
# ОБЩИЕ НАСТРОЙКИ
# =========================================================

CURRENT_YEAR = datetime.date.today().year
NEXT_YEAR = CURRENT_YEAR + 1
TARGET_YEARS = {CURRENT_YEAR, NEXT_YEAR}

MAX_PAGES = 60
MAX_DEPTH = 3
PAGE_WORKERS = 6
IMAGE_WORKERS = 8

st.set_page_config(
    page_title="Первый Снег | Каталоги конкурентов",
    page_icon="❄️",
    layout="wide",
)


# =========================================================
# ДИЗАЙН
# =========================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f8fafc;
    }

    .company-logo {
        position: fixed;
        top: 15px;
        right: 20px;
        z-index: 99999;
        background-color: #dc2626;
        color: white !important;
        font-weight: 900;
        padding: 8px 18px;
        border-radius: 8px;
        border: 2px solid white;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.30);
        letter-spacing: 1px;
    }

    .doc-card {
        background-color: white;
        border-left: 6px solid #dc2626;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }

    .doc-button {
        display: inline-block;
        background-color: #dc2626;
        color: white !important;
        font-weight: 700;
        padding: 9px 18px;
        margin-top: 8px;
        border-radius: 7px;
        text-decoration: none;
    }

    .product-title {
        min-height: 42px;
        margin: 5px 0;
        color: #1e293b;
        font-size: 14px;
        font-weight: 700;
        line-height: 1.3;
    }

    .badge-box {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        background-color: #16a34a;
        color: white;
        font-size: 11px;
        font-weight: 700;
    }

    .badge-weight {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        background-color: #dc2626;
        color: white;
        font-size: 11px;
        font-weight: 700;
    }
    </style>

    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    """,
    unsafe_allow_html=True,
)

st.title("🎁 Каталоги новогодних подарков конкурентов")
st.caption(
    f"Поиск каталогов и подарочных наборов сезонов "
    f"{CURRENT_YEAR}–{NEXT_YEAR}. Одиночные конфеты, плитки, "
    f"батончики и рекламные изображения исключаются."
)


# =========================================================
# ПРОВЕРЕННЫЕ КОМПАНИИ И ПУТИ
# =========================================================

SITE_MAP = {
    "рубин": "rubin-2000.ru",
    "rubin": "rubin-2000.ru",
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
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "славянка": "slavyanka.ru",
    "миракс": "mirax-gifts.ru",
    "москондитер": "mosconditer.ru",
    "росшоколад": "roschocolate.ru",
}

START_PATHS = {
    "rubin-2000.ru": ["/catalog/"],
    "chocolate-academy.ru": ["/catalog/", "/catalog/novogodnie-podarki/"],
    "lakond.ru": ["/products/", "/catalog/"],
    "akkond.ru": ["/catalog/"],
    "kommunarka.by": ["/catalog/"],
    "spartak.by": ["/catalog/"],
    "rakhat.kz": ["/products/", "/catalog/"],
    "bayansulu.kz": ["/ru/catalog/", "/catalog/"],
    "podarki-reid21.ru": ["/present-category/"],
}


# =========================================================
# СЛОВАРИ ФИЛЬТРАЦИИ
# =========================================================

NEW_YEAR_WORDS = [
    "новогод",
    "новый год",
    "рождеств",
    "christmas",
    "xmas",
    "new-year",
    "newyear",
    "символ года",
]

GIFT_WORDS = [
    "подарок",
    "подарки",
    "подарочн",
    "набор",
    "комплект",
    "ассорти",
    "сладкий подарок",
]

TARGET_PACKAGE_WORDS = [
    "короб",
    "картон",
    "микрогофр",
    "гофрокартон",
    "мгк",
    "переплет",
    "переплёт",
    "кашир",
    "туб",
    "тубус",
    "футляр",
    "шкатул",
    "сундуч",
    "домик",
    "книга",
    "чемоданчик",
]

SINGLE_SWEET_WORDS = [
    "конфета",
    "конфеты",
    "батончик",
    "шоколадка",
    "плитка",
    "шоколадная плитка",
    "карамель",
    "драже",
    "вафля",
    "вафли",
    "печенье",
    "зефир",
    "мармелад",
    "ирис",
    "помадка",
    "поштучно",
    "весовые",
    "на развес",
]

WRONG_MATERIAL_WORDS = [
    "текстиль",
    "ткань",
    "мешок",
    "мешочек",
    "рюкзак",
    "подушка",
    "плюш",
    "мягкая игрушка",
    "жесть",
    "жестяная",
    "металл",
    "дерево",
    "фанера",
    "пластик",
    "пвх",
]

JUNK_IMAGE_WORDS = [
    "logo",
    "icon",
    "banner",
    "slider",
    "sprite",
    "placeholder",
    "no-image",
    "no_image",
    "social",
    "avatar",
    "payment",
    "delivery",
    "header",
    "footer",
    "menu",
    "arrow",
    "captcha",
    "counter",
    "metrika",
    "favicon",
]

JUNK_DOCUMENT_WORDS = [
    "презентация",
    "соглашение",
    "политика",
    "конфиденциальность",
    "персональные данные",
    "договор",
    "оферта",
    "вакансии",
    "реквизиты",
    "cookies",
    "устав",
    "инвесторам",
    "соут",
    "privacy",
    "policy",
    "license",
    "сертификат",
    "декларация",
    "отчет",
]

DOCUMENT_WORDS = [
    "каталог",
    "catalog",
    "прайс",
    "price",
    "новогод",
    "подарки",
    "gift",
]

LINK_HINTS = [
    "новогод",
    "подар",
    "gift",
    "new-year",
    "newyear",
    "catalog",
    "каталог",
    "product",
    "товар",
    "upakov",
    "упаков",
    "korob",
    "короб",
    "karton",
    "картон",
    "tuba",
    "туб",
    "present-category",
]

BAD_LINK_HINTS = [
    "login",
    "register",
    "account",
    "cart",
    "basket",
    "compare",
    "favorite",
    "search",
    "contact",
    "vacancy",
    "news",
    "blog",
    "privacy",
    "policy",
    "mailto:",
    "tel:",
    "javascript:",
]

MARKETPLACE_HOSTS = [
    "wildberries.",
    "ozon.",
    "market.yandex.",
    "avito.",
    "instagram.",
    "facebook.",
    "vk.com",
    "youtube.",
    "wikipedia.",
    "2gis.",
]

PRODUCT_CLASS_RE = re.compile(
    r"(product|catalog[-_]?item|product[-_]?item|goods|"
    r"card|item[-_]?card|b-catalog|catalog[-_]?element)",
    re.I,
)

WEIGHT_REGEX = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)",
    re.IGNORECASE,
)

YEAR_REGEX = re.compile(r"\b(20\d{2})\b")


# =========================================================
# НОРМАЛИЗАЦИЯ
# =========================================================

def normalize_text(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_domain(value: str):
    raw = value.strip()
    normalized = normalize_text(raw)

    if raw.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(raw)
        return parsed.netloc.replace("www.", ""), raw

    if "." in raw and " " not in raw:
        prepared = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
        parsed = urllib.parse.urlparse(prepared)
        return parsed.netloc.replace("www.", ""), prepared

    # Сначала точные совпадения — чтобы «тор» не перехватывал «тореро».
    if normalized in SITE_MAP:
        domain = SITE_MAP[normalized]
        return domain, f"https://{domain}"

    # Потом длинные алиасы.
    aliases = sorted(SITE_MAP, key=len, reverse=True)
    for alias in aliases:
        if len(alias) >= 5 and re.search(
            rf"(^|\s){re.escape(alias)}($|\s)", normalized
        ):
            domain = SITE_MAP[alias]
            return domain, f"https://{domain}"

    return None, None


def clean_url(base_url: str, value: str) -> str:
    value = (value or "").strip()

    if not value or value.startswith(
        ("data:", "javascript:", "mailto:", "tel:")
    ):
        return ""

    if value.startswith("//"):
        value = "https:" + value

    full = urllib.parse.urljoin(base_url, value)
    parsed = urllib.parse.urlparse(full)

    path = urllib.parse.quote(
        urllib.parse.unquote(parsed.path),
        safe="/:@-._~",
    )
    query = urllib.parse.quote(
        urllib.parse.unquote(parsed.query),
        safe="=&?+/:,@-._~",
    )

    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            query,
            "",
        )
    )


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

    params = [
        (key, value)
        for key, value in params
        if not key.lower().startswith("utm_")
        and key.lower() not in {"yclid", "gclid", "fbclid"}
    ]

    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            urllib.parse.urlencode(params),
            "",
        )
    )


def same_site(url_1: str, url_2: str) -> bool:
    host_1 = urllib.parse.urlparse(url_1).netloc.lower().replace("www.", "")
    host_2 = urllib.parse.urlparse(url_2).netloc.lower().replace("www.", "")
    return host_1 == host_2


# =========================================================
# БЫСТРЫЙ СЕТЕВОЙ СЛОЙ
# =========================================================

THREAD_LOCAL = threading.local()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}


def get_thread_session():
    session = getattr(THREAD_LOCAL, "session", None)

    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.verify = False

        retry = Retry(
            total=1,
            connect=0,
            read=0,
            status=1,
            backoff_factor=0.2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=20,
            pool_maxsize=20,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        THREAD_LOCAL.session = session

    return session


def looks_like_html(content: bytes) -> bool:
    if not content or len(content) < 300:
        return False

    beginning = content[:5000].lower()

    return any(
        marker in beginning
        for marker in (
            b"<html",
            b"<!doctype",
            b"<body",
            b"<head",
            b"<title",
        )
    )


def request_html(url: str, transport: str):
    try:
        if transport == "curl" and HAS_CURL:
            response = curl_requests.get(
                url,
                headers=HEADERS,
                impersonate="chrome",
                timeout=10,
                verify=False,
                allow_redirects=True,
            )
        else:
            response = get_thread_session().get(
                url,
                timeout=(3.5, 9),
                allow_redirects=True,
            )

        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}"

        content = response.content

        if not looks_like_html(content):
            return None, "Ответ не похож на HTML"

        low = content[:10000].lower()
        if (
            b"cf-chl-" in low
            or b"access denied" in low
            or b"enable javascript and cookies" in low
        ):
            return None, "Сайт вернул страницу защиты"

        return {
            "url": response.url,
            "content": content,
            "transport": transport,
            "status": response.status_code,
        }, None

    except Exception as exc:
        return None, str(exc)


def transport_order(url: str):
    host = urllib.parse.urlparse(url).netloc.lower()

    # curl_cffi быстрее решает часть TLS-проблем на .by и .kz.
    if HAS_CURL and host.endswith((".by", ".kz")):
        return ["curl", "requests"]

    if HAS_CURL:
        return ["requests", "curl"]

    return ["requests"]


def probe_url(url: str):
    errors = []

    for transport in transport_order(url):
        result, error = request_html(url, transport)

        if result:
            return result, errors

        errors.append(f"{transport}: {error}")

    return None, errors


def connection_variants(url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    host_without_www = host.replace("www.", "")
    path = parsed.path or "/"

    hosts = [host]
    if host.startswith("www."):
        hosts.append(host_without_www)
    else:
        hosts.append("www." + host_without_www)

    variants = [url]

    for scheme in ("https", "http"):
        for candidate_host in hosts:
            variants.append(
                urllib.parse.urlunparse(
                    (
                        scheme,
                        candidate_host,
                        path,
                        "",
                        parsed.query,
                        "",
                    )
                )
            )

    # Также проверяем главную страницу, если переданный раздел устарел.
    for scheme in ("https", "http"):
        for candidate_host in hosts:
            variants.append(f"{scheme}://{candidate_host}/")

    unique = []
    seen = set()

    for item in variants:
        item = canonical_url(item)
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return unique


def connect_to_site(url: str):
    variants = connection_variants(url)
    errors = []

    # Варианты проверяются параллельно, а не 4 × 12 секунд подряд.
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=min(4, len(variants))
    )

    future_map = {
        executor.submit(probe_url, variant): variant
        for variant in variants
    }

    try:
        for future in concurrent.futures.as_completed(
            future_map,
            timeout=15,
        ):
            variant = future_map[future]

            try:
                result, variant_errors = future.result()
            except Exception as exc:
                errors.append(f"{variant}: {exc}")
                continue

            if result:
                for pending in future_map:
                    if not pending.done():
                        pending.cancel()

                executor.shutdown(wait=False, cancel_futures=True)
                return result, errors

            errors.append(
                f"{variant}: {'; '.join(variant_errors)}"
            )

    except concurrent.futures.TimeoutError:
        errors.append("Истекло время параллельной проверки адресов")

    executor.shutdown(wait=False, cancel_futures=True)
    return None, errors


def fetch_page(url: str, transport: str):
    result, error = request_html(url, transport)
    return result, error


# =========================================================
# АВТОПОИСК САЙТА ПО НАЗВАНИЮ
# =========================================================

def transliterate(text: str) -> str:
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
        "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }

    result = "".join(
        table.get(character, character)
        for character in text.lower()
    )

    return re.sub(r"[^a-z0-9]+", "-", result).strip("-")


def search_company_candidates(company_name: str):
    candidates = []

    if HAS_DDGS:
        try:
            query = (
                f'"{company_name}" официальный сайт '
                f"новогодние подарки каталог упаковка"
            )

            results = list(
                DDGS().text(
                    query,
                    region="ru-ru",
                    safesearch="off",
                    max_results=8,
                )
            )

            for item in results:
                href = (
                    item.get("href")
                    or item.get("url")
                    or ""
                )

                if not href.startswith(("http://", "https://")):
                    continue

                host = urllib.parse.urlparse(href).netloc.lower()

                if any(blocked in host for blocked in MARKETPLACE_HOSTS):
                    continue

                candidates.append(href)

        except Exception:
            pass

    # Бесплатный резервный подбор доменов.
    slug = transliterate(company_name)

    if slug:
        candidates.extend(
            [
                f"https://{slug}.ru",
                f"https://{slug}.by",
                f"https://{slug}.kz",
                f"https://{slug}-gifts.ru",
                f"https://{slug}-podarki.ru",
            ]
        )

    unique = []
    seen_hosts = set()

    for candidate in candidates:
        host = urllib.parse.urlparse(candidate).netloc.replace("www.", "")

        if host and host not in seen_hosts:
            seen_hosts.add(host)
            unique.append(candidate)

    return unique[:10]


def company_site_score(company_name: str, result: dict) -> int:
    soup = BeautifulSoup(result["content"], "lxml")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = soup.get_text(" ", strip=True)[:150000]

    text = normalize_text(f"{title} {body} {result['url']}")
    company_words = [
        word
        for word in normalize_text(company_name).split()
        if len(word) >= 3
    ]

    company_score = sum(2 for word in company_words if word in text)

    theme_score = 0
    for word in NEW_YEAR_WORDS:
        if word in text:
            theme_score += 3

    for word in GIFT_WORDS:
        if word in text:
            theme_score += 2

    for word in TARGET_PACKAGE_WORDS:
        if word in text:
            theme_score += 1

    if theme_score == 0:
        return -100

    return company_score + theme_score


def resolve_company(company_input: str):
    domain, direct_url = normalize_domain(company_input)

    # Известная компания или введённый домен.
    if direct_url:
        connection, errors = connect_to_site(direct_url)

        if connection:
            connection["domain"] = (
                urllib.parse.urlparse(connection["url"])
                .netloc.replace("www.", "")
            )
            return connection, errors

        return None, errors

    # Новая компания — ищем сайт автоматически.
    candidates = search_company_candidates(company_input)

    if not candidates:
        return None, ["Поисковик не вернул кандидатов"]

    checked = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(probe_url, candidate): candidate
            for candidate in candidates
        }

        for future in concurrent.futures.as_completed(future_map):
            candidate = future_map[future]

            try:
                result, errors = future.result()
            except Exception as exc:
                checked.append((candidate, None, str(exc)))
                continue

            if result:
                score = company_site_score(company_input, result)
                checked.append((candidate, result, score))
            else:
                checked.append(
                    (candidate, None, "; ".join(errors))
                )

    valid = [
        (score, result)
        for _, result, score in checked
        if result and isinstance(score, int) and score >= 3
    ]

    if not valid:
        diagnostics = [
            f"{candidate}: {details}"
            for candidate, _, details in checked
        ]
        return None, diagnostics

    valid.sort(key=lambda item: item[0], reverse=True)
    connection = valid[0][1]
    connection["domain"] = (
        urllib.parse.urlparse(connection["url"])
        .netloc.replace("www.", "")
    )

    return connection, []


# =========================================================
# ФИЛЬТРЫ КАТАЛОГОВ И ТОВАРОВ
# =========================================================

def extract_years(text: str):
    return {
        int(year)
        for year in YEAR_REGEX.findall(text or "")
    }


def years_are_relevant(text: str) -> bool:
    years = extract_years(text)

    # Если год не указан, документ/товар проверяется по тематике.
    if not years:
        return True

    return bool(years & TARGET_YEARS)


def is_target_document(text: str) -> bool:
    normalized = normalize_text(
        urllib.parse.unquote(text or "")
    )

    if any(word in normalized for word in JUNK_DOCUMENT_WORDS):
        return False

    if not years_are_relevant(normalized):
        return False

    has_document_word = any(
        word in normalized
        for word in DOCUMENT_WORDS
    )

    has_new_year = any(
        word in normalized
        for word in NEW_YEAR_WORDS
    )

    has_target_year = any(
        str(year) in normalized
        for year in TARGET_YEARS
    )

    # Нужен каталог/прайс и новогодняя тема либо нужный год.
    return has_document_word and (has_new_year or has_target_year)


def is_new_year_context(text: str) -> bool:
    normalized = normalize_text(text)

    if not years_are_relevant(normalized):
        return False

    return (
        any(word in normalized for word in NEW_YEAR_WORDS)
        or any(str(year) in normalized for year in TARGET_YEARS)
    )


def is_target_product(
    title: str,
    card_text: str,
    image_url: str,
    product_url: str,
    page_context: str,
    is_product_card: bool,
) -> bool:
    own_text = normalize_text(
        f"{title} {card_text} "
        f"{urllib.parse.unquote(image_url)} "
        f"{urllib.parse.unquote(product_url)}"
    )
    context = normalize_text(page_context)
    combined = f"{own_text} {context}"

    # Старые годы не принимаются.
    if not years_are_relevant(combined):
        return False

    # Жесть, текстиль, дерево, пластик и игрушки исключаются.
    if any(word in own_text for word in WRONG_MATERIAL_WORDS):
        return False

    has_single_sweet = any(
        word in own_text
        for word in SINGLE_SWEET_WORDS
    )
    has_gift = any(
        word in own_text
        for word in GIFT_WORDS
    )
    has_package = any(
        word in own_text
        for word in TARGET_PACKAGE_WORDS
    )

    context_is_new_year = is_new_year_context(context)
    context_has_package = any(
        word in context
        for word in TARGET_PACKAGE_WORDS
    )

    # Обычная конфета или плитка не проходит только по контексту страницы.
    if has_single_sweet and not has_gift and not has_package:
        return False

    # Явный подарок/набор должен быть новогодним.
    if has_gift:
        return (
            is_new_year_context(own_text)
            or context_is_new_year
        )

    # Явная коробка/туба должна находиться в новогоднем разделе.
    if has_package:
        return (
            is_new_year_context(own_text)
            or context_is_new_year
        )

    # Пустой alt разрешён только внутри настоящей товарной карточки
    # в конкретном разделе новогодней картонной упаковки.
    if (
        is_product_card
        and context_is_new_year
        and context_has_package
        and not has_single_sweet
    ):
        return True

    return False


# =========================================================
# ИЗВЛЕЧЕНИЕ КАРТОЧЕК
# =========================================================

def extract_image_source(img):
    for attribute in (
        "data-src",
        "data-original",
        "data-lazy-src",
        "data-srcset",
        "srcset",
        "src",
    ):
        value = img.get(attribute)

        if not value:
            continue

        if "srcset" in attribute:
            candidates = [
                item.strip().split()[0]
                for item in value.split(",")
                if item.strip()
            ]
            if candidates:
                return candidates[-1]
        else:
            return value

    return ""


def find_product_container(img):
    levels = 0

    for parent in img.parents:
        if not getattr(parent, "name", None):
            continue

        levels += 1
        classes = " ".join(parent.get("class", []))

        if (
            parent.name in {"article", "li"}
            or PRODUCT_CLASS_RE.search(classes)
            or parent.get("itemtype", "").endswith("/Product")
        ):
            return parent, True

        if levels >= 6:
            break

    return img.parent, False


def extract_product_title(card, img):
    selectors = [
        "[itemprop='name']",
        ".product-title",
        ".product-name",
        ".item-title",
        ".item-name",
        ".catalog-item-title",
        "h2",
        "h3",
        "h4",
    ]

    if card:
        for selector in selectors:
            try:
                element = card.select_one(selector)
            except Exception:
                element = None

            if element:
                title = " ".join(element.get_text(" ", strip=True).split())
                if len(title) >= 3:
                    return title[:180]

    for value in (
        img.get("alt"),
        img.get("title"),
    ):
        if value:
            value = " ".join(value.split())
            if len(value) >= 3:
                return value[:180]

    if card:
        text = " ".join(card.get_text(" ", strip=True).split())
        return text[:180]

    return ""


def extract_product_link(card, page_url: str):
    if not card:
        return page_url

    link = card.find("a", href=True)

    if not link:
        return page_url

    return clean_url(page_url, link["href"])


def parse_page(page_url: str, content: bytes):
    soup = BeautifulSoup(content, "lxml")

    for junk in soup.select(
        "script, style, noscript, iframe, "
        "footer, header, nav"
    ):
        junk.decompose()

    title_text = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else ""
    )

    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""

    breadcrumbs = " ".join(
        element.get_text(" ", strip=True)
        for element in soup.select(
            ".breadcrumb, .breadcrumbs, [itemtype*='BreadcrumbList']"
        )[:3]
    )

    page_context = (
        f"{page_url} {title_text} {h1_text} {breadcrumbs}"
    )

    documents = []
    products = []
    discovered_links = []

    # ---------- Документы ----------
    for link in soup.find_all("a", href=True):
        href = clean_url(page_url, link["href"])

        if not href:
            continue

        path = urllib.parse.urlparse(href).path.lower()

        if path.endswith((".pdf", ".xlsx", ".xls")):
            link_text = " ".join(
                link.get_text(" ", strip=True).split()
            )
            combined = (
                f"{link_text} "
                f"{urllib.parse.unquote(href)} "
                f"{page_context}"
            )

            if is_target_document(combined):
                documents.append(
                    {
                        "title": (
                            link_text
                            or f"Новогодний каталог {CURRENT_YEAR}"
                        ),
                        "url": href,
                    }
                )

    # ---------- Товарные изображения ----------
    for img in soup.find_all("img"):
        src = extract_image_source(img)

        if not src:
            continue

        image_url = clean_url(page_url, src)

        if not image_url:
            continue

        decoded_url = urllib.parse.unquote(image_url).lower()

        if any(word in decoded_url for word in JUNK_IMAGE_WORDS):
            continue

        card, is_product_card = find_product_container(img)
        title = extract_product_title(card, img)

        card_text = ""
        if card and card.name != "img":
            card_text = " ".join(
                card.get_text(" ", strip=True).split()
            )[:1200]

        product_url = extract_product_link(card, page_url)

        if not is_target_product(
            title=title,
            card_text=card_text,
            image_url=image_url,
            product_url=product_url,
            page_context=page_context,
            is_product_card=is_product_card,
        ):
            continue

        weight_match = WEIGHT_REGEX.search(
            f"{title} {card_text}"
        )
        weight = (
            weight_match.group(1)
            if weight_match
            else None
        )

        products.append(
            {
                "title": title or "Новогодний подарочный набор",
                "weight": weight,
                "image_url": image_url,
                "product_url": product_url,
                "source_page": page_url,
            }
        )

    # ---------- Ссылки для дальнейшего обхода ----------
    page_is_target = (
        is_new_year_context(page_context)
        or any(
            word in normalize_text(page_context)
            for word in TARGET_PACKAGE_WORDS
        )
    )

    for link in soup.find_all("a", href=True):
        href_raw = link["href"].strip()

        if any(
            href_raw.lower().startswith(prefix)
            for prefix in ("mailto:", "tel:", "javascript:")
        ):
            continue

        href = clean_url(page_url, href_raw)

        if not href or not same_site(href, page_url):
            continue

        path = urllib.parse.urlparse(href).path.lower()

        if path.endswith(
            (
                ".jpg", ".jpeg", ".png", ".webp",
                ".gif", ".svg", ".pdf", ".xlsx", ".xls",
                ".zip", ".rar",
            )
        ):
            continue

        text = " ".join(link.get_text(" ", strip=True).split())
        combined = normalize_text(
            f"{text} {urllib.parse.unquote(href)}"
        )

        if any(word in combined for word in BAD_LINK_HINTS):
            continue

        link_years = extract_years(combined)
        if link_years and not (link_years & TARGET_YEARS):
            continue

        score = 0

        if any(word in combined for word in NEW_YEAR_WORDS):
            score += 100
        if any(word in combined for word in GIFT_WORDS):
            score += 80
        if any(word in combined for word in TARGET_PACKAGE_WORDS):
            score += 70
        if any(word in combined for word in LINK_HINTS):
            score += 40
        if any(
            token in combined
            for token in ("page", "pagen", "p=", "pg=")
        ):
            score += 35
        if text.isdigit() and page_is_target:
            score += 30
        if (
            page_is_target
            and any(
                token in combined
                for token in ("product", "товар", "item")
            )
        ):
            score += 20

        if score > 0:
            discovered_links.append(
                {
                    "url": href,
                    "score": score,
                }
            )

    return documents, products, discovered_links


# =========================================================
# ГЛУБОКИЙ ОБХОД САЙТА
# =========================================================

def crawl_site(connection: dict):
    start_url = connection["url"]
    transport = connection["transport"]
    domain = connection["domain"]

    parsed = urllib.parse.urlparse(start_url)
    base_root = f"{parsed.scheme}://{parsed.netloc}"

    queue = deque()
    queued = set()
    visited = set()

    def add_to_queue(url: str, depth: int, priority: int = 0):
        normalized_url = canonical_url(url)

        if normalized_url in queued or normalized_url in visited:
            return

        if not same_site(normalized_url, base_root):
            return

        queued.add(normalized_url)
        queue.append(
            {
                "url": normalized_url,
                "depth": depth,
                "priority": priority,
            }
        )

    add_to_queue(start_url, 0, 1000)
    add_to_queue(base_root + "/", 0, 900)

    for path in START_PATHS.get(domain, ["/catalog/"]):
        add_to_queue(
            urllib.parse.urljoin(base_root + "/", path),
            0,
            800,
        )

    documents_by_url = {}
    products_by_image = {}
    page_errors = []
    pages_scanned = 0

    initial_cache = {
        canonical_url(start_url): connection["content"]
    }

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=PAGE_WORKERS
    ) as executor:
        while queue and pages_scanned < MAX_PAGES:
            # Приоритетные ссылки ставим впереди.
            sorted_queue = sorted(
                list(queue),
                key=lambda item: item["priority"],
                reverse=True,
            )
            queue.clear()
            queue.extend(sorted_queue)

            batch = []

            while (
                queue
                and len(batch) < PAGE_WORKERS
                and pages_scanned + len(batch) < MAX_PAGES
            ):
                item = queue.popleft()

                if item["url"] in visited:
                    continue

                visited.add(item["url"])
                batch.append(item)

            if not batch:
                break

            futures = {}

            for item in batch:
                cached = initial_cache.get(item["url"])

                if cached:
                    futures[item["url"]] = (
                        item,
                        {
                            "url": item["url"],
                            "content": cached,
                            "transport": transport,
                        },
                        None,
                    )
                else:
                    future = executor.submit(
                        fetch_page,
                        item["url"],
                        transport,
                    )
                    futures[future] = item

            results = []

            for key, value in list(futures.items()):
                if isinstance(key, str):
                    item, result, error = value
                    results.append((item, result, error))

            future_keys = [
                key for key in futures
                if not isinstance(key, str)
            ]

            for future in concurrent.futures.as_completed(future_keys):
                item = futures[future]

                try:
                    result, error = future.result()
                except Exception as exc:
                    result, error = None, str(exc)

                results.append((item, result, error))

            for item, result, error in results:
                pages_scanned += 1

                if not result:
                    if error:
                        page_errors.append(
                            f"{item['url']}: {error}"
                        )
                    continue

                real_url = result["url"]

                docs, products, links = parse_page(
                    real_url,
                    result["content"],
                )

                for document in docs:
                    documents_by_url[document["url"]] = document

                for product in products:
                    existing = products_by_image.get(
                        product["image_url"]
                    )

                    if (
                        existing is None
                        or len(product["title"])
                        > len(existing["title"])
                    ):
                        products_by_image[
                            product["image_url"]
                        ] = product

                if item["depth"] >= MAX_DEPTH:
                    continue

                links.sort(
                    key=lambda link: link["score"],
                    reverse=True,
                )

                for link in links:
                    add_to_queue(
                        link["url"],
                        item["depth"] + 1,
                        link["score"],
                    )

    documents = list(documents_by_url.values())
    products = list(products_by_image.values())

    documents.sort(
        key=lambda item: (
            any(str(year) in item["title"] for year in TARGET_YEARS),
            item["title"],
        ),
        reverse=True,
    )

    products.sort(key=lambda item: item["title"].lower())

    return {
        "site_url": start_url,
        "domain": domain,
        "transport": transport,
        "documents": documents,
        "products": products,
        "pages_scanned": pages_scanned,
        "errors": page_errors[:20],
    }


# =========================================================
# СКАЧИВАНИЕ И ВАЛИДАЦИЯ ИЗОБРАЖЕНИЙ
# =========================================================

def request_binary(url: str, referer: str = ""):
    headers = dict(HEADERS)

    if referer:
        headers["Referer"] = referer

    host = urllib.parse.urlparse(url).netloc.lower()
    use_curl_first = HAS_CURL and host.endswith((".by", ".kz"))

    order = ["curl", "requests"] if use_curl_first else ["requests", "curl"]

    if not HAS_CURL:
        order = ["requests"]

    for transport in order:
        try:
            if transport == "curl":
                response = curl_requests.get(
                    url,
                    headers=headers,
                    impersonate="chrome",
                    timeout=12,
                    verify=False,
                    allow_redirects=True,
                )
            else:
                response = get_thread_session().get(
                    url,
                    headers=headers,
                    timeout=(4, 12),
                    allow_redirects=True,
                )

            if response.status_code != 200:
                continue

            content = response.content

            if len(content) < 4000:
                continue

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if (
                "image" not in content_type
                and not re.search(
                    r"\.(jpg|jpeg|png|webp)(?:\?|$)",
                    url,
                    re.I,
                )
            ):
                continue

            return content

        except Exception:
            continue

    return None


def validate_downloaded_image(product: dict):
    data = request_binary(
        product["image_url"],
        product["source_page"],
    )

    if not data:
        return None

    extension = "jpg"
    width = None
    height = None

    if HAS_PIL:
        try:
            image = Image.open(io.BytesIO(data))
            width, height = image.size
            image_format = (image.format or "JPEG").lower()

            if image_format == "jpeg":
                image_format = "jpg"

            if image_format not in {"jpg", "png", "webp"}:
                image_format = "jpg"

            extension = image_format

            if width < 120 or height < 120:
                return None

            ratio = width / height

            # Отсекаются только очевидные баннеры и полосы.
            if ratio > 3.2 or ratio < 0.20:
                return None

        except Exception:
            return None

    result = dict(product)
    result.update(
        {
            "bytes": data,
            "ext": extension,
            "width": width,
            "height": height,
            "hash": hashlib.sha1(data).hexdigest(),
        }
    )

    return result


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value)
    value = re.sub(r"\s+", " ", value).strip(" ._-")

    return value[:80] or "Новогодний подарок"


def create_products_zip(products: list, domain: str):
    validated = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=IMAGE_WORKERS
    ) as executor:
        for item in executor.map(
            validate_downloaded_image,
            products[:700],
        ):
            if item:
                validated.append(item)

    unique = []
    hashes = set()

    for item in validated:
        if item["hash"] in hashes:
            continue

        hashes.add(item["hash"])
        unique.append(item)

    zip_buffer = io.BytesIO()
    manifest_buffer = io.StringIO()
    manifest_writer = csv.writer(manifest_buffer, delimiter=";")

    manifest_writer.writerow(
        [
            "Название",
            "Вес",
            "Страница товара",
            "Изображение",
            "Имя файла",
        ]
    )

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:
        for index, product in enumerate(unique, start=1):
            filename = (
                f"{index:03d}_"
                f"{safe_filename(product['title'])}."
                f"{product['ext']}"
            )

            archive.writestr(filename, product["bytes"])

            manifest_writer.writerow(
                [
                    product["title"],
                    product.get("weight") or "",
                    product["product_url"],
                    product["image_url"],
                    filename,
                ]
            )

        archive.writestr(
            "catalog.csv",
            "\ufeff" + manifest_buffer.getvalue(),
        )

    return zip_buffer.getvalue(), len(unique)


# =========================================================
# ИНТЕРФЕЙС
# =========================================================

company_input = st.text_input(
    "Введите только название компании:",
    placeholder=(
        "Например: Коммунарка, Спартак, Рахат, "
        "Баян Сулу, Рубин, неизвестная компания..."
    ),
)

search_clicked = st.button(
    "🚀 НАЙТИ КАТАЛОГИ И ПОДАРОЧНЫЕ НАБОРЫ",
    type="primary",
    use_container_width=True,
)

if search_clicked:
    if not company_input.strip():
        st.warning("Введите название компании.")
    else:
        st.session_state.pop("catalog_zip", None)
        st.session_state.pop("catalog_zip_count", None)

        with st.spinner(
            "Определяем официальный сайт компании..."
        ):
            connection, connection_errors = resolve_company(
                company_input
            )

        if not connection:
            st.session_state["analysis_result"] = None
            st.error(
                "Не удалось определить или открыть официальный сайт "
                "компании."
            )

            with st.expander("Техническая диагностика"):
                if connection_errors:
                    for error in connection_errors:
                        st.code(error)
                else:
                    st.write("Диагностических данных нет.")
        else:
            st.success(
                f"🌐 Найден сайт: {connection['url']}  \n"
                f"Сетевой режим: `{connection['transport']}`"
            )

            with st.spinner(
                "Обходим категории, пагинацию и карточки товаров..."
            ):
                analysis_result = crawl_site(connection)

            analysis_result["query"] = company_input.strip()
            st.session_state["analysis_result"] = analysis_result

result = st.session_state.get("analysis_result")

if result and result.get("query") == company_input.strip():
    documents = result["documents"]
    products = result["products"]

    st.markdown("---")
    st.success(
        f"Обработано страниц: **{result['pages_scanned']}**. "
        f"Найдено каталогов: **{len(documents)}**. "
        f"Найдено целевых наборов/коробок: **{len(products)}**."
    )

    document_column, product_column = st.columns([1, 1.25])

    with document_column:
        st.subheader(
            f"📄 Каталоги {CURRENT_YEAR}–{NEXT_YEAR}"
        )

        if not documents:
            st.info(
                "Подходящие PDF/Excel-каталоги не обнаружены."
            )

        for document in documents:
            title = html_module.escape(document["title"])
            url = html_module.escape(
                document["url"],
                quote=True,
            )

            icon = (
                "📕 PDF"
                if ".pdf" in document["url"].lower()
                else "📊 EXCEL"
            )

            st.markdown(
                f"""
                <div class="doc-card">
                    <div><b>{icon} — {title}</b></div>
                    <a href="{url}" target="_blank"
                       class="doc-button">
                       📥 ОТКРЫТЬ КАТАЛОГ
                    </a>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with product_column:
        st.subheader(
            f"📦 Наборы и коробки ({len(products)})"
        )

        if not products:
            st.info(
                "Целевые подарочные наборы и коробки не обнаружены."
            )
        else:
            if st.button(
                "📦 ПОДГОТОВИТЬ ZIP С ИЗОБРАЖЕНИЯМИ",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner(
                    "Скачиваем и проверяем изображения..."
                ):
                    zip_data, archive_count = create_products_zip(
                        products,
                        result["domain"],
                    )

                st.session_state["catalog_zip"] = zip_data
                st.session_state[
                    "catalog_zip_count"
                ] = archive_count

            zip_data = st.session_state.get("catalog_zip")
            archive_count = st.session_state.get(
                "catalog_zip_count",
                0,
            )

            if zip_data:
                st.download_button(
                    label=(
                        f"⬇️ СКАЧАТЬ ZIP "
                        f"({archive_count} изображений)"
                    ),
                    data=zip_data,
                    file_name=(
                        f"{result['domain']}_"
                        f"new_year_{CURRENT_YEAR}_"
                        f"{NEXT_YEAR}.zip"
                    ),
                    mime="application/zip",
                    use_container_width=True,
                )

    if products:
        st.markdown("---")
        st.subheader("Предварительный просмотр")

        preview_products = products[:40]
        columns = st.columns(4)

        for index, product in enumerate(preview_products):
            with columns[index % 4]:
                title = html_module.escape(
                    product["title"]
                )

                weight_html = ""
                if product.get("weight"):
                    weight_html = (
                        '<span class="badge-weight">'
                        f'⚖️ {html_module.escape(product["weight"])}'
                        "</span>"
                    )

                st.image(
                    product["image_url"],
                    use_container_width=True,
                )

                st.markdown(
                    f"""
                    <div class="product-title">{title}</div>
                    <span class="badge-box">
                        🎁 НАБОР / КОРОБКА
                    </span>
                    {weight_html}
                    """,
                    unsafe_allow_html=True,
                )

                if product.get("product_url"):
                    st.link_button(
                        "Открыть товар",
                        product["product_url"],
                        use_container_width=True,
                    )

    if result["errors"]:
        with st.expander(
            "Необязательная диагностика пропущенных страниц"
        ):
            for error in result["errors"]:
                st.code(error)

st.divider()
st.caption(
    f"«Первый Снег» · Каталоги сезонов "
    f"{CURRENT_YEAR}–{NEXT_YEAR} · "
    f"Строгая фильтрация одиночных конфет активна."
)
