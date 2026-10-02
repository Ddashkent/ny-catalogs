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
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =========================================================
# НАСТРОЙКИ
# =========================================================

CURRENT_YEAR = datetime.date.today().year
TARGET_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1, CURRENT_YEAR + 2}

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
        box-shadow: 0 4px 12px rgba(220,38,38,.3); letter-spacing: 1px;
    }
    .doc-card {
        background: white; border-left: 6px solid #dc2626; border-radius: 10px;
        padding: 16px; margin-bottom: 12px; box-shadow: 0 4px 10px rgba(0,0,0,.04);
    }
    .doc-button {
        display: inline-block; background: #dc2626; color: white !important;
        font-weight: 700; padding: 9px 18px; margin-top: 8px;
        border-radius: 7px; text-decoration: none;
    }
    .product-title {
        min-height: 40px; margin: 6px 0; color: #1e293b;
        font-size: 13px; font-weight: 700; line-height: 1.3;
    }
    .badge-box {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background: #16a34a; color: white; font-size: 11px; font-weight: 700;
    }
    .badge-weight {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background: #dc2626; color: white; font-size: 11px; font-weight: 700;
    }
    .cand-ok { color:#16a34a; font-weight:700; }
    .cand-bad { color:#94a3b8; }
    </style>
    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    """,
    unsafe_allow_html=True,
)

st.title("🔎 Поиск официальных сайтов и новогодних каталогов")
st.caption(
    "Сайт компании находится через поисковые системы и проверяется по содержимому. "
    "Затем собираются PDF-каталоги и подарочные наборы в картонной упаковке, МГК и тубах."
)


# =========================================================
# СЕТЬ
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def create_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504], raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=12, pool_maxsize=12)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


SESSION = create_session()


def fetch(url, timeout=(10, 25)):
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 300:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.url, r.text, None
        return None, None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, None, str(e)


def connect_sequentially(url):
    """Проверка адресов по очереди, без параллельного флуда (иначе WAF рубит соединение)."""
    final, html, err = fetch(url)
    if html:
        return final, html, None

    p = urllib.parse.urlparse(url if url.startswith("http") else "https://" + url)
    host = p.netloc.replace("www.", "") or p.path.split("/")[0]
    variants = [f"https://www.{host}/", f"https://{host}/", f"http://www.{host}/", f"http://{host}/"]

    errors = [f"{url}: {err}"]
    for v in variants:
        if v.rstrip("/") == url.rstrip("/"):
            continue
        time.sleep(0.35)
        final, html, err = fetch(v)
        if html:
            return final, html, None
        errors.append(f"{v}: {err}")
    return None, None, errors


# =========================================================
# ПОИСКОВЫЙ СЛОЙ (НАСТОЯЩИЙ ПОИСК, А НЕ ПОДСТАНОВКА .RU)
# =========================================================

BLOCKED_HOSTS = [
    "wildberries.", "ozon.", "market.yandex.", "yandex.", "avito.", "aliexpress.",
    "vk.com", "ok.ru", "facebook.", "instagram.", "youtube.", "t.me", "telegram.",
    "wikipedia.", "2gis.", "zoon.", "rusprofile.", "list-org.", "sbis.ru",
    "tiu.ru", "pulscen.", "flagma.", "satu.kz", "prom.ua", "blizko.",
    "hh.ru", "rabota.", "dzen.ru", "pinterest.", "google.", "bing.", "mojeek.",
    "duckduckgo.", "mail.ru", "rambler.", "tutu.", "spark-interfax",
]


def is_blocked_host(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(b in host for b in BLOCKED_HOSTS)


def _extract_links(html, base):
    """Достаёт внешние ссылки из HTML выдачи любого движка."""
    out = []
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # DuckDuckGo оборачивает ссылки в редирект
        if "uddg=" in href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in q:
                href = q["uddg"][0]
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            continue
        if is_blocked_host(href):
            continue
        out.append(href)
    return out


def search_mojeek(query):
    u = "https://www.mojeek.com/search?q=" + urllib.parse.quote(query)
    _, html, _ = fetch(u, timeout=(8, 15))
    return _extract_links(html, u) if html else []


def search_ddg_html(query):
    u = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    _, html, _ = fetch(u, timeout=(8, 15))
    return _extract_links(html, u) if html else []


def search_ddg_lite(query):
    u = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    _, html, _ = fetch(u, timeout=(8, 15))
    return _extract_links(html, u) if html else []


def search_bing(query):
    u = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=ru"
    _, html, _ = fetch(u, timeout=(8, 15))
    return _extract_links(html, u) if html else []


SEARCH_ENGINES = [
    ("Mojeek", search_mojeek),
    ("DuckDuckGo", search_ddg_html),
    ("DuckDuckGo Lite", search_ddg_lite),
    ("Bing", search_bing),
]


def root_url(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def web_search_candidates(company, log):
    queries = [
        f"{company} официальный сайт новогодние подарки каталог",
        f"{company} новогодние подарки упаковка оптом",
        f"{company} официальный сайт",
    ]

    seen_hosts, candidates = set(), []

    for engine_name, engine in SEARCH_ENGINES:
        for q in queries:
            try:
                links = engine(q)
            except Exception:
                links = []
            if links:
                log.append(f"{engine_name}: «{q}» → {len(links)} ссылок")
            for link in links:
                host = urllib.parse.urlparse(link).netloc.lower().replace("www.", "")
                if not host or host in seen_hosts:
                    continue
                seen_hosts.add(host)
                candidates.append(root_url(link))
            if len(candidates) >= 12:
                break
        if len(candidates) >= 12:
            break

    return candidates[:12]


# =========================================================
# ПРОВЕРКА КАНДИДАТА ПО СОДЕРЖИМОМУ
# =========================================================

NY_WORDS = ["новогод", "новый год", "рождеств", "дед мороз", "christmas", "new year", "символ года"]
GIFT_WORDS = ["подарок", "подарки", "подарочн", "набор", "сладкий подарок", "ассорти"]
PACK_WORDS = ["картон", "микрогофр", "гофр", "мгк", "переплет", "переплёт", "кашир",
              "туба", "тубус", "коробка", "упаковка", "футляр", "шкатулка", "сундучок"]
WRONG_INDUSTRY = ["металлопрокат", "арматура", "швеллер", "бетон", "кирпич", "недвижим",
                  "автосервис", "шины", "ювелир", "окна пвх", "кровля", "сантехник"]


def translit(text):
    m = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i",
         "й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t",
         "у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"",
         "э":"e","ю":"yu","я":"ya"}
    return re.sub(r"[^a-z0-9]+", "", "".join(m.get(c, c) for c in text.lower()))


def score_candidate(company, url):
    final_url, html, _ = fetch(url, timeout=(7, 15))
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = (title + " " + soup.get_text(" ", strip=True)[:120000]).lower().replace("ё", "е")
    host = urllib.parse.urlparse(final_url).netloc.lower()

    score = 0
    name_slug = translit(company)
    if name_slug and name_slug[:6] in translit(host):
        score += 25
    for w in company.lower().split():
        if len(w) >= 4 and w in text:
            score += 8

    ny = sum(6 for w in NY_WORDS if w in text)
    gift = sum(5 for w in GIFT_WORDS if w in text)
    pack = sum(3 for w in PACK_WORDS if w in text)
    score += min(ny, 30) + min(gift, 25) + min(pack, 18)

    if any(w in text for w in WRONG_INDUSTRY) and (ny + gift) == 0:
        score -= 60

    if ny + gift == 0:
        score -= 25

    return {"url": final_url, "title": title[:90] or host, "score": score, "host": host}


def find_official_site(company, log):
    candidates = web_search_candidates(company, log)

    # Если ввели домен или ссылку — работаем напрямую.
    q = company.strip().lower()
    if q.startswith("http") or ("." in q and " " not in q):
        direct = q if q.startswith("http") else "https://" + q
        candidates.insert(0, root_url(direct))

    if not candidates:
        return None, []

    scored = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda u: score_candidate(company, u), candidates):
            if res:
                scored.append(res)

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored and scored[0]["score"] > 10 else None
    return best, scored


# =========================================================
# ФИЛЬТРЫ ТОВАРОВ
# =========================================================

TARGET_BOX_WORDS = ["набор", "подарок", "подарки", "упаковк", "коробк", "туб", "тубус",
                    "сундуч", "домик", "книг", "футляр", "шкатулк", "чемоданчик",
                    "картон", "микрогофр", "гофро", "мгк", "переплет", "переплёт",
                    "кашир", "комплект", "сладкий подарок"]

EXCLUDE_SINGLE = ["конфета", "конфеты весовые", "батончик", "плитка шоколада", "шоколадка",
                  "драже", "карамелька", "вафля", "вафли", "печенье", "зефир", "ирис",
                  "мармелад весовой", "поштучно", "на развес"]

EXCLUDE_MATERIAL = ["жесть", "жестяная", "металл", "tin", "текстиль", "ткань", "мешок",
                    "мешочек", "рюкзак", "подушка", "плюш", "мягкая игрушка", "дерево",
                    "фанера", "пластик", "пвх"]

JUNK_IMG = ["logo", "icon", "banner", "slider", "sprite", "placeholder", "social", "avatar",
            "payment", "delivery", "header", "footer", "menu", "arrow", "captcha",
            "counter", "metrika", "favicon"]

JUNK_DOC = ["презентация", "соглашение", "политика", "конфиденциальн", "персональн",
            "договор", "оферта", "вакансии", "реквизиты", "cookies", "устав",
            "инвесторам", "соут", "privacy", "policy", "сертификат", "декларация"]

DOC_WORDS = ["каталог", "catalog", "прайс", "price", "новогод", "подарки", "gift"]

WEIGHT_RE = re.compile(r"(\d+(?:[.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.I)


def fix_url(base, href):
    href = (href or "").strip()
    if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return ""
    if href.startswith("//"):
        href = "https:" + href
    full = urllib.parse.urljoin(base, href)
    p = urllib.parse.urlparse(full)
    path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/:@-._~")
    query = urllib.parse.quote(urllib.parse.unquote(p.query), safe="=&?+/:,@-._~")
    return urllib.parse.urlunparse((p.scheme, p.netloc, path, p.params, query, ""))


def is_box_or_set(title, context, url):
    blob = f"{title} {context} {url}".lower().replace("ё", "е")
    if any(b in blob for b in EXCLUDE_MATERIAL):
        return False
    has_single = any(s in blob for s in EXCLUDE_SINGLE)
    has_box = any(b in blob for b in TARGET_BOX_WORDS)
    if has_single and not has_box:
        return False
    return has_box or "podar" in url.lower() or "novogod" in url.lower()


def scan_page(url):
    _, html, _ = fetch(url, timeout=(8, 18))
    if not html:
        return [], []

    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("script, style, noscript, footer, header, nav"):
        junk.decompose()

    page_ctx = (soup.title.get_text(" ", strip=True) if soup.title else "") + " " + url
    pdfs, imgs = [], []

    for a in soup.find_all("a", href=True):
        href = fix_url(url, a["href"])
        if href.lower().split("?")[0].endswith((".pdf", ".xlsx", ".xls")):
            text = " ".join(a.get_text().split())
            blob = f"{text} {urllib.parse.unquote(href)}".lower()
            if any(b in blob for b in JUNK_DOC):
                continue
            if any(g in blob for g in DOC_WORDS):
                pdfs.append({"name": text or "Каталог", "url": href})

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not src:
            continue
        full = fix_url(url, src)
        if not full or any(j in full.lower() for j in JUNK_IMG):
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)", full.lower()):
            continue

        alt = (img.get("alt") or img.get("title") or "").strip()
        parent_text = (img.parent.get_text(" ", strip=True) if img.parent else "")[:300]
        title = alt or parent_text[:60] or "Подарочный набор"

        if is_box_or_set(title, parent_text + " " + page_ctx, full):
            m = WEIGHT_RE.search(parent_text + " " + title)
            imgs.append({"title": title[:100], "weight": m.group(1) if m else None, "url": full})

    return pdfs, imgs


def deep_scan(site_url):
    final_url, html, errors = connect_sequentially(site_url)
    if not html:
        return None, None, 0, errors

    domain = urllib.parse.urlparse(final_url).netloc.replace("www.", "")
    soup = BeautifulSoup(html, "lxml")

    pages = {final_url}
    for path in ("/catalog/", "/products/", "/podarki/", "/novogodnie-podarki/"):
        pages.add(urllib.parse.urljoin(final_url, path))

    for a in soup.find_all("a", href=True):
        href = fix_url(final_url, a["href"])
        if href and urllib.parse.urlparse(href).netloc.replace("www.", "") == domain:
            blob = (a.get_text() + " " + href).lower()
            if any(k in blob for k in ["catalog", "katalog", "novogod", "podarki", "karton",
                                       "tuba", "upakov", "product", "gift"] + [str(y) for y in TARGET_YEARS]):
                pages.add(href)

    queue = list(pages)[:MAX_PAGES]
    all_pdfs, all_imgs = [], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        for p, i in ex.map(scan_page, queue):
            all_pdfs.extend(p)
            all_imgs.extend(i)

    pdfs = list({d["url"]: d for d in all_pdfs}.values())
    imgs = list({d["url"]: d for d in all_imgs}.values())
    return pdfs, imgs, len(queue), None


# =========================================================
# ИНТЕРФЕЙС
# =========================================================

company = st.text_input("Введите название компании:", placeholder="Абинекс, Коммунарка, Рубин, Рахат…")

if st.button("🚀 НАЙТИ САЙТ И СОБРАТЬ КАТАЛОГИ", type="primary", use_container_width=True):
    if not company.strip():
        st.warning("Введите название компании.")
        st.stop()

    log = []
    with st.spinner("Ищем официальный сайт в поисковых системах…"):
        best, scored = find_official_site(company.strip(), log)

    if not best:
        st.error("Официальный сайт не найден или не подтверждён по содержимому.")
        with st.expander("Диагностика поиска"):
            for line in log:
                st.write(line)
            for c in scored:
                st.write(f"{c['url']} — баллы {c['score']} — {c['title']}")
        st.stop()

    st.success(f"🌐 Официальный сайт: **{best['url']}**  \n{best['title']}  \nРелевантность: {best['score']}")

    others = [c for c in scored[1:6] if c["score"] > 0]
    if others:
        with st.expander("Другие найденные кандидаты"):
            for c in others:
                st.markdown(f"- [{c['host']}]({c['url']}) — баллы {c['score']} — {c['title']}")

    with st.spinner("Обходим каталог и собираем наборы…"):
        pdfs, imgs, pages_count, errors = deep_scan(best["url"])

    if pdfs is None:
        st.error("Сайт найден, но не отвечает на запросы.")
        with st.expander("Диагностика соединения"):
            for e in errors or []:
                st.code(e)
        st.stop()

    st.info(f"Обработано страниц: **{pages_count}**")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"📄 Каталоги PDF / Excel ({len(pdfs)})")
        if pdfs:
            for d in pdfs:
                st.markdown(
                    f'<div class="doc-card"><b>📕 {d["name"]}</b><br>'
                    f'<a class="doc-button" href="{d["url"]}" target="_blank">📥 СКАЧАТЬ</a></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("PDF-каталоги не найдены.")

    with col2:
        st.subheader(f"📦 Наборы и коробки ({len(imgs)})")
        if imgs:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, item in enumerate(imgs[:400], 1):
                    try:
                        r = SESSION.get(item["url"], timeout=8)
                        if r.status_code != 200 or len(r.content) < 4000:
                            continue
                        if HAS_PIL:
                            try:
                                im = Image.open(io.BytesIO(r.content))
                                w, h = im.size
                                if w < 120 or h < 120 or not (0.25 < w / h < 3.0):
                                    continue
                            except Exception:
                                pass
                        name = re.sub(r"[^\w\-]+", "_", item["title"])[:35] or "item"
                        ext = "png" if ".png" in item["url"].lower() else "webp" if ".webp" in item["url"].lower() else "jpg"
                        zf.writestr(f"{i:03d}_{name}.{ext}", r.content)
                    except Exception:
                        continue

            st.download_button(
                f"📥 СКАЧАТЬ ZIP ({len(imgs)} изображений)",
                data=buf.getvalue(),
                file_name=f"{best['host']}_gift_boxes.zip",
                mime="application/zip",
                type="primary",
            )

            grid = st.columns(3)
            for i, item in enumerate(imgs[:9]):
                with grid[i % 3]:
                    st.image(item["url"], use_container_width=True)
                    st.markdown(
                        f'<div class="product-title">{item["title"]}</div>'
                        f'<span class="badge-box">🎁 НАБОР / КОРОБКА</span>'
                        + (f'<span class="badge-weight">⚖️ {item["weight"]}</span>' if item["weight"] else ""),
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Подарочные наборы и коробки не найдены.")

st.divider()
st.caption("«Первый Снег» · поиск сайта через Mojeek / DuckDuckGo / Bing с проверкой тематики")
