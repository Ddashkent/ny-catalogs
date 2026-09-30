import io
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3
from duckduckgo_search import DDGS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 РЕЕСТР ПОСТАВЩИКОВ
# =========================================================
EXPERT_DB = {
    'рубин': ['https://rubin-2000.ru', 'https://rubin-tg.ru'],
    'академия шоколада': ['https://chocohunter.ru', 'https://academy-chocolate.ru'],
    'спартак': ['https://spartak.by'],
    'коммунарка': ['https://www.kommunarka.by'],
    'миракс': ['https://mirax-gifts.ru'],
    'дилявер': ['https://dilyaver.com'],
    'росшоколад': ['https://roschocolate.ru'],
    'москондитер': ['https://mosconditer.ru'],
    'акконд': ['https://akkond.ru'],
    'славянка': ['https://slavyanka.ru'],
}

# =========================================================
# 📦 КАРТОННЫЙ СЛОВАРЬ (ТОЛЬКО ЭТО НАМ НУЖНО)
# =========================================================
CARDBOARD_WORDS = [
    'картон', 'karton', 'cardboard',
    'мгк', 'микрогофр', 'гофрокартон', 'гофро', 'gofr', 'mgk',
    'переплет', 'переплёт', 'perepl', 'кашир', 'kashir',
    'туб', 'tuba', 'tube', 'тубус',
    'коробка', 'korobka', 'box', 'футляр', 'шкатулка из картона',
    'сундучок картон', 'домик картон', 'книга картон',
]

# Материалы, которые НАМ НЕ НУЖНЫ (жёсткий стоп-лист)
FOREIGN_MATERIALS = [
    'жест', 'zhest', 'металл', 'tin', 'банка',
    'текстил', 'tekstil', 'ткан', 'мешоч', 'мешок', 'рюкзак', 'сумка',
    'плюш', 'мягк', 'игрушк', 'toy',
    'дерев', 'derev', 'фанер', 'wood',
    'пластик', 'plastik', 'plastic', 'пэт', 'pvc', 'пвх',
    'керамик', 'стекл', 'валенк', 'носк', 'варежк',
]

# Интерфейсный мусор
UI_JUNK = [
    'logo', 'icon', 'banner', 'button', 'btn', 'social', 'vk', 'fb', 'instagram',
    'telegram', 'cart', 'avatar', 'payment', 'header', 'footer', 'pixel',
    'mastercard', 'visa', 'mir', 'arrow', 'bg', 'background', 'slider',
    'widget', 'rating', 'share', 'captcha', 'counter', 'metrika', 'sprite',
]

PDF_JUNK = ['политика', 'обработк', 'персональн', 'лицензия', 'устав',
            'согласие', 'sout', 'privacy', 'terms', 'реквизит', 'договор', 'оферт']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# =========================================================
# 🔍 ЛОГИКА ФИЛЬТРАЦИИ
# =========================================================

def fix_url(url):
    return quote(url, safe=':/?&=#')


def is_cardboard(text):
    """True — если позиция относится к картону/МГК/переплёту/тубам."""
    t = text.lower()
    if any(bad in t for bad in FOREIGN_MATERIALS):
        return False
    return any(good in t for good in CARDBOARD_WORDS)


def is_cardboard_section(url, anchor_text):
    """Пускаем краулер только в картонные разделы каталога."""
    t = (url + ' ' + anchor_text).lower()
    if any(bad in t for bad in FOREIGN_MATERIALS):
        return False
    if any(good in t for good in CARDBOARD_WORDS):
        return True
    # Общие разделы каталога пропускаем — внутри отфильтруем по карточкам
    return any(k in t for k in ['catalog', 'katalog', 'product', 'category', 'upakovka', 'podarki'])


# =========================================================
# 🌐 ПОИСК САЙТА
# =========================================================

def find_official_site(company_name):
    q = company_name.lower().strip()
    for key, urls in EXPERT_DB.items():
        if key in q:
            return urls if isinstance(urls, list) else [urls]
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(
                f"{q} новогодняя упаковка картон тубы каталог официальный сайт",
                max_results=5))
            return [r['href'] for r in res
                    if not any(b in r['href'] for b in
                               ['wikipedia', 'vk.com', 'avito', 'youtube', 'facebook'])]
    except Exception:
        return [f"https://{q.replace(' ', '-')}.ru"]


def fetch_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception:
        return None


# =========================================================
# 🕷 КРАУЛЕР (ТОЛЬКО КАРТОН)
# =========================================================

def parse_page(page_url, base_domain):
    soup = fetch_soup(page_url)
    if not soup:
        return [], []

    pdfs, imgs = [], []

    # --- PDF ---
    for a in soup.find_all('a', href=True):
        href = urljoin(page_url, a['href']).split('#')[0]
        if urlparse(href).netloc != base_domain:
            continue
        if href.lower().rsplit('?', 1)[0].endswith('.pdf'):
            title = a.get_text().strip() or href.split('/')[-1]
            combo = (title + ' ' + href).lower()
            if any(j in combo for j in PDF_JUNK):
                continue
            # PDF берём, если это каталог или картонная тема
            if is_cardboard(combo) or 'каталог' in combo or 'catalog' in combo:
                pdfs.append({'name': title, 'url': fix_url(href)})

    # --- Изображения (с учётом lazy-load) ---
    for img in soup.find_all('img'):
        src = (img.get('src') or img.get('data-src') or
               img.get('data-original') or img.get('data-lazy-src'))
        if not src:
            continue
        full = urljoin(page_url, src)
        low = full.lower()

        if any(j in low for j in UI_JUNK) or low.endswith('.svg'):
            continue
        if not any(ext in low for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            continue

        alt = (img.get('alt') or img.get('title') or '').strip()
        name = alt if alt else full.split('/')[-1].split('?')[0]

        # Проверяем: alt + имя файла + URL страницы (контекст раздела)
        context = f"{alt} {full} {page_url}"
        if is_cardboard(context):
            imgs.append({'name': name, 'url': fix_url(full)})

    return pdfs, imgs


def deep_scan(start_url):
    base_domain = urlparse(start_url).netloc
    soup = fetch_soup(start_url)
    if not soup:
        return None, None

    pages = {start_url}
    for a in soup.find_all('a', href=True):
        href = urljoin(start_url, a['href']).split('#')[0]
        if urlparse(href).netloc != base_domain:
            continue
        if is_cardboard_section(href, a.get_text()):
            pages.add(href)

    # Приоритет — явно картонным разделам
    ordered = sorted(pages, key=lambda u: 0 if any(w in u.lower() for w in CARDBOARD_WORDS) else 1)
    targets = ordered[:35]

    all_pdfs, all_imgs = [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(parse_page, u, base_domain): u for u in targets}
        for f in as_completed(futures):
            try:
                p, i = f.result()
                all_pdfs.extend(p)
                all_imgs.extend(i)
            except Exception:
                continue

    return (list({v['url']: v for v in all_pdfs}.values()),
            list({v['url']: v for v in all_imgs}.values()))


# =========================================================
# 🖥 ИНТЕРФЕЙС
# =========================================================

st.set_page_config(page_title="Картонная упаковка ЕАЭС", layout="wide", page_icon="📦")

st.title("📦 Поиск новогодней упаковки: картон / МГК / переплёт / тубы")
st.caption("Жесть, текстиль, дерево, пластик и мягкая игрушка автоматически исключаются.")

query = st.text_input("Название компании:", placeholder="Рубин")

if query:
    with st.spinner(f"Анализируем картонные разделы каталога «{query}»..."):
        sites = find_official_site(query)
        target, pdfs, imgs = None, None, None

        for s in sites:
            p, i = deep_scan(s)
            if p or i:
                target, pdfs, imgs = s, p, i
                break

    if target:
        st.success(f"✅ Сайт: **{target}**")

        c1, c2 = st.columns(2)

        with c1:
            st.subheader(f"📄 PDF-каталоги ({len(pdfs)})")
            if pdfs:
                for p in pdfs:
                    st.markdown(f"📎 **[{p['name']}]({p['url']})**")
            else:
                st.info("PDF не найдены.")

        with c2:
            st.subheader(f"📦 Картон / МГК / тубы ({len(imgs)})")
            if imgs:
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, 'w') as zf:
                    for idx, im in enumerate(imgs[:300]):
                        try:
                            data = requests.get(im['url'], timeout=4, verify=False).content
                            ext = 'png' if '.png' in im['url'].lower() else \
                                  'webp' if '.webp' in im['url'].lower() else 'jpg'
                            safe_name = ''.join(ch for ch in im['name'] if ch.isalnum() or ch in ' -_')[:40]
                            zf.writestr(f"{idx+1:03d}_{safe_name or 'karton'}.{ext}", data)
                        except Exception:
                            continue

                st.download_button(
                    f"📥 СКАЧАТЬ {len(imgs)} ФОТО (ZIP)",
                    zip_io.getvalue(),
                    file_name=f"karton_{urlparse(target).netloc}.zip",
                    mime="application/zip"
                )

                st.write("---")
                grid = st.columns(4)
                for i, im in enumerate(imgs[:12]):
                    grid[i % 4].image(im['url'], caption=im['name'][:25], use_container_width=True)
            else:
                st.info("Картонной упаковки не найдено.")
    else:
        st.error("❌ Данные извлечь не удалось. Уточните название компании.")
