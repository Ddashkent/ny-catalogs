import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse

import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Отключение предупреждений SSL для работы с legacy-серверами предприятий
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🏆 БАЗА ЗНАНИЙ И НАСТРОЙКИ ФИЛЬТРАЦИИ
# =========================================================

# База официальных ресурсов производителей и поставщиков ЕАЭС
COMPANIES_DIRECTORY = {
    "рубин": "https://rubin-2000.ru",
    "рубин тг": "https://rubin-tg.ru",
    "академия шоколада": "https://academy-chocolate.ru",
    "спартак": "https://spartak.by",
    "коммунарка": "https://www.kommunarka.by",
    "рахат": "https://rakhat.kz",
    "миракс": "https://mirax-gifts.ru",
    "дилявер": "https://dilyaver.com",
    "росшоколад": "https://roschocolate.ru",
    "москондитер": "https://mosconditer.ru",
    "акконд": "https://akkond.ru",
    "славянка": "https://slavyanka.ru",
    "красный октябрь": "https://www.uniconf.ru",
    "рот фронт": "https://www.uniconf.ru",
    'бабаевский': "https://www.uniconf.ru",
    "эссен": "https://essenproduction.com",
    "победа": "https://store.pobedavkusa.ru",
    "сириус": "https://sirius-gk.ru",
    "микс ко": "https://mixco.ru",
}

# Белый список: Новогодняя тематика, годы и упаковка
NY_KEYWORDS = [
    "новогод", "новый год", "подар", "сладк", "упаков", "каталог", "catalog", "gift", "newyear", "ny",
    "2024", "2025", "2026", "2027", "2028",
    "короб", "жесть", "картон", "мгк", "туба", "тубус", "текстиль", "символ", "набор"
]

# Черный список: Служебные файлы и элементы интерфейса
STOP_WORDS = [
    "политика", "конфиденц", "персональн", "обработк", "устав", "лицензия", "сертификат",
    "реквизит", "договор", "оферта", "согласие", "соут", "privacy", "policy", "terms", "license", "report"
]

UI_EXCLUDE = [
    "logo", "icon", "banner", "button", "social", "vk", "fb", "instagram", "telegram",
    "cart", "avatar", "payment", "header", "footer", "pixel", "mastercard", "visa", "mir",
    "arrow", "bg", "background", "slider", "widget", "rating", "share", "captcha", "counter", "metrika"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ
# =========================================================

def build_session():
    """Создает отказоустойчивую сессию с повторами запросов"""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.verify = False
    retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = build_session()

def fetch_html(url):
    """Скачивание и парсинг HTML с автоопределением кодировки"""
    try:
        response = SESSION.get(url, timeout=15)
        if response.status_code != 200:
            return None
        response.encoding = response.apparent_encoding or "utf-8"
        return BeautifulSoup(response.text, "lxml")
    except Exception:
        return None

def transliterate(text):
    """Преобразование названия в slug для подбора доменов"""
    char_map = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
        'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
        'х':'h','ц':'c','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    }
    clean_text = text.lower().strip()
    result = "".join(char_map.get(char, char) for char in clean_text)
    return re.sub(r"[^a-z0-9]+", "-", result).strip("-")

def resolve_company_url(query):
    """Определяет целевой URL компании по названию или ссылке"""
    q = query.lower().strip()
    
    # 1. Прямой URL
    if q.startswith(("http://", "https://")):
        return q
    if "." in q and " " not in q:
        return f"https://{q}"
        
    # 2. Поиск в реестре
    for name, domain in COMPANIES_DIRECTORY.items():
        if name in q or q in name:
            return domain
            
    # 3. Эвристический подбор доступного домена
    slug = transliterate(q)
    candidates = [
        f"https://{slug}.ru", f"https://{slug}.by", f"https://{slug}.kz",
        f"https://{slug}-2000.ru", f"https://{slug}-tg.ru", f"https://{slug}-gifts.ru"
    ]
    for target in candidates:
        try:
            r = SESSION.head(target, timeout=3, allow_redirects=True)
            if r.status_code < 400:
                return r.url
        except Exception:
            continue
            
    return f"https://{slug}.ru"

# =========================================================
# 🕷 СКАНЕР И ФИЛЬТРАЦИЯ
# =========================================================

def is_ny_relevant(text, url=""):
    """Проверка контента на соответствие новогодней тематике"""
    combined = f"{text} {url}".lower()
    if any(stop in combined for stop in STOP_WORDS):
        return False
    return any(keyword in combined for keyword in NY_KEYWORDS)

def parse_page_assets(page_url, domain):
    """Извлечение PDF-каталогов и изображений с отдельной страницы"""
    soup = fetch_html(page_url)
    if not soup:
        return [], []

    pdfs, imgs = [], []
    page_context_relevant = is_ny_relevant("", page_url)

    # 1. Поиск PDF
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"]).split("#")[0]
        clean_href = href.lower().split("?")[0]
        if clean_href.endswith(".pdf"):
            title = " ".join(a.get_text().split())
            combo = f"{title} {href}"
            if is_ny_relevant(combo) or "каталог" in combo.lower() or "catalog" in combo.lower():
                if not any(stop in combo.lower() for stop in ["политика", "устав", "персональн"]):
                    pdfs.append({"name": title or "Новогодний каталог PDF", "url": quote(href, safe=":/?&=#")})

    # 2. Поиск изображений продукции (с поддержкой Lazy-Load)
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not src:
            continue
        full_url = urljoin(page_url, src)
        url_lower = full_url.lower()

        if any(junk in url_lower for junk in UI_EXCLUDE) or url_lower.endswith(".svg"):
            continue
        if not any(ext in url_lower for ext in (".jpg", ".jpeg", ".png", ".webp")):
            continue

        alt_text = (img.get("alt") or img.get("title") or "").strip()
        if is_ny_relevant(f"{alt_text} {full_url}") or page_context_relevant:
            imgs.append({"name": alt_text or "Новогодний подарок / упаковка", "url": quote(full_url, safe=":/?&=#")})

    return pdfs, imgs

def run_deep_analysis(start_url):
    """Многопоточный обход разделов сайта"""
    domain = urlparse(start_url).netloc
    soup = fetch_html(start_url)
    if not soup:
        return None, None, None

    # Поиск тематических разделов
    target_pages = {start_url}
    for a in soup.find_all("a", href=True):
        href = urljoin(start_url, a["href"]).split("#")[0]
        if urlparse(href).netloc.replace("www.", "") == domain.replace("www.", ""):
            link_text = a.get_text().lower()
            if any(k in link_text or k in href.lower() for k in ["catalog", "katalog", "podarki", "novogod", "upakov", "korob", "gift", "202"]):
                target_pages.add(href)

    scan_queue = list(target_pages)[:35]
    all_pdfs, all_imgs = [], []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(parse_page_assets, url, domain) for url in scan_queue]
        for future in as_completed(futures):
            try:
                p, i = future.result()
                all_pdfs.extend(p)
                all_imgs.extend(i)
            except Exception:
                continue

    # Дедупликация списков
    unique_pdfs = list({item["url"]: item for item in all_pdfs}.values())
    unique_imgs = list({item["url"]: item for item in all_imgs}.values())

    return unique_pdfs, unique_imgs, len(scan_queue)

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Анализатор новогодних каталогов конкурентов", layout="wide", page_icon="🎁")

st.title("🎁 Парсер новогодних каталогов и продукции конкурентов")
st.caption("Автоматический поиск PDF-каталогов сезонов 2024-2027 и выгрузка фотографий упаковки/подарков.")

company_query = st.text_input("Введите название компании или домен:", placeholder="Спартак / Коммунарка / Рубин / rubin-2000.ru")

if company_query:
    target_site = resolve_company_url(company_query)
    st.info(f"🎯 Целевой веб-ресурс: **[{target_site}]({target_site})**")

    with st.spinner("Сканирование структуры сайта и сбор медиа-данных..."):
        pdfs, imgs, pages_scanned = run_deep_analysis(target_site)

    if pdfs is None and imgs is None:
        st.error(f"❌ Не удалось установить соединение с {target_site}. Проверьте доступность сайта в браузере.")
    elif not pdfs and not imgs:
        st.warning(f"Просканировано страниц: {pages_scanned}. Новогодние каталоги и продукция не обнаружены.")
    else:
        st.success(f"Анализ завершен. Обработано страниц: {pages_scanned}")
        col_pdf, col_img = st.columns(2)

        with col_pdf:
            st.subheader(f"📄 Найденные PDF-каталоги ({len(pdfs)})")
            if pdfs:
                for pdf in pdfs:
                    st.markdown(f"📎 **[{pdf['name']}]({pdf['url']})**")
            else:
                st.write("PDF-каталоги не найдены.")

        with col_img:
            st.subheader(f"🖼 Изображения продукции ({len(imgs)})")
            if imgs:
                # Сборка ZIP-архива в памяти
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for idx, img in enumerate(imgs[:500]):
                        try:
                            res = SESSION.get(img["url"], timeout=8)
                            if res.status_code == 200:
                                clean_name = re.sub(r"[^\w\-]+", "_", img["name"])[:40] or "item"
                                ext = "png" if ".png" in img["url"].lower() else "webp" if ".webp" in img["url"].lower() else "jpg"
                                zf.writestr(f"{idx+1:03d}_{clean_name}.{ext}", res.content)
                        except Exception:
                            continue

                st.download_button(
                    label=f"📥 СКАЧАТЬ ВСЕ ИЗОБРАЖЕНИЯ (ZIP, {len(imgs)} шт.)",
                    data=zip_buffer.getvalue(),
                    file_name=f"catalog_{urlparse(target_site).netloc}.zip",
                    mime="application/zip",
                )

                st.write("---")
                grid = st.columns(3)
                for idx, img in enumerate(imgs[:9]):
                    grid[idx % 3].image(img["url"], caption=img["name"][:30], use_container_width=True)
            else:
                st.write("Изображения товаров не найдены.")
