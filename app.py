import concurrent.futures
import datetime
import io
import re
import time
import urllib.parse
import zipfile

import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# =========================================================
# ❄️ НАСТРОЙКИ И ДИЗАЙН
# =========================================================

CURRENT_YEAR = datetime.date.today().year
NEXT_YEAR = CURRENT_YEAR + 1
TARGET_YEARS = {CURRENT_YEAR, NEXT_YEAR, NEXT_YEAR + 1}

MAX_PAGES = 40
PAGE_WORKERS = 4

st.set_page_config(page_title="Первый Снег | Поиск каталогов", page_icon="❄️", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }
    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: white !important; font-weight: 900;
        padding: 8px 18px; border-radius: 8px; border: 2px solid white;
        box-shadow: 0 4px 12px rgba(220,38,38,0.30); letter-spacing: 1px;
    }
    .doc-card {
        background-color: white; border-left: 6px solid #dc2626;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }
    .doc-button {
        display: inline-block; background-color: #dc2626; color: white !important;
        font-weight: 700; padding: 9px 18px; margin-top: 8px;
        border-radius: 7px; text-decoration: none;
    }
    .product-title {
        min-height: 42px; margin: 5px 0; color: #1e293b;
        font-size: 13px; font-weight: 700; line-height: 1.3;
    }
    .badge-box {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background-color: #16a34a; color: white; font-size: 11px; font-weight: 700;
    }
    .badge-weight {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background-color: #dc2626; color: white; font-size: 11px; font-weight: 700;
    }
    .candidate-item { padding: 4px 0; font-size: 13px; }
    </style>
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    """,
    unsafe_allow_html=True,
)

st.title("📦 Поиск каталогов и подарочных наборов")
st.caption("Работает как поисковик: находит официальный сайт по названию компании, затем собирает PDF-каталоги и коробки (картон / МГК / тубы). Одиночные конфеты, жесть и текстиль отсеиваются.")

# =========================================================
# 🎯 БАЗА ИЗВЕСТНЫХ КОМПАНИЙ (ПРОВЕРЕННЫЕ АДРЕСА)
# =========================================================

EXPERT_DIRECTORY = {
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocolate-academy.ru",
    "рахат": "https://rakhat.kz",
    "баян сулу": "https://www.bayansulu.kz",
    "акконд": "https://akkond.ru",
    "лаконд": "https://lakond.ru",
    "донко": "https://donko.su",
    "дилявер": "https://dilaver.ru",
    "главупак": "https://glavupak.ru",
    "дедморозов": "https://dedmorozov.ru",
    "славянка": "https://slavyanka.ru",
    "миракс": "https://mirax-gifts.ru",
    "москондитер": "https://mosconditer.ru",
    "росшоколад": "https://roschocolate.ru",
    "рэйд": "https://podarki-reid21.ru",
    "конфешн": "https://confashion.ru",
    "тореро": "https://torero.ru",
}

START_PATHS = {
    "kommunarka.by": ["/catalog/novogodnie-podarki/", "/catalog/"],
    "spartak.by": ["/catalog/novogodnyaya-produktsiya/", "/catalog/"],
    "rubin-2000.ru": ["/catalog/"],
    "chocolate-academy.ru": ["/catalog/novogodnie-podarki/", "/catalog/"],
    "rakhat.kz": ["/products/novogodnie-podarki/", "/products/"],
    "bayansulu.kz": ["/ru/catalog/", "/catalog/"],
}

# =========================================================
# 📦 СЛОВАРИ ФИЛЬТРАЦИИ
# =========================================================

TARGET_BOX_WORDS = [
    "набор", "подарок", "подарки", "упаковк", "коробк", "туб", "тубус",
    "сундуч", "домик", "книг", "футляр", "шкатулк", "баульч", "чемоданчик",
    "картон", "микрогофр", "гофро", "мгк", "переплет", "переплёт", "кашир",
    "комплект", "сладкий подарок",
]

EXCLUDE_SINGLE_CANDIES = [
    "конфета", "конфеты весовые", "батончик", "плитка шоколада", "шоколадка",
    "драже", "карамелька", "вафля", "вафли", "печенье", "зефир", "ирис",
    "мармелад весовой", "поштучно",
]

EXCLUDE_MATERIALS = [
    "жесть", "жестяная", "металл", "текстиль", "ткань", "мешок", "мешочек",
    "рюкзак", "подушка", "плюш", "мягкая игрушка", "дерево", "фанера", "пластик", "пвх",
]

JUNK_IMAGE_WORDS = [
    "logo", "icon", "banner", "slider", "sprite", "placeholder", "social",
    "avatar", "payment", "delivery", "header", "footer", "menu", "arrow",
    "captcha", "counter", "metrika", "favicon",
]

JUNK_DOCUMENT_WORDS = [
    "презентация", "соглашение", "политика", "конфиденциальность", "персональные",
    "договор", "оферта", "вакансии", "реквизиты", "cookies", "устав",
    "инвесторам", "соут", "privacy", "policy",
]

DOCUMENT_WORDS = ["каталог", "catalog", "прайс", "price", "новогод", "подарки", "gift"]

WEIGHT_REGEX = re.compile(r"(\d+(?:[.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE)

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ
# =========================================================

def create_http_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    session.verify = False
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504], raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = create_http_session()


def safe_fetch(url, timeout=(10, 20)):
    try:
        resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 300:
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.url, resp.text, None
        return None, None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, None, str(e)


def connect_sequentially(target_url):
    """Последовательная проверка: точный адрес → www → http. Без SYN-флуда."""
    final_url, html, err = safe_fetch(target_url)
    if html:
        return final_url, html, [f"{target_url}: OK"]

    parsed = urllib.parse.urlparse(target_url)
    host = parsed.netloc.replace("www.", "") or target_url.split("/")[0]

    variants = [
        f"https://www.{host}/",
        f"https://{host}/",
        f"http://www.{host}/",
        f"http://{host}/",
    ]

    errors = [f"{target_url}: {err}"]
    for variant in variants:
        if variant.rstrip("/") == str(target_url).rstrip("/"):
            continue
        time.sleep(0.4)
        final_url, html, err = safe_fetch(variant)
        if html:
            return final_url, html, errors
        errors.append(f"{variant}: {err}")

    return None, None, errors


def fix_url(base_url, href):
    href = (href or "").strip()
    if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return ""
    if href.startswith("//"):
        href = "https:" + href
    full = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(full)
    safe_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:@-._~")
    safe_query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&?+/:,@-._~")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, safe_query, ""))


# =========================================================
# 🔎 ПОИСКОВЫЙ ДВИЖОК (КАК У ПОИСКОВИКА)
# =========================================================

def transliterate(text):
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    return "".join(table.get(c, c) for c in text.lower())

# Хосты, которые НЕ являются официальными сайтами компаний
NON_OFFICIAL_HOSTS = [
    "wikipedia", "wiktionary", "vk.com", "vkontakte", "ok.ru", "youtube", "youtu.be",
    "instagram", "facebook", "tiktok", "telegram", "t.me", "twitter", "x.com",
    "avito", "wildberries", "ozon.ru", "market.yandex", "aliexpress", "tiu.ru",
    "prom.ua", "olx", "flamp", "2gis", "yandex.", "google.", "youtube",
    "rusprofile", "checko", "audit-it", "list-org", "sbis", "kontur",
    "zachestnyibiznes", "rbc.companies", "kartoteka", "rptak", "zakupki",
    "orgpage", "company ", "biznes", "firmy", "spravnik", "yell", "zoon",
    "pinterest", "dzen.ru", "livejournal", "habr", "pikabu", "otzovic",
    "otzovik", "irecommend", "flamp", "google maps", "gmaps",
]

GOOD_TLDS = (".ru", ".рф", ".by", ".kz", ".com", ".su", ".kg", ".am", ".uz")


def score_candidate(url, company_name):
    """Оценка: насколько URL похож на официальный сайт компании"""
    host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    if not host:
        return -1000

    for junk in NON_OFFICIAL_HOSTS:
        if junk in host:
            return -1000

    slug = transliterate(company_name)
    words = [w for w in slug.replace("-", " ").split() if len(w) >= 3]
    # Склеенный и слитный вариант названия: "академияшоколада", "abinex"
    joined = "".join(words)
    first_word = words[0] if words else ""

    score = 0
    if slug and slug[:10] in host.replace("-", ""):
        score += 60
    if joined and len(joined) >= 5 and joined in host.replace("-", ""):
        score += 60
    if first_word and first_word in host.replace("-", ""):
        score += 35
    if host.endswith(GOOD_TLDS):
        score += 10
    if "opt" in host or "podarki" in host or "gift" in host or "upak" in host:
        score += 5

    return score


def search_via_ddgs_lib(query):
    """Метод 1: библиотека ddgs"""
    if not HAS_DDGS:
        return []
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, region="ru-ru", max_results=12)
            return [
                (item.get("href") or item.get("url") or "")
                for item in results
                if item.get("href") or item.get("url")
            ]
    except Exception:
        return []


def search_via_ddg_html(query):
    """Метод 2: HTML-выдача DuckDuckGo (работает без библиотек)"""
    try:
        resp = SESSION.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=(8, 15),
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        urls = []
        for a in soup.select("a.result__a, a.result__url"):
            href = a.get("href", "")
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if "uddg" in parsed:
                    href = parsed["uddg"][0]
            if href.startswith("http"):
                urls.append(href)
        return urls
    except Exception:
        return []


def search_via_yandex_html(query):
    """Метод 3: резерв — HTML-выдача Яндекса"""
    try:
        resp = SESSION.get(
            "https://yandex.ru/search/",
            params={"text": query},
            timeout=(8, 15),
        )
        if resp.status_code != 200 or "captcha" in resp.text.lower():
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "yandex" not in href and "ya.ru" not in href:
                urls.append(href)
        return urls[:12]
    except Exception:
        return []


def is_site_relevant(html_text, company_name):
    """Проверка, что найденный сайт действительно про компанию/подарки"""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = (soup.get_text(" ", strip=True) + " " + (soup.title.get_text() if soup.title else "")).lower()
        host_slug = transliterate(company_name)
        words = [w for w in host_slug.replace("-", " ").split() if len(w) >= 4]

        # Название компании на сайте (в любом виде)
        if any(w in text for w in words):
            return True
        # Либо тематика подарков/упаковки
        if any(k in text for k in ["подар", "упаков", "каталог", "набор", "короб"]):
            return True
    except Exception:
        pass
    return False


def search_official_site(company_name):
    """
    Полный цикл: запрос к поисковикам → ранжирование → верификация.
    Возвращает (url, список кандидатов для показа).
    """
    query = f"{company_name} официальный сайт"

    # 1. Собираем кандидатов из всех доступных поисковиков
    raw_urls = []
    raw_urls.extend(search_via_ddgs_lib(query))
    if not raw_urls:
        raw_urls.extend(search_via_ddg_html(query))
    if not raw_urls:
        raw_urls.extend(search_via_yandex_html(query))

    # Дополнительно: запрос без слова "официальный сайт"
    if not raw_urls:
        raw_urls.extend(search_via_ddgs_lib(company_name))

    # 2. Ранжирование и очистка
    scored = {}
    for url in raw_urls:
        host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
        if not host:
            continue
        s = score_candidate(url, company_name)
        if s <= -100:
            continue  # маркетплейс/справочник — выкидываем
        # Оставляем лучший URL для каждого хоста
        if host not in scored or s > scored[host][0]:
            scored[host] = (s, url)

    candidates = sorted(scored.values(), key=lambda x: x[0], reverse=True)
    candidate_list = [url for _, url in candidates[:6]]

    display_candidates = [
        {"url": url, "score": s, "status": "в очереди"}
        for s, url in candidates[:6]
    ]

    # 3. Верификация по очереди: открываем и проверяем релевантность
    for i, url in enumerate(candidate_list):
        final_url, html, _ = safe_fetch(url, timeout=(8, 15))
        if not html:
            display_candidates[i]["status"] = "недоступен"
            continue
        if is_site_relevant(html, company_name):
            display_candidates[i]["status"] = "✅ принят"
            return final_url, display_candidates
        display_candidates[i]["status"] = "не по теме"

    return None, display_candidates


def resolve_site_url(company_input):
    """Главная точка входа: имя компании → официальный сайт"""
    q = company_input.lower().strip()

    # 1. Уже готовый URL
    if q.startswith(("http://", "https://")):
        return q, None, "прямой адрес"
    if "." in q and " " not in q:
        return f"https://{q}", None, "прямой адрес"

    # 2. База известных компаний (без учета регистра и лишних слов)
    for key, url in EXPERT_DIRECTORY.items():
        if key in q:
            return url, None, f"база компаний ({key})"

    # 3. Поисковик — как настоящий поисковый запрос
    url, candidates = search_official_site(company_input)
    if url:
        return url, candidates, "найден через поисковик"

    # 4. Крайний резерв: транслитерация (только если поисковики молчат)
    slug = transliterate(q)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"https://{slug}.ru", candidates, "резервный подбор домена (поисковик недоступен)"


# =========================================================
# 🔍 ФИЛЬТРАЦИЯ НАБОРОВ / УПАКОВКИ
# =========================================================

def is_box_or_set(title, context_text, url):
    combined = f"{title} {context_text} {url}".lower()

    if any(bad in combined for bad in EXCLUDE_MATERIALS):
        return False

    has_single = any(single in combined for single in EXCLUDE_SINGLE_CANDIES)
    has_box = any(box in combined for box in TARGET_BOX_WORDS)

    if has_single and not has_box:
        return False

    return has_box or "podar" in url.lower() or "novogod" in url.lower()


def scan_single_page(url, domain):
    _, html, _ = safe_fetch(url, timeout=(8, 15))
    if not html:
        return [], []

    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("script, style, footer, header, nav"):
        junk.decompose()

    page_context = (soup.title.get_text(" ", strip=True) if soup.title else "") + " " + url

    pdfs, imgs = [], []

    # PDF / Excel каталоги
    for a in soup.find_all("a", href=True):
        href = fix_url(url, a["href"])
        if href.lower().split("?")[0].endswith((".pdf", ".xlsx", ".xls")):
            text = a.get_text().strip()
            comb = f"{text} {href}".lower()
            if any(bad in comb for bad in JUNK_DOCUMENT_WORDS):
                continue
            if any(good in comb for good in DOCUMENT_WORDS):
                pdfs.append({"name": text or "Официальный каталог PDF", "url": href})

    # Картинки наборов / коробок
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not src:
            continue

        full_img = fix_url(url, src)
        if not full_img or any(j in full_img.lower() for j in JUNK_IMAGE_WORDS):
            continue

        alt = (img.get("alt") or img.get("title") or "").strip()
        parent_text = (img.parent.get_text(" ", strip=True) if img.parent else "")[:300]
        title = alt or parent_text[:60] or "Подарочный набор"

        if is_box_or_set(title, parent_text + " " + page_context, full_img):
            weight_match = WEIGHT_REGEX.search(parent_text + " " + title)
            imgs.append({
                "title": title[:100],
                "weight": weight_match.group(1) if weight_match else None,
                "url": full_img,
                "page_url": url,
            })

    return pdfs, imgs


def deep_scan_site(start_url):
    domain = urllib.parse.urlparse(start_url).netloc.replace("www.", "")

    final_start_url, main_html, errors = connect_sequentially(start_url)
    if not main_html:
        return None, None, 0, errors

    soup = BeautifulSoup(main_html, "lxml")

    pages_to_scan = {final_start_url}
    for path in START_PATHS.get(domain, ["/catalog/"]):
        pages_to_scan.add(urllib.parse.urljoin(final_start_url, path))

    for a in soup.find_all("a", href=True):
        href = fix_url(final_start_url, a["href"])
        if href and urllib.parse.urlparse(href).netloc.replace("www.", "") == domain:
            txt = (a.get_text() + " " + href).lower()
            if any(k in txt for k in [
                "catalog", "novogod", "podarki", "karton", "tuba", "upakov",
                "2025", "2026", "2027", "product", "gift",
            ]):
                pages_to_scan.add(href)

    scan_queue = list(pages_to_scan)[:MAX_PAGES]

    all_pdfs, all_imgs = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=PAGE_WORKERS) as executor:
        futures = [executor.submit(scan_single_page, url, domain) for url in scan_queue]
        for f in concurrent.futures.as_completed(futures):
            try:
                p, i = f.result()
                all_pdfs.extend(p)
                all_imgs.extend(i)
            except Exception:
                continue

    unique_pdfs = list({item["url"]: item for item in all_pdfs}.values())
    unique_imgs = list({item["url"]: item for item in all_imgs}.values())
    return unique_pdfs, unique_imgs, len(scan_queue), None


# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

company_input = st.text_input(
    "Введите название компании:",
    placeholder="Например: Абинекс, Коммунарка, Спартак, Рахат, Рубин...",
)

if st.button("🚀 НАЙТИ КАТАЛОГИ И ПОДАРОЧНЫЕ НАБОРЫ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.warning("Введите название компании.")
        st.stop()

    st.session_state.pop("scan_done", None)

    with st.spinner("Ищем официальный сайт через поисковую систему..."):
        target_url, candidates, method = resolve_site_url(company_input)

    st.info(f"🌐 Целевой сайт: **{target_url}**  \nСпособ определения: {method}")

    # Показать кандидатов из поисковой выдачи (прозрачность)
    if candidates:
        with st.expander("🔍 Что нашел поисковик (кандидаты)"):
            for c in candidates:
                st.markdown(
                    f"<div class='candidate-item'>{c['status']} — "
                    f"<a href='{c['url']}' target='_blank'>{c['url']}</a></div>",
                    unsafe_allow_html=True,
                )

    with st.spinner("Сканируем разделы каталога, пагинацию и карточки товаров..."):
        pdfs, imgs, pages_count, errors = deep_scan_site(target_url)

    if pdfs is None and imgs is None:
        st.error(f"❌ Сайт {target_url} не отвечает. Попробуйте уточнить название или ввести адрес вручную.")
        if errors:
            with st.expander("Техническая диагностика"):
                for err in errors:
                    st.code(err)
    else:
        st.success(f"✅ Обработано страниц: **{pages_count}**")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader(f"📄 PDF / Excel Каталоги ({len(pdfs)})")
            if pdfs:
                for doc in pdfs:
                    st.markdown(
                        f"""
                        <div class="doc-card">
                            <div><b>📕 {doc['name']}</b></div>
                            <a href="{doc['url']}" target="_blank" class="doc-button">📥 СКАЧАТЬ КАТАЛОГ</a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("PDF-каталоги не обнаружены.")

        with col2:
            st.subheader(f"📦 Подарочные наборы и коробки ({len(imgs)})")
            if imgs:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx, item in enumerate(imgs[:400], start=1):
                        try:
                            res = SESSION.get(item["url"], timeout=8)
                            if res.status_code == 200:
                                clean_title = re.sub(r"[^\w\-]+", "_", item["title"])[:35] or "item"
                                ext = "jpg"
                                if ".png" in item["url"].lower():
                                    ext = "png"
                                elif ".webp" in item["url"].lower():
                                    ext = "webp"
                                zf.writestr(f"box_{idx:03d}_{clean_title}.{ext}", res.content)
                        except Exception:
                            continue

                st.download_button(
                    f"📥 СКАЧАТЬ ZIP С НАБОРАМИ ({len(imgs)} шт.)",
                    data=zip_buffer.getvalue(),
                    file_name="gift_boxes_catalog.zip",
                    mime="application/zip",
                    type="primary",
                )

                st.write("---")
                grid = st.columns(3)
                for idx, item in enumerate(imgs[:9]):
                    with grid[idx % 3]:
                        st.markdown(
                            f"""
                            <div style="text-align:center;">
                                <div class="product-title">{item['title']}</div>
                                <span class="badge-box">🎁 НАБОР / КОРОБКА</span>
                                {f'<span class="badge-weight">⚖️ {item["weight"]}</span>' if item['weight'] else ''}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.image(item["url"], use_container_width=True)
            else:
                st.info("Подарочные наборы и коробки не найдены.")

st.divider()
st.caption("Инструмент «Первый Снег» | Поиск официального сайта через поисковую систему | Фильтрация одиночных конфет активна.")
