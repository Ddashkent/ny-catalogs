import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Безопасный импорт PIL
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -----------------------------
# НАСТРОЙКИ ИНТЕРФЕЙСА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(
    page_title="Первый Снег | Анализ Упаковки & Каталогов",
    page_icon="❄️",
    layout="wide",
)

TARGET_YEAR = 2026

st.markdown(
    """
    <style>
    .stApp { background-color: #f4f7f9; }
    .main-title { color: #1e3a8a; font-weight: 800; font-size: 28px; }
    .sub-title { color: #475569; font-size: 14px; margin-bottom: 20px; }
    
    /* Карточки товаров */
    .product-card {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.04);
    }
    .badge-our {
        background-color: #0284c7; color: white;
        font-weight: bold; padding: 4px 10px;
        font-size: 12px; border-radius: 6px; display: inline-block;
    }
    .badge-comp {
        background-color: #ef4444; color: white;
        font-weight: bold; padding: 4px 10px;
        font-size: 12px; border-radius: 6px; display: inline-block;
    }
    .doc-box {
        background-color: #ffffff; border-left: 6px solid #10b981;
        padding: 16px; border-radius: 10px; margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .btn-doc {
        background-color: #10b981; color: white !important;
        font-weight: bold; padding: 10px 20px; border-radius: 6px;
        text-decoration: none; display: inline-block; margin-top: 8px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.markdown("<div class='main-title'>❄️ Первый Снег: Мониторинг & Аудит Упаковки</div>", unsafe_allow_html=True)
st.markdown(f"<div class='sub-title'>Рабочий инструмент менеджера: поиск каталогов {TARGET_YEAR}, выгрузка визуалов и анализ доли нашей упаковки у клиентов.</div>", unsafe_allow_html=True)

# -----------------------------
# БАЗА ЗНАНИЙ И ФИЛЬТРЫ
# -----------------------------

KNOWLEDGE_BASE = {
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "тор": "donko.su",
    "рубин": "rubin-2000.ru",
    "дилявер": "dilaver.ru",
    "главупак": "glavupak.ru",
    "дедморозов": "dedmorozov.ru",
    "коммунарка": "kommunarka.by",
    "спартак": "spartak.by",
    "рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "униконф": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.ru",
    "красный мозырянин": "mozyrconfectionery.by"
}

JUNK_WORDS = ["политика", "согласие", "соглашение", "вакансии", "акции", "инвесторам", "реквизиты", "устав", "новости"]
CATALOG_WORDS = ["каталог", "подарки", "упаковка", "продукц", "catalog", "нг", "новогод", "наборы", "коробки"]
JUNK_DOMAINS = ["wikipedia.org", "otzovik", "avito", "checko", "list-org", "hh.ru", "vk.com", "youtube"]

PROBE_PATHS = ["", "/catalog/", "/katalog/", "/podarki/", "/novogodnie-podarki/", "/upakovka/", "/catalog/novogodnie-podarki/"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

# Инициализация сессии для аудита доли упаковки
if "tagged_items" not in st.session_state:
    st.session_state.tagged_items = {}

# -----------------------------
# ВСПАМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("http"):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.replace("www.", "")

def get_html(url: str):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        if res.status_code == 200:
            return res.url, res.text
    except Exception:
        pass
    return None, None

def find_site_dynamic(company_name: str) -> str:
    q_low = company_name.lower().strip()
    if q_low in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[q_low]
    for k, v in KNOWLEDGE_BASE.items():
        if k in q_low or q_low in k:
            return v
    try:
        query = f'"{company_name}" новогодняя упаковка подарки официальный сайт'
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(search_url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", class_="result__url", href=True):
                target = urllib.parse.parse_qs(urllib.parse.urlparse(a['href']).query).get("uddg", [a['href']])[0]
                netloc = urllib.parse.urlparse(target).netloc.lower().replace("www.", "")
                if netloc and not any(bad in netloc for bad in JUNK_DOMAINS):
                    return netloc
    except Exception:
        pass
    return None

def extract_assets(domain: str):
    base_protocol = f"https://{domain}"
    urls_to_check = [base_protocol + p for p in PROBE_PATHS]

    docs, products = [], []
    seen_links = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        pages_data = list(executor.map(get_html, urls_to_check))

        for p_url, p_html in pages_data:
            if not p_html:
                continue
            p_soup = BeautifulSoup(p_html, "html.parser")

            # 1. Поиск PDF / Excel каталогов
            for a in p_soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip()
                if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                    if not any(bad in text.lower() for bad in JUNK_WORDS):
                        if any(good in text.lower() or good in href for good in ["каталог", "прайс", "подарки", "2026", "2025", "price", "catalog"]):
                            full_link = urllib.parse.urljoin(p_url, a["href"])
                            if full_link not in seen_links:
                                seen_links.add(full_link)
                                docs.append({"title": text or "Официальный каталог / прайс-лист", "url": full_link})

            # 2. Извлечение карточек товаров (если PDF мало)
            for img in p_soup.find_all("img"):
                src = img.get("data-src") or img.get("data-original") or img.get("src")
                if not src:
                    continue

                img_url = urllib.parse.urljoin(p_url, src)
                if any(bad in img_url.lower() for bad in ["logo", "icon", "banner", "vk", "social", "avatar"]):
                    continue

                # Очистка превью Битрикса
                img_url = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", img_url)
                img_url = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", img_url)

                title = ""
                if img.parent:
                    title = img.parent.get_text(" ", strip=True)[:120]
                if not title or len(title) < 5:
                    title = img.get("alt") or img.get("title") or "Подарок / Упаковка"

                title = re.sub(r"\s+", " ", title).strip()

                if img_url not in seen_links and len(title) > 3:
                    if not any(bad in title.lower() for bad in JUNK_WORDS):
                        seen_links.add(img_url)
                        products.append({"title": title, "img": img_url, "id": len(products)})

    return docs, products

# -----------------------------
# ВВОД ДАННЫХ И ИНТЕРФЕЙС
# -----------------------------

col_search, col_mode = st.columns([3, 1])

with col_search:
    company_input = st.text_input("Введите название заказчика или адрес его сайта:", placeholder="Например: Рубин, Академия шоколада, lakond.ru, bayansulu.kz...")

with col_mode:
    search_type = st.selectbox("Режим работы:", ["Авто-поиск по названию", "Прямой ввод сайта"])

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ И НАЧАТЬ АУДИТ", type="primary", use_container_width=True):
    if not company_input.strip():
        st.error("Пожалуйста, введите название компании или сайт.")
        st.stop()

    input_str = company_input.strip()
    domain = None

    if search_type == "Прямой ввод сайта" or ("." in input_str and " " not in input_str):
        domain = normalize_domain(input_str)
    else:
        with st.spinner(f"Определяем официальный сайт для '{input_str}'..."):
            domain = find_site_dynamic(input_str)

    if domain:
        st.session_state["current_domain"] = domain
        with st.spinner(f"Сканируем сайт {domain} и извлекаем новогодний ассортимент..."):
            docs, products = extract_assets(domain)
            st.session_state["current_docs"] = docs
            st.session_state["current_products"] = products
    else:
        st.error("Не удалось определить сайт. Переключите режим на 'Прямой ввод сайта' и вставьте домен вручную (например: chocolate-academy.ru).")

# -----------------------------
# ОТОБРАЖЕНИЕ РЕЗУЛЬТАТОВ И АНАЛИТИКА
# -----------------------------

if "current_domain" in st.session_state:
    domain = st.session_state["current_domain"]
    docs = st.session_state.get("current_docs", [])
    products = st.session_state.get("current_products", [])

    st.success(f"🌐 Активный сайт заказчика: `{domain}`")

    tab1, tab2, tab3 = st.tabs(["📄 Официальные Файлы (PDF/XLS)", "📸 Визуальный Каталог & Маркировка Упаковки", "📊 Отчет по Доле рынка (Share of Shelf)"])

    # ВКЛАДКА 1: Документы
    with tab1:
        if docs:
            st.success(f"Найдено официально опубликованных каталогов/прайсов: **{len(docs)}**")
            for d in docs:
                icon = "📕 PDF" if ".pdf" in d['url'].lower() else "📊 EXCEL / DOC"
                st.markdown(
                    f"""
                    <div class="doc-box">
                        <b>{icon} | {d['title']}</b><br>
                        <small style="color:gray;">Ссылка: {d['url']}</small><br>
                        <a href="{d['url']}" target="_blank" class="btn-doc">📥 СКАЧАТЬ ОФИЦИАЛЬНЫЙ КАТАЛОГ</a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("Открытых PDF/Excel файлов на страницах не найдено. Используйте визуальный каталог во 2-й вкладке.")

    # ВКЛАДКА 2: Визуальный Каталог + Разметка (Первый Снег vs Конкуренты)
    with tab2:
        if products:
            st.write(f"Найдено карточек подарков/упаковки: **{len(products)} шт.**")

            # Кнопка быстрой выгрузки ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for i, p in enumerate(products[:100]):
                    try:
                        res_img = requests.get(p["img"], timeout=5).content
                        zf.writestr(f"item_{i+1:03d}.jpg", res_img)
                    except Exception:
                        continue

            st.download_button("📥 СКАЧАТЬ ВСЕ ФОТО ПОДАРКОВ В ZIP", zip_buffer.getvalue(), f"{domain}_catalog_photos.zip", "application/zip")

            st.markdown("---")
            st.write("##### 💡 Разметка менеджера: отмечайте галочками коробки «Первого Снега» для расчета вашей доли:")

            cols = st.columns(4)
            for i, p in enumerate(products[:36]): # Отображаем первые 36 для высокой скорости UI
                item_key = f"{domain}_item_{i}"
                with cols[i % 4]:
                    st.image(p["img"], use_container_width=True)
                    st.caption(p["title"][:70])
                    
                    # Разметка принадлежности упаковки
                    is_our = st.checkbox("❄️ Наша упаковка (Первый Снег)", key=item_key)
                    if is_our:
                        st.session_state.tagged_items[item_key] = {"domain": domain, "title": p["title"], "type": "Первый Снег", "img": p["img"]}
                    else:
                        st.session_state.tagged_items[item_key] = {"domain": domain, "title": p["title"], "type": "Конкурент", "img": p["img"]}

        else:
            st.warning("На сайте не удалось выгрузить карточки товаров. Используйте снайперские кнопки внизу.")

    # ВКЛАДКА 3: Сводный Отчет для Руководства Sales-отдела
    with tab3:
        st.subheader(f"📊 Отчет по клиенту `{domain}`")
        
        domain_tags = [v for k, v in st.session_state.tagged_items.items() if v["domain"] == domain]
        total_tagged = len(domain_tags)
        our_count = len([v for v in domain_tags if v["type"] == "Первый Снег"])
        comp_count = total_tagged - our_count

        share_pct = round((our_count / total_tagged * 100), 1) if total_tagged > 0 else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Всего позиций в аудите", f"{total_tagged} шт.")
        m2.metric("Упаковка «Первый Снег»", f"{our_count} шт.", f"{share_pct}% доли")
        m3.metric("Упаковка Конкурентов", f"{comp_count} шт.", f"{round(100 - share_pct, 1)}%")

        st.progress(share_pct / 100 if total_tagged > 0 else 0)

        if total_tagged > 0:
            st.write("### 📝 Детализация размеченных позиций:")
            for item in domain_tags:
                tag_badge = "❄️ Первый Снег" if item["type"] == "Первый Снег" else "⚔️ Конкурент"
                st.write(f"- **[{tag_badge}]** {item['title']}")

    # Резервный блок постоянных снайперских ссылок
    st.markdown("---")
    st.write("### 🔍 Резервный поиск напрямую в базе Яндекса и Google:")
    c1, c2, c3 = st.columns(3)
    clean_q = urllib.parse.quote(f'"{domain}" новогодние подарки упаковка {TARGET_YEAR}')
    with c1:
        st.link_button("📕 PDF Каталоги в Google", f"https://www.google.com/search?q={clean_q}+filetype:pdf")
    with c2:
        st.link_button("📊 Прайсы XLS в Яндекс", f"https://yandex.ru/search/?text={clean_q}+прайс+xls")
    with c3:
        st.link_button("📱 Соцсети и VK", f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={clean_q}")

st.divider()
st.caption(f"Инструмент коммерческого отдела компании «Первый Снег». Сезон {TARGET_YEAR}.")
