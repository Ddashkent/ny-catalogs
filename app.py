import io
import re
from urllib.parse import parse_qs, urljoin, urlparse
import zipfile

from bs4 import BeautifulSoup
import requests
import streamlit as st

# ==========================================
# 🛑 НАСТРОЙКИ ФИЛЬТРАЦИИ И ИСКЛЮЧЕНИЙ
# ==========================================

# Черный список для PDF (юридические и технические документы)
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
    'отчет',
    'бухгалтер',
    'финанс',
    'сводн',
    'ведомост',
    'sout',
    'privacy',
    'policy',
    'consent',
    'terms',
    'license',
    'report',
    'audit',
]

# Черный список для картинок (элементы интерфейса, баннеры, логотипы)
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
    'arrow',
    'bg',
    'background',
    'slider',
    'widget',
    'rating',
    'share',
]

# Белый список ключевых слов (Новый Год и Упаковка)
TARGET_KEYWORDS = [
    'новогод',
    'новый',
    'подар',
    'упаков',
    'каталог',
    '2024',
    '2025',
    '2026',
    'короб',
    'жесть',
    'картон',
    'туб',
    'текстиль',
    'символ',
    'сладк',
    'набор',
    'gift',
    'box',
    'catalog',
    'ny',
    'newyear',
    'present',
    'pack',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}

# ==========================================
# 🔎 ПОИСКОВЫЙ ДВИЖОК
# ==========================================


def transliterate(text):
  """Конвертирует кириллицу в латиницу для проверки доменов"""
  translit_dict = {
      'а': 'a',
      'б': 'b',
      'в': 'v',
      'г': 'g',
      'д': 'd',
      'е': 'e',
      'ё': 'yo',
      'ж': 'zh',
      'з': 'z',
      'и': 'i',
      'й': 'y',
      'к': 'k',
      'л': 'l',
      'м': 'm',
      'н': 'n',
      'о': 'o',
      'п': 'p',
      'р': 'r',
      'с': 's',
      'т': 't',
      'у': 'u',
      'ф': 'f',
      'х': 'h',
      'ц': 'ts',
      'ч': 'ch',
      'ш': 'sh',
      'щ': 'sch',
      'ъ': '',
      'ы': 'y',
      'ь': '',
      'э': 'e',
      'ю': 'yu',
      'я': 'ya',
  }
  return ''.join(translit_dict.get(c, c) for c in text.lower() if c.isalnum())


def resolve_company_site(query):
  """Находит официальный сайт компании с несколькими уровнями резервирования"""
  query = query.strip()

  # Если введен прямой URL
  if '.' in query and not ' ' in query:
    if not query.startswith(('http://', 'https://')):
      return f'https://{query}'
    return query

  search_term = f'{query} официальный сайт'

  # Метод 1: DuckDuckGo HTML
  try:
    resp = requests.post(
        'https://html.duckduckgo.com/html/',
        data={'q': search_term},
        headers=HEADERS,
        timeout=6,
    )
    if resp.status_code == 200:
      soup = BeautifulSoup(resp.text, 'html.parser')
      for a in soup.find_all('a', class_='result__url'):
        href = a.get('href', '')
        if 'uddg=' in href:
          parsed = parse_qs(urlparse(href).query)
          if 'uddg' in parsed:
            url = parsed['uddg'][0]
            if not any(
                bad in url
                for bad in [
                    'wikipedia',
                    'vk.com',
                    'avito',
                    'yandex',
                    'facebook',
                    'instagram',
                ]
            ):
              return url
  except Exception:
    pass

  # Метод 2: Yandex HTML
  try:
    resp = requests.get(
        f'https://yandex.ru/search/?text={requests.utils.quote(search_term)}',
        headers=HEADERS,
        timeout=6,
    )
    if resp.status_code == 200:
      soup = BeautifulSoup(resp.text, 'html.parser')
      for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and not any(
            bad in href
            for bad in [
                'yandex',
                'passport',
                'captcha',
                'vk.com',
                'wikipedia',
                'avito',
                'youtube',
            ]
        ):
          return href
  except Exception:
    pass

  # Метод 3: Эвристический подбор доменов ЕАЭС (.by, .ru, .kz, .com)
  clean_name = transliterate(query)
  if clean_name:
    for tld in ['by', 'ru', 'kz', 'com']:
      test_url = f'https://{clean_name}.{tld}'
      try:
        r = requests.head(
            test_url, headers=HEADERS, timeout=3, allow_redirects=True
        )
        if r.status_code < 400:
          return r.url
      except Exception:
        continue

  return None


# ==========================================
# 🕷 КРАУЛЕР И ФИЛЬТРЫ
# ==========================================


def is_pdf_valid(text, url):
  """Проверяет PDF на соответствие новогодней тематике и отсутствие юр. мусора"""
  combined = (text + ' ' + url).lower()

  if any(bad in combined for bad in PDF_BLACKLIST):
    return False

  # Файл должен иметь привязку к каталогу, подаркам или Новому Году
  if any(good in combined for good in TARGET_KEYWORDS):
    return True

  # Если в названии файла есть цифры года (24, 25, 2024, 2025)
  if re.search(r'20?2[4-6]', combined):
    return True

  return False


def is_img_valid(alt, src):
  """Отбирает только изображения упаковки и подарков"""
  combined = (alt + ' ' + src).lower()

  if any(bad in combined for bad in IMG_BLACKLIST):
    return False

  if combined.endswith('.svg'):
    return False

  if any(good in combined for good in TARGET_KEYWORDS):
    return True

  return False


def fetch_page(url):
  """Безопасно скачивает содержимое страницы"""
  try:
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')
  except Exception:
    return None


def run_catalog_parser(base_url):
  """Основной алгоритм сбора данных"""
  soup = fetch_page(base_url)
  if not soup:
    st.error(f'Не удалось загрузить сайт: {base_url}')
    return

  domain = urlparse(base_url).netloc
  pages_to_scan = {base_url}

  # Находим внутренние страницы каталогов и подарков
  for a in soup.find_all('a', href=True):
    href = urljoin(base_url, a['href'])
    text = a.get_text().strip().lower()

    if urlparse(href).netloc == domain:
      if any(k in text or k in href.lower() for k in TARGET_KEYWORDS):
        pages_to_scan.add(href)

  pages_list = list(pages_to_scan)[:8]  # Сканируем до 8 ключевых страниц сайта

  found_pdfs = []
  found_images = []

  progress_bar = st.progress(0)
  status_text = st.empty()

  for idx, page_url in enumerate(pages_list):
    status_text.text(
        f'Сканирование страницы {idx+1} из {len(pages_list)}: {page_url}'
    )
    page_soup = fetch_page(page_url) if page_url != base_url else soup
    if not page_soup:
      continue

    # 1. Поиск PDF
    for a in page_soup.find_all('a', href=True):
      href = urljoin(page_url, a['href'])
      link_text = a.get_text().strip()

      if href.lower().rsplit('?', 1)[0].endswith('.pdf'):
        if is_pdf_valid(link_text, href):
          item = {
              'name': (
                  link_text if len(link_text) > 3 else href.split('/')[-1]
              ),
              'url': href,
          }
          if item not in found_pdfs:
            found_pdfs.append(item)

    # 2. Поиск Изображений
    for img in page_soup.find_all('img', src=True):
      src = urljoin(page_url, img['src'])
      alt = img.get('alt', '').strip()

      if is_img_valid(alt, src):
        item = {'name': alt if alt else src.split('/')[-1], 'url': src}
        if item not in found_images:
          found_images.append(item)

    progress_bar.progress((idx + 1) / len(pages_list))

  status_text.empty()

  # ==========================================
  # 📊 ВЫВОД РЕЗУЛЬТАТОВ
  # ==========================================
  st.divider()

  # Вывод PDF
  st.subheader('📄 Найденные PDF-каталоги')
  if found_pdfs:
    for pdf in found_pdfs:
      st.success(f"📥 **[{pdf['name']}]({pdf['url']})**")
  else:
    st.info(
        'Новогодние PDF-каталоги не обнаружены (технические и юридические PDF'
        ' скрыты фильтром).'
    )

  # Вывод Изображений
  st.subheader(
      f'🖼 Изображения упаковки и подарков (Найдено: {len(found_images)})'
  )
  if found_images:
    # Отображение сетки превью
    cols = st.columns(4)
    for idx, img in enumerate(found_images[:8]):
      cols[idx % 4].image(
          img['url'], caption=img['name'][:25], use_container_width=True
      )

    # Генерация ZIP
    st.write('---')
    if st.button('📦 Сформировать ZIP-архив со всеми изображениями'):
      with st.spinner('Скачивание и упаковка файлов в ZIP...'):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer, 'a', zipfile.ZIP_DEFLATED, False
        ) as zip_file:
          for i, img in enumerate(found_images):
            try:
              res = requests.get(img['url'], headers=HEADERS, timeout=6)
              if res.status_code == 200:
                clean_name = re.sub(r'[^\w\-_.]', '_', img['name'])
                ext = '.jpg'
                if '.png' in img['url'].lower():
                  ext = '.png'
                elif '.webp' in img['url'].lower():
                  ext = '.webp'

                filename = f'{i+1:02d}_{clean_name[:40]}{ext}'
                zip_file.writestr(filename, res.content)
            except Exception:
              continue

        st.download_button(
            label='💾 Скачать ZIP-архив',
            data=zip_buffer.getvalue(),
            file_name=f"catalog_packaging_{domain.replace('.', '_')}.zip",
            mime='application/zip',
        )
  else:
    st.warning('Изображения целевых подарков и упаковки не найдены.')


# ==========================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# ==========================================
st.set_page_config(
    page_title='Поиск новогодних каталогов и упаковки',
    page_icon='🎁',
    layout='wide',
)

st.title('🎁 Поиск новогодних каталогов и упаковки ЕАЭС')
st.caption(
    'Введите название компании (например: Спартак, Коммунарка, Рахат) или прямой'
    ' адрес сайта.'
)

query_input = st.text_input('Заказчик / Компания / Сайт:', value='')

if query_input:
  resolved_url = resolve_company_site(query_input)

  if resolved_url:
    st.success(f'🔗 Целевой адрес сайта: **{resolved_url}**')
    run_catalog_parser(resolved_url)
  else:
    st.error(
        f'Не удалось автоматически определить сайт для «{query_input}».'
        ' Пожалуйста, введите точный адрес (например: spartak.by).'
    )
