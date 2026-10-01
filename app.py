import concurrent.futures
import csv
import datetime
import io
import re
import time
import urllib.parse
import zipfile
from collections import deque

import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
  from PIL import Image

  HAS_PIL = True
except ImportError:
  HAS_PIL = False

# =========================================================
# ❄️ НАСТРОЙКИ И ДИЗАЙН «ПЕРВЫЙ СНЕГ»
# =========================================================

CURRENT_YEAR = datetime.date.today().year
NEXT_YEAR = CURRENT_YEAR + 1
TARGET_YEARS = {CURRENT_YEAR, NEXT_YEAR, NEXT_YEAR + 1}

MAX_PAGES = 40
PAGE_WORKERS = 4
IMAGE_WORKERS = 6

st.set_page_config(
    page_title="Первый Снег | Экстрактор Упаковки",
    page_icon="❄️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #f8fafc; }

    .company-logo {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: white !important;
        font-weight: 900; padding: 8px 18px; border-radius: 8px;
        border: 2px solid white; box-shadow: 0 4px 12px rgba(220, 38, 38, 0.30);
        letter-spacing: 1px;
    }

    .doc-card {
        background-color: white; border-left: 6px solid #dc2626;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.04);
    }

    .doc-button {
        display: inline-block; background-color: #dc2626;
        color: white !important; font-weight: 700; padding: 9px 18px;
        margin-top: 8px; border-radius: 7px; text-decoration: none;
    }

    .product-title {
        min-height: 42px; margin: 5px 0; color: #1e293b;
        font-size: 13px; font-weight: 700; line-height: 1.3;
    }

    .badge-box {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background-color: #16a34a; color: white; font-size: 11px; font-weight: 700;
    }

    .badge-weight {
        display: inline-block; padding: 3px 8px; border-radius: 6px;
        background-color: #dc2626; color: white; font-size: 11px; font-weight: 700;
    }
    </style>

    <div class="company-logo">❄️ ПЕРВЫЙ СНЕГ</div>
    """,
    unsafe_allow_html=True,
)

st.title("📦 Экстрактор Новогодних Наборов и Упаковки")
st.caption(
    "Поиск PDF-каталогов и коробок (картон, МГК, тубы). Одиночные конфеты,"
    " жесть, текстиль и рекламные баннеры отсеиваются."
)

# =========================================================
# 🎯 ПРОВЕРЕННАЯ БАЗА ПРОИЗВОДИТЕЛЕЙ (ТОЧНЫЕ АДРЕСА)
# =========================================================

EXPERT_DIRECTORY = {
    "коммунарка": "https://www.kommunarka.by",
    "спартак": "https://spartak.by",
    "рубин": "https://rubin-2000.ru",
    "рубин тг": "https://rubin-tg.ru",
    "академия шоколада": "https://chocolate-academy.ru",
    "рахат": "https://rakhat.kz",
    "баян сулу": "https://www.bayansulu.kz",
    "акконд": "https://akkond.ru",
    "лаконд": "https://lakond.ru",
    "донко": "https://donko.su",
    "дилявер": "https://dilaver.ru",
    "главупак": "https://glavupak.ru",
    "дедморозов": "https://dedmorozov.ru",
    "славянка": "https://slavyanka.ru",
    "миракс": "https://mirax-gifts.ru",
    "москондитер": "https://mosconditer.ru",
    "росшоколад": "https://roschocolate.ru",
    "рэйд": "https://podarki-reid21.ru",
}

START_PATHS = {
    "kommunarka.by": ["/catalog/novogodnie-podarki/", "/catalog/"],
    "spartak.by": ["/catalog/novogodnyaya-produktsiya/", "/catalog/"],
    "rubin-2000.ru": ["/catalog/"],
    "chocolate-academy.ru": ["/catalog/novogodnie-podarki/", "/catalog/"],
    "rakhat.kz": ["/products/novogodnie-podarki/", "/products/"],
    "bayansulu.kz": ["/ru/catalog/", "/catalog/"],
}

# =========================================================
# 📦 СЛОВАРЬ ФИЛЬТРАЦИИ МАТЕРИАЛОВ И НАБОРОВ
# =========================================================

TARGET_BOX_WORDS = [
    "набор",
    "подарок",
    "подарки",
    "упаковк",
    "коробк",
    "туб",
    "тубус",
    "сундуч",
    "домик",
    "книг",
    "футляр",
    "шкатулк",
    "баульч",
    "чемоданчик",
    "картон",
    "микрогофр",
    "гофро",
    "мгк",
    "переплет",
    "переплёт",
    "кашир",
    "комплект",
    "сладкий подарок",
]

EXCLUDE_SINGLE_CANDIES = [
    "конфета",
    "конфеты весовые",
    "батончик",
    "плитка шоколада",
    "шоколадка",
    "драже",
    "карамелька",
    "вафля",
    "вафли",
    "печенье",
    "зефир",
    "ирис",
    "мармелад весовой",
    "поштучно",
]

EXCLUDE_MATERIALS = [
    "жесть",
    "жестяная",
    "металл",
    "tin",
    "текстиль",
    "ткань",
    "мешок",
    "мешочек",
    "рюкзак",
    "подушка",
    "плюш",
    "мягкая игрушка",
    "дерево",
    "фанера",
    "пластик",
    "пвх",
]

JUNK_IMAGE_WORDS = [
    "logo",
    "icon",
    "banner",
    "slider",
    "sprite",
    "placeholder",
    "social",
    "avatar",
    "payment",
    "delivery",
    "header",
    "footer",
    "menu",
    "arrow",
    "captcha",
    "counter",
    "metrika",
]

JUNK_DOCUMENT_WORDS = [
    "презентация",
    "соглашение",
    "политика",
    "конфиденциальность",
    "персональные данные",
    "договор",
    "оферта",
    "вакансии",
    "реквизиты",
    "cookies",
    "устав",
    "инвесторам",
    "соут",
    "privacy",
    "policy",
]

DOCUMENT_WORDS = [
    "каталог",
    "catalog",
    "прайс",
    "price",
    "новогод",
    "подарки",
    "gift",
]

WEIGHT_REGEX = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)", re.IGNORECASE
)

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ (ПОСЛЕДОВАТЕЛЬНЫЙ И БЕЗОПАСНЫЙ)
# =========================================================


def create_http_session():
  session = requests.Session()
  session.headers.update({
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
      ),
      "Accept": (
          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
      ),
      "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
      "Cache-Control": "no-cache",
  })
  session.verify = False

  retry = Retry(
      total=2,
      backoff_factor=0.5,
      status_forcelist=[500, 502, 503, 504],
      raise_on_status=False,
  )

  adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
  session.mount("https://", adapter)
  session.mount("http://", adapter)
  return session


SESSION = create_http_session()


def safe_fetch(url, timeout=(10, 25)):
  """Безопасный запрос с нормальным таймаутом без провоцирования фаерволов"""
  try:
    resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
    if resp.status_code == 200 and len(resp.content) > 300:
      resp.encoding = resp.apparent_encoding or "utf-8"
      return resp.url, resp.text, None
    return None, None, f"HTTP {resp.status_code}"
  except Exception as e:
    return None, None, str(e)


def connect_sequentially(target_url):
  """Последовательная проверка адресов без спама параллельными SYN-пакетами"""
  # 1. Пробуем прямой URL
  final_url, html, err = safe_fetch(target_url)
  if html:
    return final_url, html, None

  # 2. Если прямой адрес не ответил, пробуем варианты по очереди с паузой
  parsed = urllib.parse.urlparse(target_url)
  host = parsed.netloc.replace("www.", "") or parsed.path.split("/")[0]

  variants = [
      f"https://www.{host}/",
      f"https://{host}/",
      f"http://www.{host}/",
      f"http://{host}/",
  ]

  errors = [f"{target_url}: {err}"]

  for variant in variants:
    if variant.rstrip("/") == target_url.rstrip("/"):
      continue
    time.sleep(0.4)  # Пауза, чтобы сервер не принял за атакующую бота-сеть
    final_url, html, err = safe_fetch(variant)
    if html:
      return final_url, html, None
    errors.append(f"{variant}: {err}")

  return None, None, errors


def resolve_site_url(company_input):
  q = company_input.lower().strip()

  # Прямая ссылка
  if q.startswith(("http://", "https://")):
    return q
  if "." in q and " " not in q:
    return f"https://{q}"

  # Поиск в базе
  for key, url in EXPERT_DIRECTORY.items():
    if key in q or q in key:
      return url

  # Транслитерация для незнакомых компаний
  char_map = {
      "а": "a",
      "б": "b",
      "в": "v",
      "г": "g",
      "д": "d",
      "е": "e",
      "ё": "e",
      "ж": "zh",
      "з": "z",
      "и": "i",
      "й": "y",
      "к": "k",
      "л": "l",
      "м": "m",
      "н": "n",
      "о": "o",
      "п": "p",
      "р": "r",
      "с": "s",
      "т": "t",
      "у": "u",
      "ф": "f",
      "х": "h",
      "ц": "c",
      "ч": "ch",
      "ш": "sh",
      "щ": "shch",
      "ъ": "",
      "ы": "y",
      "ь": "",
      "э": "e",
      "ю": "yu",
      "я": "ya",
  }
  slug = "".join(char_map.get(c, c) for c in q if c.isalnum() or c.isspace())
  slug = re.sub(r"\s+", "-", slug).strip("-")

  return f"https://{slug}.ru"


def fix_url(base_url, href):
  href = (href or "").strip()
  if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:")):
    return ""
  if href.startswith("//"):
    href = "https:" + href
  full = urllib.parse.urljoin(base_url, href)
  parsed = urllib.parse.urlparse(full)
  safe_path = urllib.parse.quote(
      urllib.parse.unquote(parsed.path), safe="/:@-._~"
  )
  safe_query = urllib.parse.quote(
      urllib.parse.unquote(parsed.query), safe="=&?+/:,@-._~"
  )
  return urllib.parse.urlunparse(
      (parsed.scheme, parsed.netloc, safe_path, parsed.params, safe_query, "")
  )


# =========================================================
# 🔍 ЛОГИКА ФИЛЬТРАЦИИ НАБОРОВ И УПАКОВКИ
# =========================================================


def is_box_or_set(title, context_text, url):
  """Жесткий фильтр: отбрасывает одиночные конфеты, жесть, текстиль и оставляет только наборы/коробки"""
  combined = f"{title} {context_text} {url}".lower()

  # 1. Отбраковываем материалы не по спецификации (жесть, мешки, мягкие игрушки)
  if any(bad in combined for bad in EXCLUDE_MATERIALS):
    return False

  # 2. Если это одиночные весовые конфеты или плитки и НЕТ признака подарка/коробки
  has_single = any(single in combined for single in EXCLUDE_SINGLE_CANDIES)
  has_box = any(box in combined for box in TARGET_BOX_WORDS)

  if has_single and not has_box:
    return False

  # 3. Должно быть упоминание набора, подарка, коробки или тубы
  return has_box or "podar" in url.lower() or "novogod" in url.lower()


def scan_single_page(url, domain):
  _, html, _ = safe_fetch(url, timeout=(8, 15))
  if not html:
    return [], []

  soup = BeautifulSoup(html, "lxml")
  for junk in soup.select("script, style, footer, header, nav"):
    junk.decompose()

  page_context = (
      soup.title.get_text(" ", strip=True) if soup.title else ""
  ) + " " + url

  pdfs, imgs = [], []

  # Сбор PDF
  for a in soup.find_all("a", href=True):
    href = fix_url(url, a["href"])
    if href.lower().split("?")[0].endswith((".pdf", ".xlsx", ".xls")):
      text = a.get_text().strip()
      comb = f"{text} {href}".lower()
      if any(bad in comb for bad in JUNK_DOCUMENT_WORDS):
        continue
      if any(good in comb for good in DOCUMENT_WORDS):
        pdfs.append(
            {"name": text or "Официальный каталог PDF", "url": href}
        )

  # Сбор Картинок Наборов/Коробок
  for img in soup.find_all("img"):
    src = (
        img.get("src")
        or img.get("data-src")
        or img.get("data-original")
        or img.get("data-lazy-src")
    )
    if not src:
      continue

    full_img = fix_url(url, src)
    if not full_img or any(junk in full_img.lower() for junk in JUNK_IMAGE_WORDS):
      continue

    alt = (img.get("alt") or img.get("title") or "").strip()
    parent_text = (
        img.parent.get_text(" ", strip=True) if img.parent else ""
    )[:300]

    title = alt or parent_text[:60] or "Подарочный набор / Коробка"

    if is_box_or_set(title, parent_text + " " + page_context, full_img):
      weight_match = WEIGHT_REGEX.search(parent_text + " " + title)
      weight = weight_match.group(1) if weight_match else None
      imgs.append({
          "title": title[:100],
          "weight": weight,
          "url": full_img,
          "page_url": url,
      })

  return pdfs, imgs


def deep_scan_site(start_url):
  domain = urllib.parse.urlparse(start_url).netloc.replace("www.", "")

  final_start_url, main_html, errors = connect_sequentially(start_url)
  if not main_html:
    return None, None, 0, errors

  soup = BeautifulSoup(main_html, "lxml")

  # Находим разделы каталогов
  pages_to_scan = {final_start_url}

  # Добавляем заведомо известные глубокие пути
  for path in START_PATHS.get(domain, ["/catalog/"]):
    pages_to_scan.add(urllib.parse.urljoin(final_start_url, path))

  for a in soup.find_all("a", href=True):
    href = fix_url(final_start_url, a["href"])
    if (
        href
        and urllib.parse.urlparse(href).netloc.replace("www.", "") == domain
    ):
      txt = (a.get_text() + " " + href).lower()
      if any(
          k in txt
          for k in [
              "catalog",
              "novogod",
              "podarki",
              "karton",
              "tuba",
              "upakov",
              "2025",
              "2026",
              "2027",
          ]
      ):
        pages_to_scan.add(href)

  scan_queue = list(pages_to_scan)[:MAX_PAGES]

  all_pdfs, all_imgs = [], []

  with concurrent.futures.ThreadPoolExecutor(
      max_workers=PAGE_WORKERS
  ) as executor:
    futures = [
        executor.submit(scan_single_page, url, domain) for url in scan_queue
    ]
    for f in concurrent.futures.as_completed(futures):
      try:
        p, i = f.result()
        all_pdfs.extend(p)
        all_imgs.extend(i)
      except Exception:
        continue

  unique_pdfs = list({item["url"]: item for item in all_pdfs}.values())
  unique_imgs = list({item["url"]: item for item in all_imgs}.values())

  return unique_pdfs, unique_imgs, len(scan_queue), None


# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

company_input = st.text_input(
    "Введите название компании:",
    placeholder=(
        "Например: Коммунарка, Спартак, Рахат, Рубин, Акконд, Лаконд..."
    ),
)

if st.button(
    "🚀 НАЙТИ КАТАЛОГИ И ПОДАРОЧНЫЕ НАБОРЫ",
    type="primary",
    use_container_width=True,
):
  if not company_input.strip():
    st.warning("Пожалуйста, введите название компании.")
    st.stop()

  target_start_url = resolve_site_url(company_input)
  st.info(f"🌐 Целевой адрес для подключения: `{target_start_url}`")

  with st.spinner(
      "Подключение и глубокий сканинг категорий коробок и наборов..."
  ):
    pdfs, imgs, pages_count, errors = deep_scan_site(target_start_url)

  if pdfs is None and imgs is None:
    st.error(
        f"❌ Не удалось подключиться к сайту {target_start_url}. Сервер не"
        " ответил на запрос."
    )
    if errors:
      with st.expander("Техническая диагностика подключения"):
        for err in errors:
          st.code(err)
  else:
    st.success(
        f"✅ Сканирование завершено. Обработано страниц: **{pages_count}**"
    )

    col1, col2 = st.columns(2)

    with col1:
      st.subheader(f"📄 PDF / Excel Каталоги ({len(pdfs)})")
      if pdfs:
        for doc in pdfs:
          st.markdown(
              f"""
                    <div class="doc-card">
                        <div><b>📕 {doc['name']}</b></div>
                        <a href="{doc['url']}" target="_blank" class="doc-button">📥 СКАЧАТЬ КАТАЛОГ</a>
                    </div>
                    """,
              unsafe_allow_html=True,
          )
      else:
        st.info("PDF-каталоги не обнаружены.")

    with col2:
      st.subheader(f"📦 Подарочные наборы и коробки ({len(imgs)})")
      if imgs:
        # ZIP Выгрузка
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
          for idx, item in enumerate(imgs[:400], start=1):
            try:
              res = SESSION.get(item["url"], timeout=8)
              if res.status_code == 200:
                clean_title = (
                    re.sub(r"[^\w\-]+", "_", item["title"])[:35] or "item"
                )
                ext = "jpg"
                if ".png" in item["url"].lower():
                  ext = "png"
                elif ".webp" in item["url"].lower():
                  ext = "webp"
                zf.writestr(f"box_{idx:03d}_{clean_title}.{ext}", res.content)
            except Exception:
              continue

        st.download_button(
            f"📥 СКАЧАТЬ ZIP С КАРТИНКАМИ НАБОРОВ ({len(imgs)} шт.)",
            data=zip_buffer.getvalue(),
            file_name="gift_boxes_catalog.zip",
            mime="application/zip",
            type="primary",
        )

        st.write("---")
        grid = st.columns(3)
        for idx, item in enumerate(imgs[:9]):
          with grid[idx % 3]:
            st.markdown(
                f"""
                        <div style="text-align:center;">
                            <div class="product-title">{item['title']}</div>
                            <span class="badge-box">🎁 НАБОР / КОРОБКА</span>
                            {f'<span class="badge-weight">⚖️ {item["weight"]}</span>' if item['weight'] else ''}
                        </div>
                        """,
                unsafe_allow_html=True,
            )
            st.image(item["url"], use_container_width=True)
      else:
        st.info("Подарочные наборы и коробки не найдены.")

st.divider()
st.caption(
    "Инструмент «Первый Снег» | Фильтрация конфет активна | Безопасное"
    " последовательное соединение."
)
