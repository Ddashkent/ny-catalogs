import io
import re
import zipfile
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3
from duckduckgo_search import DDGS

# Отключаем предупреждения о SSL-сертификатах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🎯 БАЗА И ИСКЛЮЧЕНИЯ
# =========================================================
EXPERT_DB = {
    'рубин': ['https://rubin-2000.ru', 'https://rubin-tg.ru', 'https://rubin-grodno.by'],
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

# Строгий черный список для отсечения мусора интерфейса
UI_JUNK = [
    'logo', 'icon', 'banner', 'button', 'btn', 'social', 'vk', 'fb', 'instagram',
    'telegram', 'cart', 'avatar', 'payment', 'header', 'footer', 'pixel', 'mastercard',
    'visa', 'mir', 'arrow', 'bg', 'background', 'slider', 'widget', 'rating', 'share',
    'captcha', 'counter', 'yametrika', 'google'
]

PDF_JUNK = ['политика', 'обработк', 'персональн', 'лицензия', 'устав', 'согласие', 'sout', 'privacy', 'terms']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# =========================================================
# 🧠 ПОИСК И АНАЛИЗ
# =========================================================

def fix_url(url):
    return quote(url, safe=':/?&=#')

def find_official_site(company_name):
    q = company_name.lower().strip()
    for key, urls in EXPERT_DB.items():
        if key in q:
            return urls if isinstance(urls, list) else [urls]

    try:
        with DDGS() as ddgs:
            search_query = f"{q} новогодние подарки упаковка официальный сайт каталог"
            results = list(ddgs.text(search_query, max_results=5))
            valid_urls = []
            for r in results:
                url = r['href']
                if not any(bad in url for bad in ['wikipedia', 'vk.com', 'avito', 'youtube', 'facebook']):
                    valid_urls.append(url)
            return valid_urls
    except:
        return [f"https://{q.replace(' ', '-')}.ru"]

def fetch_page_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except:
        return None

# =========================================================
# 🕷 ГЛУБОКИЙ МНОГОПОТОЧНЫЙ КРАУЛЕР (DEEP SCAN)
# =========================================================

def parse_single_page(page_url, base_domain):
    """Сканирует одну конкретную страницу на PDF и изображения товаров"""
    soup = fetch_page_soup(page_url)
    if not soup:
        return [], [], []

    page_pdfs = []
    page_imgs = []
    found_links = []

    # 1. Поиск внутренних ссылок для дальнейшего углубления
    for a in soup.find_all('a', href=True):
        href = urljoin(page_url, a['href'])
        if urlparse(href).netloc == base_domain:
            # Чистим от якорей и параметров фильтрации
            clean_href = href.split('#')[0]
            found_links.append(clean_href)

            # Проверка на PDF
            if clean_href.lower().rsplit('?', 1)[0].endswith('.pdf'):
                title = a.get_text().strip() or clean_href.split('/')[-1]
                if not any(j in (title + clean_href).lower() for j in PDF_JUNK):
                    page_pdfs.append({'name': title, 'url': fix_url(clean_href)})

    # 2. Поиск изображений (учитываем Lazy-Load: data-src, data-original)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-lazy-src')
        if not src:
            continue

        full_img_url = urljoin(page_url, src)
        img_lower = full_img_url.lower()

        # Отсекаем интерфейсный мусор
        if any(junk in img_lower for junk in UI_JUNK) or img_lower.endswith('.svg'):
            continue

        # Проверяем расширения изображений
        if any(ext in img_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            alt = img.get('alt', '').strip() or img.get('title', '').strip()
            name = alt if alt else full_img_url.split('/')[-1].split('?')[0]
            page_imgs.append({'name': name, 'url': fix_url(full_img_url)})

    return page_pdfs, page_imgs, found_links


def deep_full_website_scan(start_url):
    """Полный многопоточный анализ всех разделов каталога"""
    base_domain = urlparse(start_url).netloc
    first_soup = fetch_page_soup(start_url)
    if not first_soup:
        return None, None

    # Собираем стартовый пул страниц категории и каталога
    catalog_urls = {start_url}
    for a in first_soup.find_all('a', href=True):
        href = urljoin(start_url, a['href'])
        if urlparse(href).netloc == base_domain:
            href_clean = href.split('#')[0]
            href_lower = href_clean.lower()
            # Фильтруем ссылки на категории каталога
            if any(k in href_lower for k in ['catalog', 'katalog', 'product', 'category', 'upakovka', 'podarki', 'korobki', 'zhest', 'karton', 'derevo', 'tekstil', '202']):
                catalog_urls.add(href_clean)

    # Ограничиваем список страниц до 35 самых важных разделов для высокой скорости
    urls_to_scan = list(catalog_urls)[:35]

    all_pdfs = []
    all_imgs = []

    # Многопоточный запуск сканирования
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(parse_single_page, url, base_domain): url for url in urls_to_scan}
        for future in as_completed(future_to_url):
            try:
                pdfs, imgs, _ = future.result()
                all_pdfs.extend(pdfs)
                all_imgs.extend(imgs)
            except Exception:
                continue

    # Уникализация результатов по URL
    unique_pdfs = list({v['url']: v for v in all_pdfs}.values())
    unique_imgs = list({v['url']: v for v in all_imgs}.values())

    return unique_pdfs, unique_imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Глубокий поиск каталогов ЕАЭС", layout="wide", page_icon="🎁")

st.title("🎁 Глубокий анализ каталогов и упаковки")
st.caption("Введите название компании (например: **Рубин**, **Спартак**, **Академия шоколада**). Система за секунды полностью отсканирует все категории каталога.")

query = st.text_input("Название компании:", placeholder="Рубин")

if query:
    with st.spinner(f"🔎 Ищем и глубоко анализируем каталог для «{query}»..."):
        sites = find_official_site(query)
        
        target_site = None
        pdfs, imgs = None, None
        
        for site in sites:
            res_pdfs, res_imgs = deep_full_website_scan(site)
            if res_imgs or res_pdfs:
                target_site = site
                pdfs, imgs = res_pdfs, res_imgs
                break

        if target_site and (pdfs or imgs):
            st.success(f"✅ Успешно проанализирован сайт: **{target_site}**")
            
            c1, c2 = st.columns([1, 1])
            
            with c1:
                st.subheader(f"📄 PDF Каталоги ({len(pdfs)} шт.)")
                if pdfs:
                    for p in pdfs:
                        st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                else:
                    st.info("PDF-каталоги на страницах не найдены.")

            with c2:
                st.subheader(f"🖼 Упаковка и товары ({len(imgs)} шт.)")
                if imgs:
                    # Создание полной ZIP выгрузки
                    zip_io = io.BytesIO()
                    with zipfile.ZipFile(zip_io, 'w') as zf:
                        # Скачиваем до 300 фото товаров
                        for idx, im in enumerate(imgs[:300]):
                            try:
                                r = requests.get(im['url'], timeout=4, verify=False).content
                                ext = 'jpg'
                                if '.png' in im['url'].lower(): ext = 'png'
                                elif '.webp' in im['url'].lower(): ext = 'webp'
                                zf.writestr(f"product_{idx+1}.{ext}", r)
                            except:
                                continue
                    
                    st.download_button(
                        label=f"📥 СКАЧАТЬ ВСЕ {len(imgs)} ФОТО В ZIP-АРХИВЕ",
                        data=zip_io.getvalue(),
                        file_name=f"full_catalog_{urlparse(target_site).netloc}.zip",
                        mime="application/zip"
                    )
                    
                    st.write("---")
                    st.caption("Превью первых карточек из найденных категорий:")
                    grid = st.columns(4)
                    for i, im in enumerate(imgs[:12]):
                        grid[i % 4].image(im['url'], caption=im['name'][:25], use_container_width=True)
                else:
                    st.info("Изображения упаковки не найдены.")
        else:
            st.error(f"❌ Не удалось извлечь данные с сайта компании «{query}». Попробуйте уточнить название.")
