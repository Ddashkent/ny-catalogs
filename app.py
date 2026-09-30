import io
import re
import zipfile
from urllib.parse import urljoin, urlparse, quote
import requests
from bs4 import BeautifulSoup
import streamlit as st
import urllib3

# Отключаем ошибки сертификатов (для старых сайтов заводов)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# ⚙️ НАСТРОЙКИ УМНОГО ФИЛЬТРА
# =========================================================

# Ключевые слова для ПОДАРКОВ (белый список)
GOOD_WORDS = ['подар', 'упаков', 'конфет', 'сладк', 'жесть', 'картон', 'туба', '2025', '2026', '2027', '2028', 'catalog', 'gift']
# Ключевые слова для МЕТАЛЛА и прочего мусора (черный список)
BAD_THEMES = ['металл', 'сталь', 'прокат', 'арматура', 'трубы', 'бетон', 'ювелир', 'кольцо']
# Исключения для PDF (административный мусор)
PDF_JUNK = ['политика', 'обработк', 'персональн', 'лицензия', 'устав', 'согласие', 'sout', 'special-assessment']

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# =========================================================
# 🔍 АНАЛИТИЧЕСКИЙ ДВИЖОК
# =========================================================

def fix_url(url):
    """Кодирует кириллицу (чтобы ссылки 2027 года работали)"""
    return quote(url, safe=':/?&=#')

def analyze_site_theme(url):
    """Определяет, о чем сайт: о подарках или о металле"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        page_text = soup.get_text().lower()
        
        # Проверка на металл
        if any(w in page_text for w in BAD_THEMES) and not any(w in page_text for w in GOOD_WORDS):
            return False, "❌ Это сайт другой тематики (металл/промышленность)."
        
        # Проверка на подарки
        if any(w in page_text for w in GOOD_WORDS):
            title = soup.title.string.strip() if soup.title else "Сайт найден"
            return True, title
            
        return True, "Сайт доступен для анализа"
    except Exception as e:
        return False, f"❌ Ошибка доступа: {str(e)}"

def deep_scan(base_url):
    """Ищет каталоги и фото на всех уровнях сайта"""
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
    except: return [], []

    domain = urlparse(base_url).netloc
    
    # Автоматически находим подразделы: Каталог, Новый год, 2027 и т.д.
    found_pages = {base_url}
    for a in soup.find_all('a', href=True):
        link = urljoin(base_url, a['href'])
        if urlparse(link).netloc == domain:
            link_text = a.get_text().lower()
            if any(w in link_text or w in link.lower() for w in ['catalog', 'novogod', 'podarki', '202', '2027', 'katalog']):
                found_pages.add(link)
    
    pdfs, imgs = [], []
    # Сканируем до 10 найденных страниц
    for page in list(found_pages)[:10]:
        try:
            pr = requests.get(page, headers=HEADERS, timeout=8, verify=False)
            psoup = BeautifulSoup(pr.text, 'html.parser')
            
            # Собираем PDF
            for a in psoup.find_all('a', href=True):
                href = urljoin(page, a['href'])
                name = a.get_text().strip().replace('\n', ' ')
                if href.lower().split('?')[0].endswith('.pdf'):
                    # Фильтруем PDF: ищем 2027, подарки и отсекаем мусор
                    if any(w in (name + href).lower() for w in GOOD_WORDS):
                        if not any(j in (name + href).lower() for j in PDF_JUNK):
                            pdfs.append({'name': name or "Каталог PDF", 'url': fix_url(href)})
            
            # Собираем фото упаковки
            for im in psoup.find_all('img', src=True):
                src = urljoin(page, im['src'])
                alt = im.get('alt', '').strip()
                if any(w in (alt + src).lower() for w in GOOD_WORDS):
                    if not any(j in src.lower() for j in ['logo', 'icon', 'btn', 'social']):
                        imgs.append({'name': alt or "Фото упаковки", 'url': fix_url(src)})
        except: continue

    # Удаление дубликатов
    final_pdfs = list({v['url']:v for v in pdfs}.values())
    final_imgs = list({v['url']:v for v in imgs}.values())
    
    return final_pdfs, final_imgs

# =========================================================
# 🖥 ИНТЕРФЕЙС МЕНЕДЖЕРА
# =========================================================

st.set_page_config(page_title="Анализатор подарков ЕАЭС", layout="wide")

st.markdown("""
    <style>
    .card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; background: white; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    .btn-download { background: #2a9d8f; color: white !important; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block; }
    </style>
""", unsafe_allow_html=True)

st.title("🚀 Автономный поиск новогодних каталогов")
st.write("Введите название компании или адрес сайта. Система сама проанализирует тематику и найдет файлы 2025-2027.")

user_input = st.text_input("Компания или сайт (например: rubin-2000.ru, спартак, микс-ко):")

if user_input:
    # 1. Определяем URL
    query = user_input.lower().strip()
    if '.' in query and ' ' not in query:
        target_url = query if query.startswith('http') else f"https://{query}"
    else:
        # Простая эвристика для названий
        target_url = f"https://{query.replace(' ', '-')}.ru"

    # 2. Анализируем тематику
    with st.spinner(f"Анализируем содержимое {target_url}..."):
        is_ok, message = analyze_site_theme(target_url)
        
        if is_ok:
            st.success(f"✅ Сайт подтвержден: {message}")
            
            # 3. Глубокое сканирование
            pdfs, imgs = deep_scan(target_url)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📄 Найденные PDF-каталоги")
                if pdfs:
                    for p in pdfs:
                        st.markdown(f"""
                        <div class="card">
                            <div style="margin-bottom:8px;">💾 <b>{p['name']}</b></div>
                            <a href="{p['url']}" target="_blank" class="btn-download">ОТКРЫТЬ PDF</a>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Каталоги в формате PDF не найдены.")

            with col2:
                st.subheader("🖼 Фотографии упаковки")
                if imgs:
                    st.write(f"Найдено изображений: {len(imgs)}")
                    
                    # Создание ZIP
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w') as zf:
                        for i, img in enumerate(imgs[:60]):
                            try:
                                img_data = requests.get(img['url'], timeout=5, verify=False).content
                                zf.writestr(f"item_{i+1}.jpg", img_data)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ZIP С КАРТИНКАМИ", zip_buffer.getvalue(), "catalog_archive.zip")
                    
                    # Галерея
                    g_cols = st.columns(3)
                    for idx, im in enumerate(imgs[:9]):
                        g_cols[idx%3].image(im['url'], use_container_width=True)
                else:
                    st.info("Изображения товаров не найдены.")
        else:
            st.error(message)
            st.info("Попробуйте ввести точный адрес сайта компании вручную.")
