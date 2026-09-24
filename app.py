import datetime
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st

# 1. Настройка страницы
st.set_page_config(
    page_title="Каталоги Подарков 2026", page_icon="🍬", layout="centered"
)

st.markdown(
    """
    <style>
    .stApp { background-color: #f4f7f6; }
    .catalog-card { 
        background-color: #ffffff; border-left: 6px solid #28a745; 
        padding: 18px; border-radius: 12px; margin-bottom: 12px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    }
    .download-btn {
        background-color: #28a745; color: white !important;
        padding: 10px 20px; border-radius: 6px; text-decoration: none;
        font-weight: bold; display: inline-block; margin-top: 8px;
    }
    .download-btn:hover { background-color: #218838; }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🍬 Навигатор Подарков 2026")
st.write(
    "Введите название фабрики. Система найдет официальный сайт и вытянет прямую ссылку на каталог 2026."
)

target_year = 2026

# --- БАЗА БЫСТРОГО ДОСТУПА (Ускоряет поиск для известных брендов) ---
KNOWLEDGE_BASE = {
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
    "лоте рахат": "rakhat.kz",
    "баян сулу": "bayansulu.kz",
    "баянсулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "саратовская кф": "confashion.ru",
    "тореро": "torero.ru",
    "абинекс": "abineks.ru",
    "рэйд-21": "raid21.ru",
    "сибпродторг": "sibprodtorg.ru",
    "столичные поставки": "stolichnye.ru",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "рот фронт": "uniconf.ru",
    "бабаевский": "uniconf.ru",
    "аленка": "podarki.alenka.ru",
    "фортуна": "fortuna-podarki.ru",
    "победа": "pobeda.market",
    "славянка": "slavyanka.sendy.ru",
}

# Домены-справочники, которые мы игнорируем при авто-поиске сайтов
JUNK_DOMAINS = [
    "wikipedia.org",
    "otzovik.com",
    "avito.ru",
    "list-org.com",
    "checko.ru",
    "audit-it.ru",
    "synapsenet.ru",
    "hh.ru",
    "rabota.ru",
    "pravo.ru",
    "pravoved.ru",
    "krasotaimedicina.ru",
    "espn.com",
    "365scores.com",
]

# Списки фильтрации контента
GOOD_EXT = [
    ".pdf",
    ".xls",
    ".xlsx",
    ".doc",
    "/catalog/",
    "/podarki/",
    "/products/",
    "/novogod",
]
GOOD_WORDS = [
    "каталог",
    "прайс",
    "подарк",
    "новогод",
    "нг", "2026",
    "лошад",
    "catalog",
    "price",
    "podarki",
]
BAD_WORDS = [
    "медицина",
    "врач",
    "рейтинг",
    "отзывы",
    "статья",
    "wiki",
    "hockey",
    "хоккей",
    "политика",
    "данных",
    "согласие",
    "соглашение",
    "вакансии",
    "stock",
    "finance",
    "инвесторам",
]

# --- ФУНКЦИИ ---


def is_clean_link(text, href):
    """Проверяет ссылку на актуальность и фильтрует мусор"""
    full = (text + " " + href).lower()
    if any(bad in full for bad in BAD_WORDS):
        return False
    if any(good in full for good in GOOD_WORDS) or any(
        href.lower().endswith(ext) for ext in [".pdf", ".xls", ".xlsx"]
    ):
        return True
    return False


def scan_website(url):
    """Заходит на сайт и вытаскивает все ссылки на каталоги/подарки"""
    files = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        base_url = url if url.startswith("http") else f"http://{url}"
        res = requests.get(base_url, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip()

                if is_clean_link(text, href):
                    full_link = urllib.parse.urljoin(base_url, a["href"])
                    title = text or "Каталог продукции / Прайс 2026"
                    if full_link not in [f["link"] for f in files]:
                        files.append({"title": title, "link": full_link})
    except:
        pass
    return files


def find_site_via_search(query):
    """Универсальный поиск официального сайта для ЛЮБОЙ новой компании"""
    try:
        with DDGS() as ddgs:
            q = f'"{query}" кондитерская фабрика официальный сайт -wiki -list-org'
            res = list(ddgs.text(q, region="ru-ru", max_results=5))
            for r in res:
                link = r["href"]
                if not any(junk in link.lower() for junk in JUNK_DOMAINS):
                    parsed = urllib.parse.urlparse(link)
                    return parsed.netloc or link
    except:
        return None
    return None


# --- ИНТЕРФЕЙС ---

company_input = st.text_input(
    "Название компании или бренда:",
    placeholder="Например: Лаконд, Баян Сулу, Красный Мозырянин...",
)

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ 2026", type="primary"):
    if not company_input.strip():
        st.error("Введите название компании!")
    else:
        query = company_input.lower().strip()
        st.write(f"🔍 Ищем информацию для: **{company_input.strip()}**")

        # 1. Поиск в Базе Быстрого Доступа
        target_site = None
        for key, domain in KNOWLEDGE_BASE.items():
            if key in query or query in key:
                target_site = domain
                break

        # 2. Если в базе нет — динамически находит сайт в сети
        if not target_site:
            with st.spinner("Автоматически определяю официальный сайт..."):
                target_site = find_site_via_search(query)

        links = []

        if target_site:
            st.info(f"🌐 Найден официальный сайт: `{target_site}`")

            # 3. Сканируем найденный сайт
            with st.spinner("Извлекаю прямые ссылки на каталоги и прайсы..."):
                links = scan_website(target_site)

                # Если на главной пусто, пробуем прямой поиск PDF на этом домене
                if not links:
                    try:
                        with DDGS() as ddgs:
                            pdf_q = f"site:{target_site} (каталог OR прайс) (новогодние подарки OR 2026 OR лошад) filetype:pdf"
                            extra = list(ddgs.text(pdf_q, max_results=5))
                            for e in extra:
                                links.append(
                                    {"title": e["title"], "link": e["href"]}
                                )
                    except:
                        pass

        # Вывод результатов
        st.markdown("---")
        if links:
            st.success(f"Найдено прямых ресурсов: {len(links)}")
            unique_links = {l["link"]: l for l in links}.values()
            for l in unique_links:
                icon = (
                    "📕 PDF"
                    if ".pdf" in l["link"].lower()
                    else ("📊 EXCEL" if ".xls" in l["link"].lower() else "🌐")
                )
                st.markdown(
                    f"""
                <div class="catalog-card">
                    <h4 style="margin:0; font-size:16px;">{icon} | {l['title']}</h4>
                    <a href="{l['link']}" target="_blank" class="download-btn">📥 СКАЧАТЬ / ОТКРЫТЬ ФАЙЛ 2026</a>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.warning(
                "Автоматика не вытянула прямые файлы. Воспользуйтесь снайперскими кнопками ниже:"
            )

        # Резервный блок кнопок (гарантирует результат для менеджера)
        st.write("### 🔍 Быстрый поиск в один клик:")
        c1, c2, c3 = st.columns(3)

        clean_q = urllib.parse.quote(
            f'"{company_input.strip()}" новогодние подарки каталог 2026 -хоккей -stock'
        )
        xls_q = urllib.parse.quote(
            f'"{company_input.strip()}" прайс новогодние подарки 2026 (xls OR pdf)'
        )
        vk_q = urllib.parse.quote(
            f'"{company_input.strip()}" новогодние подарки 2026'
        )

        with c1:
            st.link_button(
                "📕 PDF в Google",
                f"https://www.google.com/search?q={clean_q}+filetype:pdf",
            )
        with c2:
            st.link_button(
                "📊 Прайсы в Яндекс", f"https://yandex.ru/search/?text={xls_q}"
            )
        with c3:
            st.link_button(
                "📱 Группы в VK",
                f"https://vk.com/search?c%5Bsection%5D=auto&c%5Bq%5D={vk_q}",
            )

st.divider()
st.caption(
    "Автоматика настроена на сезон 2026 (Год Лошади). Финансовый и спортивный мусор отфильтровывается."
)
