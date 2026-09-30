import io
import re
from urllib.parse import urljoin, urlparse
import zipfile

from bs4 import BeautifulSoup
import requests
import streamlit as st

# ==========================================
# 📚 ВСТРОЕННЫЙ РЕЕСТР КРУПНЕЙШИХ ПРОИЗВОДИТЕЛЕЙ ЕАЭС
# ==========================================
EAEU_MANUFACTURERS_DB = {
    'спартак': 'https://spartak.by',
    'коммунарка': 'https://www.kommunarka.by',
    'рахат': 'https://rakhat.kz',
    'красный октябрь': 'https://www.uniconf.ru',
    'рот фронт': 'https://www.uniconf.ru',
    'бабаевский': 'https://www.uniconf.ru',
    'акконд': 'https://akkond.ru',
    'славянка': 'https://slavyanka.ru',
    'атаг': 'https://atag.ru',
    'невский кондитер': 'https://krascon.ru',
    'победа': 'https://pobeda.conf',
    'эссен': 'https://essenproduction.com',
}

# ==========================================
# 🛑 СТРОГИЕ ФИЛЬТРЫ И ИСКЛЮЧЕНИЯ
# ==========================================

# Черный список для PDF (Юридический и административный мусор)
PDF_EXCLUDE_KEYWORDS = [
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
    'соут',
    'гост',
    'декларац',
    'privacy',
    'policy',
    'consent',
    'terms',
    'license',
    'report',
]

# Черный список для Изображений (Интерфейс, логотипы, баннеры)
IMG_EXCLUDE_KEYWORDS = [
    'logo',
    'icon',
    'banner',
    'button',
    'btn',
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
    'thumb_small',
    'sprite',
    'placeholder',
]

# Белый список ключевых слов (Новый Год и Упаковка)
TARGET_KEYWORDS = [
    'новогод',
    'новый год',
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
    'дерев',
    'символ',
    'сладк',
    'набор',
    'gift',
    'box',
    'catalog',
    'ny',
    'newyear',
    'pack',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/122.0.0.0 Safari/537.36'
    )
}

# ==========================================
# ⚙️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================


def transliterate(text):
  """Перевод кириллицы в латиницу для подбора доменов"""
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
  clean = text.lower().strip()
  return ''.join(translit_dict.get(c, c) for c in clean if c.isalnum())


def find_target_domain(query):
  """Прямой подбор домена без использования поисковиков"""
  query_clean = query.lower().strip()

  # 1. Если введен прямой URL (например: spartak.by или https://site.ru)
  if '.' in query_clean and not ' ' in query_clean:
    if not query_clean.startswith(('http://', 'https://')):
      return f'https://{query_clean}'
    return query_clean

  # 2. Проверка по встроенной базе ЕАЭС
  for key, url in EAEU_MANUFACTURERS_DB.items():
    if key in query_clean:
      return url

  # 3. Прямая проверка доменных зон ЕАЭС (.by, .ru, .kz, .com)
  slug = transliterate(query_clean)
  if not slug:
    return None

  tlds = ['by', 'ru', 'kz', 'com', 'co.kg', 'am']
  for tld in tlds:
    test_url = f'https://{slug}.{tld}'
    try:
      resp = requests.head(
          test_url, headers=HEADERS, timeout=3, allow_redirects=True
      )
      if resp.status_code < 400:
        return resp.url
    except Exception:
      continue

  return None


def is_pdf_valid(title, url):
  """Жесткий фильтр для PDF"""
  combined = (title + ' ' + url).lower()

  # Отбраковываем юридический мусор
  if any(bad in combined for bad in PDF_EXCLUDE_KEYWORDS):
    return False

  # Проверяем наличие целевых слов или цифр текущего/следующего года
  if any(good in combined for good in TARGET_KEYWORDS) or re.search(
      r'20?2[4-6]', combined
  ):
    return True

  return False


def is_img_valid(alt, src):
  """Жесткий фильтр для изображений упаковки и подарков"""
  combined = (alt + ' ' + src).lower()

  # Исключаем системный мусор и векторную графику
  if any(bad in combined for bad in IMG_EXCLUDE_KEYWORDS) or combined.endswith(
      '.svg'
  ):
    return False

  # Проверяем на привязку к упаковке/подаркам
  if any(good in combined for good in TARGET_KEYWORDS):
    return True

  return False


def get_soup(url):
  """Скачивание страницы"""
  try:
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')
  except Exception:
    return None


# ==========================================
# 🕷 ОСНОВНОЙ КРАУЛЕР
# ==========================================


def process_website(start_url):
  domain = urlparse(start_url).netloc
  soup = get_soup(start_url)

  if not soup:
    st.error(
        f'Не удалось подключиться к сайту {start_url}. Проверьте правильность'
        ' адреса.'
    )
    return

  # Поиск разделов каталога и подарков
  pages_to_scan = {start_url}
  for a in soup.find_all('a', href=True):
    href = urljoin(start_url, a['href'])
    text = a.get_text().strip().lower()

    if urlparse(href).netloc == domain:
      if any(k in text or k in href.lower() for k in TARGET_KEYWORDS):
        pages_to_scan.add(href)

  scan_list = list(pages_to_scan)[:8]  # Обходим до 8 целевых страниц

  found_pdfs = []
  found_images = []

  progress_bar = st.progress(0)
  status_info = st.empty()

  for idx, page_url in enumerate(scan_list):
    status_info.text(
        f'Сканирование раздела {idx+1} из {len(scan_list)}: {page_url}'
    )
    page_soup = get_soup(page_url) if page_url != start_url else soup
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

    # 2. Поиск изображений упаковки/подарков
    for img in page_soup.find_all('img', src=True):
      src = urljoin(page_url, img['src'])
      alt = img.get('alt', '').strip()

      if is_img_valid(alt, src):
        item = {'name': alt if alt else src.split('/')[-1], 'url': src}
        if item not in found_images:
          found_images.append(item)

    progress_bar.progress((idx + 1) / len(scan_list))

  status_info.empty()
  progress_bar.empty()

  # ==========================================
  # 📊 РЕЗУЛЬТАТЫ ПОИСКА
  # ==========================================
  st.divider()

  # PDF Раздел
  st.subheader('📄 Найденные PDF-каталоги')
  if found_pdfs:
    for pdf in found_pdfs:
      st.success(f"📥 **[{pdf['name']}]({pdf['url']})**")
  else:
    st.info('Новогодние PDF-каталоги не найдены.')

  # Картинки и ZIP
  st.subheader(
      f'🖼 Изображения упаковки и подарков (Найдено: {len(found_images)})'
  )
  if found_images:
    cols = st.columns(4)
    for i, img in enumerate(found_images[:8]):
      cols[i % 4].image(
          img['url'], caption=img['name'][:30], use_container_width=True
      )

    st.write('---')
    if st.button('📦 Создать ZIP-архив со всеми изображениями'):
      with st.spinner('Сборка и сжатие файлов...'):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(
            zip_buffer, 'a', zipfile.ZIP_DEFLATED, False
        ) as zip_file:
          for i, img in enumerate(found_images):
            try:
              res = requests.get(img['url'], headers=HEADERS, timeout=6)
              if res.status_code == 200:
                ext = '.jpg'
                if '.png' in img['url'].lower():
                  ext = '.png'
                elif '.webp' in img['url'].lower():
                  ext = '.webp'

                clean_title = re.sub(r'[^\w\-_.]', '_', img['name'])
                filename = f'{i+1:02d}_{clean_title[:35]}{ext}'
                zip_file.writestr(filename, res.content)
            except Exception:
              continue

        st.download_button(
            label='💾 Скачать ZIP-архив',
            data=zip_buffer.getvalue(),
            file_name=f"catalog_{domain.replace('.', '_')}.zip",
            mime='application/zip',
        )
  else:
    st.warning('Изображения целевой новогодней упаковки/подарков не найдены.')


# ==========================================
# 🖥 ИНТЕРФЕЙС
# ==========================================
st.set_page_config(
    page_title='Новогодние каталоги и упаковка ЕАЭС',
    page_icon='🎁',
    layout='wide',
)

st.title('🎁 Поиск новогодних каталогов и упаковки ЕАЭС')
st.caption(
    'Введите название компании (Спартак, Коммунарка, Рахат) или точный адрес'
    ' сайта (spartak.by, akkond.ru).'
)

user_query = st.text_input('Заказчик / Компания / Сайт:', value='')

if user_query:
  target_url = find_target_domain(user_query)

  if target_url:
    st.success(f'🌐 Наден сайт компании: **{target_url}**')
    process_website(target_url)
  else:
    st.error(
        f'Не удалось автоматически определить домен для «{user_query}».'
        ' Пожалуйста, введите точный адрес сайта (например: spartak.by).'
    )
