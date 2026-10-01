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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FIXED_SITES = {
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://academy-chocolate.ru",
    "спартак": "https://spartak.by",
    "коммунарка": "https://www.kommunarka.by",
    "миракс": "https://mirax-gifts.ru",
    "дилявер": "https://dilyaver.com",
    "росшоколад": "https://roschocolate.ru",
    "москондитер": "https://mosconditer.ru",
    "акконд": "https://akkond.ru",
    "славянка": "https://slavyanka.ru",
}

WHITE_LIST = [
    "картон", "мгк", "микрогофр", "гофр", "переплет", "переплёт",
    "кашир", "туб", "тубус", "tube", "box", "коробка", "футляр",
    "2024", "2025", "2026", "2027", "2028", "каталог", "catalog",
]
BLACK_LIST = [
    "жесть", "металл", "tin", "банка", "текстиль", "мягк", "игрушк",
    "дерево", "фанер", "пластик", "мешок", "рюкзак", "logo", "social",
    "политика", "устав", "персональн", "privacy",
]
UI_JUNK = ["logo", "icon", "banner", "button", "social", "vk", "fb", "cart", "header", "footer", "pixel", "sprite"]
SECTION_HINTS = ["catalog", "katalog", "podarki", "novogod", "karton", "tuba", "upakov", "korob", "gift"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


SESSION = make_session()


def get_soup(url):
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "lxml")
    except Exception:
        return None


def resolve_url(query):
    q = query.lower().strip()
    if q.startswith(("http://", "https://")):
        return q
    if "." in q and " " not in q:
        return "https://" + q
    for name, url in FIXED_SITES.items():
        if name in q or q in name:
            return url
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", q, flags=re.I).strip("-")
    return f"https://{slug}.ru"


def is_relevant(text, url=""):
    t = f"{text} {url}".lower()
    if any(b in t for b in BLACK_LIST):
        return False
    return any(w in t for w in WHITE_LIST)


def same_host(a, b):
    return urlparse(a).netloc.replace("www.", "") == urlparse(b).netloc.replace("www.", "")


def scan_page(url, domain):
    soup = get_soup(url)
    if not soup:
        return [], []
    pdfs, imgs = [], []
    page_is_cardboard = is_relevant("", url)

    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"]).split("#")[0]
        if not href.lower().split("?")[0].endswith(".pdf"):
            continue
        txt = " ".join(a.get_text().split())
        combo = f"{txt} {href}"
        if is_relevant(combo) or ("каталог" in combo.lower() or "catalog" in combo.lower()):
            if not any(b in combo.lower() for b in ["политика", "устав", "персональн"]):
                pdfs.append({"name": txt or "Каталог PDF", "url": quote(href, safe=":/?&=#")})

    for im in soup.find_all("img"):
        src = im.get("src") or im.get("data-src") or im.get("data-original") or im.get("data-lazy-src")
        if not src:
            continue
        full = urljoin(url, src)
        low = full.lower()
        if any(j in low for j in UI_JUNK) or low.endswith(".svg"):
            continue
        if not any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp")):
            continue
        alt = (im.get("alt") or im.get("title") or "").strip()
        if is_relevant(f"{alt} {full} {url}") or page_is_cardboard:
            if any(b in f"{alt} {full}".lower() for b in ["жесть", "металл", "текстиль", "мягк"]):
                continue
            imgs.append({"name": alt or "Картон / туба", "url": quote(full, safe=":/?&=#")})
    return pdfs, imgs


st.set_page_config(page_title="Картонный поиск 2027", layout="wide", page_icon="📦")
st.title("📦 Поиск новогодней упаковки (картон / МГК / тубы)")
st.caption("Запускайте с ПК в РФ. Streamlit Cloud часто не достучится до сайтов .by/.ru.")

query = st.text_input("Компания или сайт", placeholder="Коммунарка / rubin-2000.ru")

if query:
    target_url = resolve_url(query)
    st.info(f"Сайт: **{target_url}**")
    soup = get_soup(target_url)

    if not soup:
        st.error(
            f"Нет ответа от {target_url}. "
            "Запустите приложение локально в РФ (`streamlit run app.py`), "
            "не из Streamlit Cloud."
        )
    else:
        domain = urlparse(target_url).netloc
        pages = {target_url}
        for a in soup.find_all("a", href=True):
            href = urljoin(target_url, a["href"]).split("#")[0]
            if not same_host(href, target_url):
                continue
            blob = f"{a.get_text()} {href}".lower()
            if any(w in blob for w in SECTION_HINTS):
                pages.add(href)

        pages = list(pages)[:30]
        all_pdfs, all_imgs = [], []
        with st.spinner(f"Сканирование {len(pages)} страниц…"):
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = [ex.submit(scan_page, u, domain) for u in pages]
                for f in as_completed(futs):
                    p, i = f.result()
                    all_pdfs.extend(p)
                    all_imgs.extend(i)

        pdfs = list({v["url"]: v for v in all_pdfs}.values())
        imgs = list({v["url"]: v for v in all_imgs}.values())

        if not pdfs and not imgs:
            st.warning("Картон / тубы / PDF-каталоги не найдены.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader(f"📄 PDF ({len(pdfs)})")
                for p in pdfs:
                    st.markdown(f"📎 [{p['name']}]({p['url']})")
                if not pdfs:
                    st.write("Нет")
            with c2:
                st.subheader(f"📦 Картон / тубы ({len(imgs)})")
                if imgs:
                    z = io.BytesIO()
                    with zipfile.ZipFile(z, "w") as zf:
                        for idx, im in enumerate(imgs[:400]):
                            try:
                                data = SESSION.get(im["url"], timeout=8).content
                                name = re.sub(r"[^\w\-]+", "_", im["name"])[:40] or "item"
                                zf.writestr(f"{idx+1:03d}_{name}.jpg", data)
                            except Exception:
                                continue
                    st.download_button(
                        f"Скачать ZIP ({len(imgs)})",
                        z.getvalue(),
                        "packaging_archive.zip",
                        "application/zip",
                    )
                    g = st.columns(3)
                    for i, im in enumerate(imgs[:9]):
                        g[i % 3].image(im["url"], use_container_width=True)
