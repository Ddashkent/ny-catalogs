import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st
import io
import zipfile

# 1. Настройка страницы
st.set_page_config(page_title="Визуальный Навигатор Подарков", page_icon="🖼️", layout="wide")

# АВТО-ГОД (настройка на актуальный сезон)
now = datetime.datetime.now()
target_year = 2026 # Фиксируем на сезон 2026 (Год Лошади), как вы просили ранее

st.title(f"🖼️ Визуальный Экстрактор Подарков {target_year}")
st.caption("Автоматический поиск каталогов и выгрузка изображений продукции без юридического мусора.")

# --- БАЗА И ФИЛЬТРЫ ---
KNOWLEDGE_BASE = {
    "лаконд": "lakond.ru", "акконд": "akkond.ru", "донко": "donko.su", "тор": "donko.su",
    "рубин": "rubin-2000.ru", "дилявер": "dilaver.ru", "главупак": "glavupak.ru",
    "коммунарка": "kommunarka.by", "спартак": "spartak.by", "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz", "славянка": "slavyanka.ru", "победа": "pobeda.market"
}

# Слова для удаления юридического мусора
JUNK_WORDS = ["политика", "обработка", "персональных", "данных", "согласие", "соглашение", "вакансии", "инн", "огрн"]

# --- УМНЫЕ ФУНКЦИИ ---

def find_site(query):
    q_low = query.lower().strip()
    if q_low in KNOWLEDGE_BASE: return KNOWLEDGE_BASE[q_low]
    try:
        with DDGS() as ddgs:
            res = list(ddgs.text(f'"{query}" кондитерская фабрика официальный сайт', max_results=3))
            for r in res:
                if not any(x in r['href'] for x in ["wiki", "otzovik", "checko", "list-org"]):
                    return urllib.parse.urlparse(r['href']).netloc
    except: return None

def get_assets(url):
    docs, imgs = [], []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"http://{url}", headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 1. Поиск документов (с фильтрацией мусора)
        for a in soup.find_all("a", href=True):
            h, t = a['href'].lower(), a.get_text().lower()
            if any(ext in h for ext in [".pdf", ".xlsx", ".xls"]):
                # Фильтр юридических документов
                if not any(junk in t or junk in h for junk in JUNK_WORDS):
                    full_link = urllib.parse.urljoin(f"http://{url}", a['href'])
                    docs.append({"title": a.get_text().strip() or "Файл", "link": full_link})
        
        # 2. Поиск картинок (фильтруем логотипы и иконки)
        for img in soup.find_all("img", src=True):
            src = img['src']
            if any(x in src.lower() for x in ["logo", "icon", "facebook", "vk", "instagram", "telegr", "wp-content/plugins", "spacer"]):
                continue
            full_img_url = urllib.parse.urljoin(f"http://{url}", src)
            if full_img_url.startswith("http") and full_img_url not in imgs:
                imgs.append(full_img_url)
                
    except: pass
    return docs, imgs

# --- ИНТЕРФЕЙС ---

company_query = st.text_input("Введите название компании:", placeholder="Например: Рубин или Лаконд")

if st.button("🚀 ЗАПУСТИТЬ СБОР ДАННЫХ", type="primary"):
    if company_query:
        site = find_site(company_query)
        if site:
            st.success(f"🌐 Сайт определен: `{site}`")
            docs, imgs = get_assets(site)
            
            tab1, tab2 = st.tabs(["📄 Каталоги и Прайсы", "🖼️ Галерея товаров"])
            
            with tab1:
                if docs:
                    st.write("### Найдено файлов:")
                    # Убираем дубликаты
                    unique_docs = {d['link']: d for d in docs}.values()
                    for d in unique_docs:
                        st.markdown(f"✅ **{d['title']}** — [Скачать]({d['link']})")
                else: st.warning("Прямых PDF/XLS файлов с продукцией не найдено.")
            
            with tab2:
                if imgs:
                    st.write(f"Найдено фото продукции: {len(imgs)}")
                    
                    # Кнопка скачивания архива
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
                        for i, img_url in enumerate(imgs[:50]): # Лимит 50 для стабильности
                            try:
                                img_res = requests.get(img_url, timeout=5)
                                if img_res.status_code == 200:
                                    ext = "jpg"
                                    if ".png" in img_url.lower(): ext = "png"
                                    zip_file.writestr(f"product_{i+1}.{ext}", img_res.content)
                            except: continue
                    
                    st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО В ZIP", zip_buffer.getvalue(), f"{company_query}_images.zip", "application/zip")
                    
                    # Сетка картинок
                    cols = st.columns(4)
                    for idx, img_url in enumerate(imgs[:24]):
                        with cols[idx % 4]:
                            st.image(img_url, use_container_width=True)
                else:
                    st.warning("Изображения товаров не найдены.")
        else:
            st.error("Не удалось найти официальный сайт фабрики.")

st.divider()
st.info(f"💡 Весь юридический мусор (политики персональных данных и т.д.) автоматически отфильтрован.")
