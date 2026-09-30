import io
import re
import zipfile
from urllib.parse import urljoin, urlparse, quote
import requests
from bs4 import BeautifulSoup
import streamlit as st
from duckduckgo_search import DDGS

# =========================================================
# 🎯 ГЛОБАЛЬНЫЙ РЕЕСТР ПОДАРОЧНИКОВ (ДЛЯ МГНОВЕННОГО ПОИСКА)
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
    'красный октябрь': ['https://www.uniconf.ru'],
    'рот фронт': 'https://www.uniconf.ru',
    'бабаевский': 'https://www.uniconf.ru',
    'эссен': 'https://essenproduction.com',
    'победа': 'https://store.pobedavkusa.ru',
    'сириус': 'https://sirius-gk.ru',
    'марс': 'https://mars-podarki.ru',
    'белкондитер': 'https://belkonditer.by',
}

# Ключевые слова для фильтрации тематики
GIFT_KEYWORDS = ['подар', 'упаков', 'конфет', 'сладк', 'жесть', 'картон', 'туба', 'каталог', '2025', '2027', 'gift', 'box']
METAL_KEYWORDS = ['металл', 'прокат', 'сталь', 'арматура', 'трубы', 'бетон', 'швеллер']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# =========================================================
# 🧠 МОЗГ ПОИСКА (SMART SEARCH)
# =========================================================

def find_official_site(company_name):
    """Ищет сайт, игнорируя металл и выбирая подарки"""
    q = company_name.lower().strip()
    
    # 1. Сначала смотрим в наш проверенный список
    for key, urls in EXPERT_DB.items():
        if key in q:
            return urls if isinstance(urls, list) else [urls]

    # 2. Если нет в базе - идем в интернет с умным запросом
    try:
        with DDGS() as ddgs:
            # Добавляем уточнение, чтобы не вылез металл
            search_query = f"{q} новогодние подарки упаковка официальный сайт каталог"
            results = list(ddgs.text(search_query, max_results=5))
            
            valid_urls = []
            for r in results:
                url = r['href']
                # Отсекаем мусорные площадки (википедия, вк, авито)
                if not any(bad in url for bad in ['wikipedia', 'vk.com', 'avito', 'youtube', 'facebook', 'instagram']):
                    valid_urls.append(url)
            return valid_urls
    except:
        # Если поиск заблокирован - пробуем прямой транслит
        return [f"https://{q.replace(' ', '-')}.ru"]

def verify_and_scan(url):
    """Проверяет сайт на тему подарков и собирает данные"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        text = (soup.title.string if soup.title else "") + soup.get_text()
        text = text.lower()
        
        # Защита от металла
        if any(w in text for w in METAL_KEYWORDS) and not any(w in text for w in GIFT_KEYWORDS):
            return None, None, False
            
        domain = urlparse(url).netloc
        sections = {url}
        for a in soup.find_all('a', href=True):
            link = urljoin(url, a['href'])
            if urlparse(link).netloc == domain:
                if any(w in a.get_text().lower() or w in link.lower() for w in ['catalog', 'katalog', 'podarki', 'novogod', '202']):
                    sections.add(link)
        
        pdfs, imgs = [], []
        for page in list(sections)[:8]:
            try:
                pr = requests.get(page, headers=HEADERS, timeout=8, verify=False)
                ps = BeautifulSoup(pr.text, 'html.parser')
                # PDF
                for a in ps.find_all('a', href=True):
                    h = urljoin(page, a['href'])
                    t = a.get_text().strip()
                    if h.lower().split('?')[0].endswith('.pdf'):
                        if any(w in (t+h).lower() for w in GIFT_KEYWORDS):
                            pdfs.append({'name': t or "Каталог PDF", 'url': quote(h, safe=':/?&=#')})
                # Images
                for im in ps.find_all('img', src=True):
                    s = urljoin(page, im['src'])
                    alt = im.get('alt', '').strip()
                    if any(w in (alt+s).lower() for w in GIFT_KEYWORDS):
                        if not any(b in s.lower() for b in ['logo', 'icon', 'btn', 'social']):
                            imgs.append({'name': alt or "Упаковка", 'url': quote(s, safe=':/?&=#')})
            except: continue
            
        return list({v['url']:v for v in pdfs}.values()), list({v['url']:v for v in imgs}.values()), True
    except:
        return None, None, False

# =========================================================
# 🖥 ИНТЕРФЕЙС МЕНЕДЖЕРА
# =========================================================

st.set_page_config(page_title="AI Поиск подарков ЕАЭС", layout="wide")

st.title("🎁 Профессиональный поиск новогодних каталогов")
st.write("Менеджеру: введите только название (напр. **Рубин**, **Спартак**, **Микс-Ко**). Система сама найдет сайт и каталоги 2025-2027.")

query = st.text_input("Название компании:")

if query:
    with st.spinner(f"Ищем официальные ресурсы для '{query}'..."):
        sites = find_official_site(query)
        
        found_any = False
        for site in sites:
            pdfs, imgs, is_relevant = verify_and_scan(site)
            
            if is_relevant:
                st.success(f"✅ Найден сайт компании: {site}")
                found_any = True
                
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("📄 PDF Каталоги (в т.ч. 2027)")
                    if pdfs:
                        for p in pdfs:
                            st.markdown(f"📎 **[{p['name']}]({p['url']})**")
                    else: st.info("PDF не найдены.")
                
                with c2:
                    st.subheader("🖼 Упаковка (Фото)")
                    if imgs:
                        st.info(f"Найдено изображений: {len(imgs)}")
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w') as zf:
                            for idx, im in enumerate(imgs[:60]):
                                try:
                                    res = requests.get(im['url'], timeout=5, verify=False).content
                                    zf.writestr(f"item_{idx+1}.jpg", res)
                                except: continue
                        st.download_button(f"📥 Скачать ZIP ({site})", zip_io.getvalue(), "catalog.zip")
                        
                        cols = st.columns(3)
                        for i, im in enumerate(imgs[:9]):
                            cols[i%3].image(im['url'], use_container_width=True)
                break # Останавливаемся на первом качественном сайте
        
        if not found_any:
            st.error("❌ Не удалось найти сайт компании с новогодней тематикой. Попробуйте уточнить название.")
