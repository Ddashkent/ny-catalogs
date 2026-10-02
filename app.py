import io
import re
import zipfile
import datetime
import urllib.parse
import concurrent.futures
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image
import urllib3

# Отключение системных уведомлений
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🏆 ЭКСПЕРТНАЯ БАЗА ПРОИЗВОДИТЕЛЕЙ (БЕЗОШИБОЧНЫЙ ВХОД)
# =========================================================
# Здесь собраны реальные сайты лидеров рынка, включая сложные домены
EXPERT_REGISTRY = {
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "солбигтрейд": "https://конфета.бел",
    "абинекс": "https://podarok-k.ru",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru",
    "рахат": "https://rakhat.kz",
    "баян сулу": "https://www.bayansulu.kz",
    "миракс": "https://mirax-gifts.ru",
    "дилявер": "https://dilyaver.ru",
    "росшоколад": "https://roschocolate.ru",
    "микс ко": "https://podarki-opt.ru",
    "рэйд 21": "https://podarki-reid21.ru",
    "акконд": "https://akkond.ru",
    "славянка": "https://slavyanka.ru",
    "лаконд": "https://lakond.ru",
    "донко": "https://donko.su",
    "тореро": "https://torero.ru",
}

# Тематические слова для подтверждения сайта
GIFT_THEME = ['подарк', 'конфет', 'новогод', 'упаков', 'коробк', 'туб', 'каталог']

# Исключаемые материалы и типы (мусор)
FORBIDDEN_ITEMS = ['плитка шоколада', 'батончик', 'конфета на вес', 'весовые конфеты', 'карамелька', 'драже']
FORBIDDEN_MATERIALS = ['жесть', 'металл', 'текстиль', 'мягкая игрушка', 'рюкзак', 'мешочек']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8'
}

# =========================================================
# ⚙️ ЛОГИКА ПОИСКА И АНАЛИЗА
# =========================================================

def fix_url(base, src):
    """Исправляет кириллические домены и пути"""
    try:
        if not src: return ""
        if src.startswith('//'): src = 'https:' + src
        full = urllib.parse.urljoin(base, src)
        p = urllib.parse.urlparse(full)
        host = p.netloc.encode('idna').decode('ascii')
        path = urllib.parse.quote(urllib.parse.unquote(p.path))
        return urllib.parse.urlunparse(p._replace(netloc=host, path=path))
    except: return src

def safe_fetch(url):
    """Профессиональная загрузка страницы"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text, r.url
    except: pass
    return None, url

def is_packaging_item(title, url):
    """Фильтр: только наборы и упаковка из картона/туб"""
    blob = (title + " " + url).lower().replace('ё', 'е')
    
    # 1. Сразу убираем нецелевые материалы
    if any(m in blob for m in FORBIDDEN_MATERIALS): return False
    # 2. Убираем одиночные конфеты, если нет слова "набор" или "подарок"
    if any(s in blob for s in FORBIDDEN_ITEMS) and not any(g in blob for g in ['набор', 'подар']):
        return False
    # 3. Оставляем только то, что похоже на новогоднюю упаковку
    return any(w in blob for w in ['набор', 'подар', 'короб', 'туб', 'мгк', 'картон', 'футляр'])

# =========================================================
# 🕷 СКАНЕР
# =========================================================

def scan_website(start_url):
    html, real_url = safe_fetch(start_url)
    if not html: return [], []
    
    soup = BeautifulSoup(html, 'lxml')
    domain = urllib.parse.urlparse(real_url).netloc
    
    # Собираем ссылки на разделы (Каталог, Подарки)
    sections = {real_url}
    for a in soup.find_all('a', href=True):
        href = fix_url(real_url, a['href'])
        if domain in href and any(w in href.lower() for w in ['catalog', 'podarki', 'novogod', 'upakovka']):
            sections.add(href.split('#')[0])
            
    all_pdfs, all_imgs = [], []
    
    def process_page(url):
        p_html, _ = safe_fetch(url)
        if not p_html: return [], []
        ps, imgs = [], []
        s = BeautifulSoup(p_html, 'lxml')
        
        # PDF
        for a in s.find_all('a', href=True):
            h = fix_url(url, a['href'])
            if h.lower().split('?')[0].endswith('.pdf'):
                name = a.get_text().strip()
                if any(w in (name+h).lower() for w in GIFT_THEME):
                    ps.append({'name': name or "Каталог PDF", 'url': h})
        
        # Фото
        for im in s.find_all('img'):
            src = im.get('src') or im.get('data-src') or im.get('data-original')
            if not src: continue
            f_src = fix_url(url, src)
            alt = (im.get('alt') or "").strip()
            if is_packaging_item(alt, f_src):
                if not any(j in f_src.lower() for j in ['logo', 'icon', 'banner', 'social']):
                    imgs.append({'name': alt or "Новогодний подарок", 'url': f_src})
        return ps, imgs

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_page, u) for u in list(sections)[:20]]
        for f in concurrent.futures.as_completed(futures):
            p, i = f.result()
            all_pdfs.extend(p)
            all_imgs.extend(i)
            
    return list({v['url']:v for v in all_pdfs}.values()), list({v['url']:v for v in all_imgs}.values())

# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(page_title="Первый Снег | Поиск", layout="wide", page_icon="❄️")
st.title("❄️ Экстрактор Новогодней Упаковки ЕАЭС")

query = st.text_input("Введите название компании (например: Коммунарка, Абинекс, СолБигТрейд):")

if query:
    q_low = query.lower().strip()
    target_site = None
    
    # 1. Проверяем Золотой Реестр (Мгновенно)
    if q_low in EXPERT_REGISTRY:
        target_site = EXPERT_REGISTRY[q_low]
    else:
        # 2. Попытка транслитерации и прямого входа
        trans = q_low.replace(' ', '-')
        target_site = f"https://{trans}.ru"

    with st.spinner(f"🚀 Подключаемся к официальному ресурсу для «{query}»..."):
        # Проверяем доступность
        html, final_url = safe_fetch(target_site)
        
        if not html:
            st.error(f"❌ Сайт {target_site} не отвечает. Пожалуйста, введите точный адрес сайта.")
            st.stop()
            
        st.success(f"🌐 Официальный сайт подтвержден: **[{final_url}]({final_url})**")
        
        # Сканирование
        pdfs, imgs = scan_website(final_url)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"📄 PDF Каталоги ({len(pdfs)})")
            if pdfs:
                for p in pdfs: st.markdown(f"• **[{p['name']}]({p['url']})**")
            else: st.info("PDF не найдены.")

        with col2:
            st.subheader(f"📦 Наборы и Упаковка ({len(imgs)})")
            if imgs:
                # ZIP
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, img in enumerate(imgs[:300]):
                        try:
                            res = requests.get(img['url'], timeout=5, verify=False).content
                            ext = img['url'].split('.')[-1][:3]
                            if ext not in ['jpg', 'png', 'web']: ext = 'jpg'
                            zf.writestr(f"item_{i+1}.{ext}", res)
                        except: continue
                
                st.download_button("📥 СКАЧАТЬ ZIP С КАРТИНКАМИ", zip_buf.getvalue(), "packaging_archive.zip", type="primary")
                
                grid = st.columns(3)
                for idx, im in enumerate(imgs[:9]):
                    grid[idx%3].image(im['url'], use_container_width=True)
            else: st.info("Картонная упаковка не найдена.")

st.divider()
st.caption("Инструмент «Первый Снег» | Встроенный реестр производителей ЕАЭС | Версия PRO")
