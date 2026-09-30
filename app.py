import io
import re
import zipfile
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import requests
import streamlit as st

# ==========================================
# 🛑 ЧЕРНЫЕ СПИСКИ (Что ИСКЛЮЧАЕМ)
# ==========================================

# Черный список для PDF (документы, не относящиеся к подаркам)
PDF_BLACKLIST = [
    'политик',
    'конфиденц',
    'согласи',
    'персональн',
    'обработк',
    'устав',
    'лицензи',
    'сертификат',
    'реквизит',
    'договор',
    'оферт',
    'паспорт',
    'инструкци',
    'положение',
    'стандарт',
    'качеств',
    'оплата',
    'доставка',
    'privacy',
    'policy',
    'consent',
    'terms',
    'license',
]

# Черный список для картинок (логотипы, кнопки, соцсети)
IMG_BLACKLIST = [
    'logo',
    'icon',
    'banner',
    'button',
    'social',
    'vk',
    'fb',
    'instagram',
    'telegram',
    'cart',
    'avatar',
    'payment',
    'header',
    'footer',
    'pixel',
    'mastercard',
    'visa',
    'mir',
]

# ==========================================
# 🎯 БЕЛЫЙ СПИСОК (Что ИЩЕМ: Новый Год и Упаковка)
# ==========================================
TARGET_KEYWORDS = [
    'новогод',
    'новый год',
    'подар',
    'упаков',
    'каталог',
    '2025',
    '2024',
    'коробк',
    'жесть',
    'картон',
    'туба',
    'текстиль',
    'символ',
    'змея',
    'дракон',
    'сладк',
    'набор',
    'gift',
    'box',
    'catalog',
    'ny',
    'newyear',
]

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(
    page_title="Поиск новогодних каталогов ЕАЭС", page_icon="🎁", layout="wide"
)
st.title("🚀 НАЙТИ КАТАЛОГ И УПАКОВКУ")


def find_official_website(query):
  """Ищет официальный сайт компании в интернете, если введен не URL"""
  # Если пользователь уже ввел URL (например spartak.by или https://...)
  if "." in query and not " " in query:
    if not query.startswith(("http://", "https://")):
      return f"https://{query}"
    return query

  # Если введено название компании (например "спартак")
  st.info(f"🔎 Ищем официальный сайт для: **{query}**...")
  try:
    with DDGS() as ddgs:
      results = list(
          ddgs.text(
              f"{query} официальный сайт каталог новогодние подарки упаковка",
              max_results=3,
          )
      )
      if results:
        target_url = results[0]["href"]
        st.success(f"Найден сайт: **{target_url}**")
        return target_url
  except Exception as e:
    st.warning(f"Не удалось автоматически найти сайт через поиск: {e}")

  return None


def is_pdf_valid(text, url):
  """Проверяет PDF: удаляет юридический мусор и оставляет только новогодние каталоги"""
  combined = (text + " " + url).lower()

  # 1. Если есть слова из черного списка — отклоняем
  if any(bad in combined for bad in PDF_BLACKLIST):
    return False

  # 2. Должно быть хотя бы одно ключевое слово (Новый год, каталог, упаковка и т.д.)
  if any(good in combined for good in TARGET_KEYWORDS):
    return True

  return False


def is_img_valid(alt, src):
  """Фильтрует баннеры и логотипы, оставляет фото упаковки/подарков"""
  combined = (alt + " " + src).lower()

  # Отсекаем логотипы и системные иконки
  if any(bad in combined for bad in IMG_BLACKLIST):
    return False

  # Оставляем, если упоминаются подарки/упаковка или если картинка из раздела каталога
  if any(good in combined for good in TARGET_KEYWORDS):
    return True

  return False


def get_soup(url):
  """Безопасно загружает HTML страницы"""
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=12)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")
  except Exception as e:
    st.error(f"Не удалось просканировать {url}: {e}")
    return None


def parse_catalog(site_url):
  soup = get_soup(site_url)
  if not soup:
    return

  found_pdfs = []
  found_images = []

  # Собираем ссылки для сканирования (главная + разделы каталога)
  pages_to_scan = {site_url}
  for a in soup.find_all("a", href=True):
    href = urljoin(site_url, a["href"])
    text = a.get_text().strip().lower()
    # Если ссылка ведет на раздел каталога/подарков на этом же сайте
    if (
        any(k in text or k in href for k in TARGET_KEYWORDS)
        and urlparse(href).netloc == urlparse(site_url).netloc
    ):
      pages_to_scan.add(href)

  # Ограничиваем глубину сканирования 5 страницами, чтобы работало быстро
  pages_to_scan = list(pages_to_scan)[:5]

  progress_bar = st.progress(0)
  for index, page_url in enumerate(pages_to_scan):
    page_soup = get_soup(page_url) if page_url != site_url else soup
    if not page_soup:
      continue

    # 1. ПОИСК PDF КАТАЛОГОВ
    for a in page_soup.find_all("a", href=True):
      href = urljoin(page_url, a["href"])
      link_text = a.get_text().strip()

      if href.lower().endswith(".pdf"):
        if is_pdf_valid(link_text, href):
          pdf_item = {
              "name": link_text if len(link_text) > 3 else "Новогодний каталог",
              "url": href,
          }
          if pdf_item not in found_pdfs:
            found_pdfs.append(pdf_item)

    # 2. ПОИСК КАРТИНОК (УПАКОВКА И ПОДАРКИ)
    for img in page_soup.find_all("img", src=True):
      src = urljoin(page_url, img["src"])
      alt = img.get("alt", "").strip()

      if is_img_valid(alt, src):
        img_item = {"name": alt if alt else src.split("/")[-1], "url": src}
        if img_item not in found_images:
          found_images.append(img_item)

    progress_bar.progress((index + 1) / len(pages_to_scan))

  # === ВЫВОД РЕЗУЛЬТАТОВ ===

  st.divider()

  # Вывод PDF
  if found_pdfs:
    st.subheader(f"📄 Найдены новогодние PDF-каталоги ({len(found_pdfs)}):")
    for pdf in found_pdfs:
      st.success(f"📥 **[{pdf['name']}]({pdf['url']})**")
  else:
    st.warning(
        "Новогодние PDF-каталоги не найдены (юридические документы и"
        " инструкции были автоматически скрыты)."
    )

  # Вывод Картинок и создание ZIP
  if found_images:
    st.subheader(
        f"🖼 Найдены изображения упаковки и подарков: {len(found_images)} шт."
    )

    # Показываем превью первых 6 картинок
    cols = st.columns(3)
    for i, img in enumerate(found_images[:6]):
      cols[i % 3].image(
          img["url"], caption=img["name"][:30], use_container_width=True
      )

    # Кнопка скачивания ZIP архива
    if st.button("📦 Сформировать ZIP-архив с подарками и упаковкой"):
      with st.spinner("Упаковываем картинки в архив..."):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer, "a", zipfile.ZIP_DEFLATED, False
        ) as zip_file:
          for i, img in enumerate(found_images):
            try:
              res = requests.get(img["url"], timeout=5)
              clean_name = re.sub(r"[^\w\-_.]", "_", img["name"])
              if not clean_name.lower().endswith(
                  (".jpg", ".png", ".jpeg", ".webp")
              ):
                clean_name += ".jpg"

              file_filename = f"{i+1}_{clean_name}"
              zip_file.writestr(file_filename, res.content)
            except:
              continue

        st.download_button(
            label="💾 Скачать ZIP-архив с картинками",
            data=zip_buffer.getvalue(),
            file_name="ny_packaging_catalog.zip",
            mime="application/zip",
        )


# --- ИНТЕРФЕЙС STREAMLIT ---
user_input = st.text_input(
    "Введите название компании или адрес сайта (например: Спартак, Коммунарка,"
    " roshen.kz, redoct.ru):"
)

if user_input:
  site_url = find_official_website(user_input.strip())
  if site_url:
    parse_catalog(site_url)
  else:
    st.error(
        "Не удалось найти сайт компании. Пожалуйста, введите точный адрес"
        " сайта."
    )
