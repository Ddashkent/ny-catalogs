import concurrent.futures
import io
import re
import urllib.parse
import zipfile
from bs4 import BeautifulSoup
from PIL import Image
import requests
import streamlit as st
import urllib3
from duckduckgo_search import DDGS

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# НАСТРОЙКИ СТРАНИЦЫ
st.set_page_config(
    page_title="Профессиональный поиск новогодних каталогов",
    page_icon="🎁",
    layout="wide",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# =========================================================
# 🎯 ЗОЛОТОЙ РЕЕСТР ПОСТАВЩИКОВ ЕАЭС
# =========================================================
GOLDEN_REGISTRY = {
    "дари радость": "https://dari-radost.ru",
    "спартак": "https://spartak.by",
    "коммунарка": "https://www.kommunarka.by",
    "абинекс": "https://podarok-k.ru",
    "солбигтрейд": "https://конфета.бел",
    "солбиг трейд": "https://конфета.бел",
    "рубин": "https://rubin-2000.ru",
    "академия шоколада": "https://chocohunter.ru",
    "рахат": "https://rakhat.kz",
    "баян сулу": "https://www.bayansulu.kz",
    "миракс": "https://mirax-gifts.ru",
    "дилявер": "https://dilyaver.com",
    "росшоколад": "https://roschocolate.ru",
    "акконд": "https://akkond.ru",
    "лаконд": "https://lakond.ru",
    "рэйд 21": "https://podarki-reid21.ru",
    "рэйд": "https://podarki-reid21.ru",
    "главупак": "https://glavupak.ru",
    "дедморозов": "https://dedmorozov.ru",
}

# =========================================================
# 🔎 ИНТЕЛЛЕКТУАЛЬНЫЙ ПОИСКОВИК
# =========================================================


def find_official_site(company_name):
  name_low = company_name.lower().strip()

  # 1. Проверяем золотой реестр
  for key, site_url in GOLDEN_REGISTRY.items():
    if key in name_low or name_low in key:
      return site_url

  # 2. Если пользователь ввел прямой URL
  if "." in name_low and " " not in name_low:
    return (
        name_low if name_low.startswith("http") else f"https://{name_low}"
    )

  # 3. Веб-поиск через DDGS (без жестких заглушек)
  try:
    with DDGS() as ddgs:
      query = (
          f"{company_name} официальный сайт новогодние подарки упаковка каталог"
      )
      results = list(ddgs.text(query, max_results=8))

      for r in results:
        url = r["href"].lower()
        bad_domains = [
            "imdb.com",
            "wikipedia",
            "vk.com",
            "ok.ru",
            "facebook",
            "instagram",
            "youtube",
            "2gis",
            "avito",
            "ozon",
            "wildberries",
        ]
        if not any(bad in url for bad in bad_domains):
          return r["href"]
  except Exception:
    pass

  return None


# =========================================================
# 🕷 СКАНЕР КАТАЛОГОВ И ИЗОБРАЖЕНИЙ
# =========================================================


def fix_url(base, src):
  if not src:
    return ""
  src = src.strip()
  if src.startswith("//"):
    src = "https:" + src
  try:
    full = urllib.parse.urljoin(base, src)
    p = urllib.parse.urlparse(full)
    host = p.netloc.encode("idna").decode("ascii")
    path = urllib.parse.quote(urllib.parse.unquote(p.path))
    query = urllib.parse.quote(urllib.parse.unquote(p.query), safe="=&?")
    return urllib.parse.urlunparse(p._replace(netloc=host, path=path, query=query))
  except Exception:
    return src


def scan_site(start_url):
  try:
    r = requests.get(start_url, headers=HEADERS, timeout=12, verify=False)
    if r.status_code != 200:
      return [], []
    soup = BeautifulSoup(r.text, "lxml")
    domain = urllib.parse.urlparse(start_url).netloc
  except Exception:
    return [], []

  # Собираем целевые страницы (разделы и категории)
  sections = {start_url}
  for a in soup.find_all("a", href=True):
    href = fix_url(start_url, a["href"])
    if domain in href:
      txt = (a.get_text() + " " + href).lower()
      if any(
          w in txt
          for w in [
              "catalog",
              "podarki",
              "novogod",
              "upakovka",
              "category",
              "page",
              "pagen",
          ]
      ):
        sections.add(href.split("#")[0])

  keywords = [
      "подар",
      "набор",
      "новогод",
      "короб",
      "упаков",
      "туб",
      "каталог",
      "2025",
      "2026",
      "2027",
      "present",
      "gift",
      "box",
  ]

  all_pdfs = []
  all_imgs = []

  def parse_page(url):
    try:
      res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
      if res.status_code != 200:
        return [], []
      p_soup = BeautifulSoup(res.text, "lxml")
      p_pdfs, p_imgs = [], []

      # Поиск PDF
      for a in p_soup.find_all("a", href=True):
        href = fix_url(url, a["href"])
        if href.lower().split("?")[0].endswith(".pdf"):
          txt = a.get_text().strip()
          if any(k in (txt + href).lower() for k in keywords):
            p_pdfs.append(
                {"name": txt or "Новогодний каталог PDF", "url": href}
            )

      # Поиск изображений
      for img in p_soup.find_all(["img", "source"]):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("srcset")
            or img.get("src")
        )
        if not src:
          continue
        if "," in src:
          src = src.split(",")[-1].strip().split(" ")[0]

        img_url = fix_url(url, src)
        alt = (img.get("alt") or img.get("title") or "").strip()

        # Фильтр: только подарки/упаковка, без логотипов
        if any(k in (alt + img_url).lower() for k in keywords):
          if not any(
              bad in img_url.lower()
              for bad in [
                  "logo",
                  "icon",
                  "social",
                  "banner",
                  "visa",
                  "cart",
                  "truck",
                  "header",
                  "footer",
              ]
          ):
            p_imgs.append({"name": alt or "Новогодний подарок", "url": img_url})

      return p_pdfs, p_imgs
    except Exception:
      return [], []

  # Многопоточный обход страниц
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    futures = [
        executor.submit(parse_page, u) for u in list(sections)[:30]
    ]
    for f in concurrent.futures.as_completed(futures):
      p, i = f.result()
      all_pdfs.extend(p)
      all_imgs.extend(i)

  # Уникализируем
  final_pdfs = list({v["url"]: v for v in all_pdfs}.values())
  final_imgs = list({v["url"]: v for v in all_imgs}.values())

  return final_pdfs, final_imgs


# =========================================================
# 📥 НАДЕЖНАЯ ЗАГРУЗКА КАРТИНКИ
# =========================================================


def download_single_image(img_info):
  url = img_info["url"]
  # Способ 1: Прямое скачивание
  try:
    r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
    if r.status_code == 200 and len(r.content) > 2000:
      return {"bytes": r.content, "name": img_info["name"]}
  except Exception:
    pass

  # Способ 2: Через графический мост (если сайт блокирует прямые запросы)
  try:
    proxy_url = f"https://wsrv.nl/?url={urllib.parse.quote(url)}&n=-1"
    r = requests.get(proxy_url, timeout=8)
    if r.status_code == 200 and len(r.content) > 2000:
      return {"bytes": r.content, "name": img_info["name"]}
  except Exception:
    pass

  return None


# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.title("🎁 Профессиональный поиск новогодних каталогов")
st.markdown(
    "Поиск по базе производителей **ЕАЭС (РФ, РБ, КЗ)**. Автоматический сбор"
    " каталогов и упаковки."
)

company = st.text_input(
    "Введите название компании (например: Дари радость, Спартак, Абинекс, СолБигТрейд):",
    placeholder="Дари радость",
)

if company:
  if st.button("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ", type="primary"):
    with st.spinner(f"Ищем официальный сайт для «{company}»..."):
      site = find_official_site(company)

    if site:
      st.success(f"✅ Найден официальный сайт: **[{site}]({site})**")

      with st.spinner("Анализируем каталог и карточки товаров..."):
        pdfs, imgs = scan_site(site)

        col1, col2 = st.columns(2)

        # Вывод PDF
        with col1:
          st.subheader(f"📄 PDF Каталоги ({len(pdfs)})")
          if pdfs:
            for p in pdfs:
              st.info(f"👉 **[{p['name']}]({p['url']})**")
          else:
            st.write("Прямых PDF-файлов не найдено.")

        # Вывод и скачивание Изображений
        with col2:
          st.subheader(f"🖼 Упаковка и подарки ({len(imgs)})")
          if imgs:
            # СБОРКА ZIP-АРХИВА
            with st.spinner("Упаковываем картинки в ZIP-архив..."):
              zip_buffer = io.BytesIO()
              valid_count = 0

              with zipfile.ZipFile(
                  zip_buffer, "w", zipfile.ZIP_DEFLATED
              ) as zf:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=10
                ) as executor:
                  results = list(
                      executor.map(download_single_image, imgs[:300])
                  )
                  for res in results:
                    if res:
                      valid_count += 1
                      clean_title = (
                          re.sub(r"[^\w\s-]", "", res["name"])[:30].strip()
                      )
                      filename = f"gift_{valid_count:03d}_{clean_title or 'box'}.jpg"
                      zf.writestr(filename, res["bytes"])

            # КНОПКА СКАЧИВАНИЯ (ОТОБРАЖАЕТСЯ ВСЕГДА)
            if valid_count > 0:
              st.download_button(
                  label=f"📥 СКАЧАТЬ ВСЕ ФОТО В ZIP-АРХИВЕ ({valid_count} шт.)",
                  data=zip_buffer.getvalue(),
                  file_name=f"{company.replace(' ', '_')}_catalog.zip",
                  mime="application/zip",
                  type="primary",
                  use_container_width=True,
              )
            else:
              st.warning(
                  "Изображения найдены, но сайт заблокировал их прямое"
                  " скачивание."
              )

            st.write("---")
            # Превью сетки
            grid = st.columns(3)
            for i, item in enumerate(imgs[:9]):
              grid[i % 3].image(item["url"], use_container_width=True)
          else:
            st.warning("Изображения подарков не найдены.")
    else:
      # Понятная ошибка без лишних текстов
      st.error(
          f"❌ Не удалось автоматически найти сайт для компании «{company}»."
          " Попробуйте ввести точный адрес сайта (например: dari-radost.ru)."
      )
