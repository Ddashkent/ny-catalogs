import concurrent.futures
import csv
import datetime
import io
import re
import urllib.parse
import zipfile

from bs4 import BeautifulSoup
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
import streamlit as st
import urllib3
from urllib3.util.retry import Retry

# Отключение предупреждений SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CURRENT_YEAR = datetime.date.today().year
TARGET_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1, CURRENT_YEAR + 2}

MAX_PAGES = 40
PAGE_WORKERS = 5

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ С ПОДДЕРЖКОЙ IDN (.БЕЛ / .РФ)
# =========================================================

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,'
        ' like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    ),
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}


def build_session():
  s = requests.Session()
  s.headers.update(HEADERS)
  s.verify = False
  retry = Retry(
      total=2,
      backoff_factor=0.4,
      status_forcelist=[500, 502, 503, 504],
      raise_on_status=False,
  )
  adapter = HTTPAdapter(
      max_retries=retry, pool_connections=15, pool_maxsize=15
  )
  s.mount('https://', adapter)
  s.mount('http://', adapter)
  return s


SESSION = build_session()


def encode_idn_url(url: str) -> str:
  """Преобразует домены с кириллицей (.бел, .рф) в Punycode"""
  try:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.encode('idna').decode('ascii')
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe='/:@-._~')
    query = urllib.parse.quote(
        urllib.parse.unquote(parsed.query), safe='=&$?+/:,@-._~'
    )
    return urllib.parse.urlunparse(
        (parsed.scheme, host, path, parsed.params, query, '')
    )
  except Exception:
    return url


def safe_fetch(url: str, timeout=(8, 18)):
  try:
    encoded_url = encode_idn_url(url)
    resp = SESSION.get(encoded_url, timeout=timeout, allow_redirects=True)
    if resp.status_code == 200 and len(resp.content) > 300:
      resp.encoding = resp.apparent_encoding or 'utf-8'
      return resp.url, resp.text, None
    return None, None, f'HTTP {resp.status_code}'
  except Exception as e:
    return None, None, str(e)


# =========================================================
# 🔎 НАСТОЯЩИЙ ПОИСКОВИК + ЖЕСТКИЙ ТЕМАТИЧЕСКИЙ ФИЛЬТР
# =========================================================

SEARCH_BLACK_LIST = [
    'wildberries.',
    'ozon.',
    'market.yandex.',
    'yandex.',
    'avito.',
    'aliexpress.',
    'vk.com',
    'ok.ru',
    'facebook.',
    'instagram.',
    'youtube.',
    'telegram.',
    't.me',
    'wikipedia.',
    '2gis.',
    'zoon.',
    'rusprofile.',
    'list-org.',
    'sbis.ru',
    'pulscen.',
    'flagma.',
    'hh.ru',
    'rabota.',
    'dzen.ru',
    'tiu.ru',
    'prom.ua',
]

# ОБЯЗАТЕЛЬНЫЕ ТЕМАТИЧЕСКИЕ СЛОВА (Новый год / конфеты / подарки / упаковка)
SWEETS_AND_GIFTS_KEYWORDS = [
    'подар',
    'конфет',
    'сладк',
    'упаков',
    'коробк',
    'туб',
    'набор',
    'новогод',
    'новый год',
    'шоколад',
    'кондитер',
    'картон',
    'мгк',
]

# ИСКЛЮЧАЕМЫЕ ОТРАСЛИ (Строительство, металл, авто, недвижимость и т.д.)
UNRELATED_INDUSTRIES = [
    'металлопрокат',
    'арматура',
    'швеллер',
    'бетон',
    'кирпич',
    'недвижимость',
    'автосервис',
    'шины',
    'ювелирный',
    'окна пвх',
    'кровля',
    'сантехника',
    'грузоперевозки',
]


def parse_search_links(html):
  urls = []
  soup = BeautifulSoup(html, 'lxml')
  for a in soup.find_all('a', href=True):
    href = a['href']
    if 'uddg=' in href:
      qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
      if 'uddg' in qs:
        href = qs['uddg'][0]
    if href.startswith('http') and not any(
        bad in href.lower() for bad in SEARCH_BLACK_LIST
    ):
      p = urllib.parse.urlparse(href)
      urls.append(f'{p.scheme}://{p.netloc}')
  return list(dict.fromkeys(urls))


def search_web_candidates(company_name):
  """Выполняет поиск в поисковых системах"""
  queries = [
      f'"{company_name}" официальный сайт новогодние подарки конфеты',
      f'{company_name} фабрика новогодние подарки упаковка каталог',
      f'"{company_name}" официальный сайт',
  ]

  candidates = []
  for query in queries:
    # 1. Поисковый запрос через Yandex HTML
    try:
      yandex_url = 'https://yandex.ru/search/?text=' + urllib.parse.quote(
          query
      )
      _, html, _ = safe_fetch(yandex_url, timeout=(6, 12))
      if html:
        candidates.extend(parse_search_links(html))
    except Exception:
      pass

    # 2. Резервный поиск через Mojeek / DuckDuckGo
    try:
      mojeek_url = 'https://www.mojeek.com/search?q=' + urllib.parse.quote(
          query
      )
      _, html, _ = safe_fetch(mojeek_url, timeout=(6, 12))
      if html:
        candidates.extend(parse_search_links(html))
    except Exception:
      pass

  return list(dict.fromkeys(candidates))


def verify_site_relevance(company_query, candidate_url):
  """Проверяет тему сайта: должен быть связан с ПОДАРКАМИ/КОНФЕТАМИ/УПАКОВКОЙ"""
  final_url, html, _ = safe_fetch(candidate_url, timeout=(6, 14))
  if not html:
    return None

  soup = BeautifulSoup(html, 'lxml')
  title = soup.title.get_text(' ', strip=True) if soup.title else ''
  text_sample = (
      title + ' ' + soup.get_text(' ', strip=True)[:80000]
  ).lower().replace('ё', 'е')
  host = urllib.parse.urlparse(final_url).netloc.lower()

  # 1. СТРОГАЯ ПРОВЕРКА ОТРАСЛИ: если сайт про металл, стройку или авто — ОТСЕКАЕМ
  if any(unrelated in text_sample for unrelated in UNRELATED_INDUSTRIES):
    return None

  # 2. ПРОВЕРКА ТЕМАТИКИ: На сайте ДОЛЖНА быть привязка к подаркам, конфетам или упаковке
  theme_score = sum(
      15 for kw in SWEETS_AND_GIFTS_KEYWORDS if kw in text_sample
  )
  if theme_score == 0:
    return None  # Отсекаем полностью, если нет связи с подарками/конфетами

  # 3. Начисление баллов за совпадение имени компании
  company_clean = company_query.lower().strip()
  words = [w for w in re.split(r'\W+', company_clean) if len(w) >= 3]

  name_score = 0
  for word in words:
    if word in text_sample:
      name_score += 20
    if word in title.lower():
      name_score += 30

  total_score = theme_score + name_score

  return {
      'url': final_url,
      'host': host,
      'title': title[:90] or host,
      'score': total_score,
  }


def find_official_website(company_input):
  q = company_input.strip()

  # Если сразу введен адрес или URL
  if q.startswith('http') or ('.' in q and ' ' not in q):
    direct_url = q if q.startswith('http') else 'https://' + q
    verified = verify_site_relevance(company_input, direct_url)
    if verified:
      return verified
    p = urllib.parse.urlparse(direct_url)
    return {
        'url': direct_url,
        'host': p.netloc,
        'title': p.netloc,
        'score': 100,
    }

  # Живой поиск в интернете
  candidates = search_web_candidates(company_input)
  if not candidates:
    return None

  verified_sites = []
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(verify_site_relevance, company_input, url)
        for url in candidates[:12]
    ]
    for f in concurrent.futures.as_completed(futures):
      try:
        res = f.result()
        if res:
          verified_sites.append(res)
      except Exception:
        continue

  if not verified_sites:
    return None

  # Выбираем ресурс с максимальным баллом релевантности
  verified_sites.sort(key=lambda x: x['score'], reverse=True)
  return verified_sites[0]


# =========================================================
# 📦 ИЗВЛЕЧЕНИЕ КАТАЛОГОВ И НАБОРОВ (КАРТОН / МГК / ТУБЫ)
# =========================================================

TARGET_BOX_KEYWORDS = [
    'набор',
    'подарок',
    'подарки',
    'упаковк',
    'коробк',
    'туб',
    'тубус',
    'сундуч',
    'домик',
    'книг',
    'футляр',
    'шкатулк',
    'чемоданчик',
    'картон',
    'микрогофр',
    'гофро',
    'мгк',
    'переплет',
    'переплёт',
    'кашир',
    'комплект',
    'сладкий подарок',
]

EXCLUDE_SINGLE_CANDIES = [
    'конфета',
    'конфеты весовые',
    'батончик',
    'плитка шоколада',
    'шоколадка',
    'драже',
    'карамелька',
    'вафля',
    'вафли',
    'печенье',
    'зефир',
    'ирис',
    'мармелад весовой',
    'поштучно',
]

EXCLUDE_MATERIALS = [
    'жесть',
    'жестяная',
    'металл',
    'tin',
    'текстиль',
    'ткань',
    'мешок',
    'мешочек',
    'рюкзак',
    'подушка',
    'плюш',
    'мягкая игрушка',
    'дерево',
    'фанера',
    'пластик',
    'пвх',
]

JUNK_DOCUMENTS = [
    'презентация',
    'соглашение',
    'политика',
    'конфиденциальн',
    'персональн',
    'договор',
    'оферта',
    'вакансии',
    'реквизиты',
    'cookies',
    'устав',
    'инвесторам',
    'соут',
    'privacy',
]
DOCUMENT_KEYWORDS = [
    'каталог',
    'catalog',
    'прайс',
    'price',
    'новогод',
    'подарки',
    'gift',
]

WEIGHT_REGEX = re.compile(
    r'(\d+(?:[.,]\d+)?\s*(?:г|гр|грамм|кг|g|kg)\b)', re.I
)


def fix_url(base, href):
  href = (href or '').strip()
  if not href or href.startswith(('data:', 'javascript:', 'mailto:', 'tel:')):
    return ''
  if href.startswith('//'):
    href = 'https:' + href
  full = urllib.parse.urljoin(base, href)
  p = urllib.parse.urlparse(full)
  path = urllib.parse.quote(urllib.parse.unquote(p.path), safe='/:@-._~')
  query = urllib.parse.quote(urllib.parse.unquote(p.query), safe='=&$?+/:,@-._~')
  return urllib.parse.urlunparse((p.scheme, p.netloc, path, p.params, query, ''))


def is_target_packaging(title, context_text, url):
  combined = f'{title} {context_text} {url}'.lower().replace('ё', 'е')

  if any(bad in combined for bad in EXCLUDE_MATERIALS):
    return False

  has_single = any(single in combined for single in EXCLUDE_SINGLE_CANDIES)
  has_box = any(box in combined for box in TARGET_BOX_KEYWORDS)

  if has_single and not has_box:
    return False

  return has_box or 'podar' in url.lower() or 'novogod' in url.lower()


def scan_page_content(url):
  _, html, _ = safe_fetch(url, timeout=(8, 15))
  if not html:
    return [], []

  soup = BeautifulSoup(html, 'lxml')
  for junk in soup.select('script, style, noscript, footer, header, nav'):
    junk.decompose()

  page_ctx = (soup.title.get_text(' ', strip=True) if soup.title else '') + ' ' + url
  pdfs, imgs = [], []

  # PDF
  for a in soup.find_all('a', href=True):
    href = fix_url(url, a['href'])
    if href.lower().split('?')[0].endswith(('.pdf', '.xlsx', '.xls')):
      text = ' '.join(a.get_text().split())
      comb = f'{text} {urllib.parse.unquote(href)}'.lower()
      if any(bad in comb for bad in JUNK_DOCUMENTS):
        continue
      if any(good in comb for good in DOCUMENT_KEYWORDS):
        pdfs.append({'name': text or 'Официальный каталог PDF', 'url': href})

  # Изображения наборов
  for img in soup.find_all('img'):
    src = (
        img.get('src')
        or img.get('data-src')
        or img.get('data-original')
        or img.get('data-lazy-src')
    )
    if not src:
      continue
    full = fix_url(url, src)
    if not full or any(
        j in full.lower()
        for j in ['logo', 'icon', 'banner', 'slider', 'social', 'avatar']
    ):
      continue
    if not re.search(r'\.(jpg|jpeg|png|webp)', full.lower()):
      continue

    alt = (img.get('alt') or img.get('title') or '').strip()
    parent_text = (
        img.parent.get_text(' ', strip=True) if img.parent else ''
    )[:300]
    title = alt or parent_text[:60] or 'Подарочный набор'

    if is_target_packaging(title, parent_text + ' ' + page_ctx, full):
      m = WEIGHT_REGEX.search(parent_text + ' ' + title)
      imgs.append({
          'title': title[:100],
          'weight': m.group(1) if m else None,
          'url': full,
      })

  return pdfs, imgs


def deep_scan_catalog(site_url):
  _, html, err = safe_fetch(site_url, timeout=(10, 20))
  if not html:
    return None, None, 0, [err]

  domain = urllib.parse.urlparse(site_url).netloc.replace('www.', '')
  soup = BeautifulSoup(html, 'lxml')

  pages = {site_url}
  for path in (
      '/catalog/',
      '/products/',
      '/podarki/',
      '/novogodnie-podarki/',
      '/upakovka/',
  ):
    pages.add(urllib.parse.urljoin(site_url, path))

  for a in soup.find_all('a', href=True):
    href = fix_url(site_url, a['href'])
    if href and urllib.parse.urlparse(href).netloc.replace('www.', '') == domain:
      blob = (a.get_text() + ' ' + href).lower()
      if any(
          k in blob
          for k in [
              'catalog',
              'katalog',
              'novogod',
              'podarki',
              'karton',
              'tuba',
              'upakov',
              'product',
              'gift',
              '2025',
              '2026',
              '2027',
          ]
      ):
        pages.add(href)

  queue = list(pages)[:MAX_PAGES]
  all_pdfs, all_imgs = [], []

  with concurrent.futures.ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
    for p, i in ex.map(scan_page_content, queue):
      all_pdfs.extend(p)
      all_imgs.extend(i)

  pdfs = list({d['url']: d for d in all_pdfs}.values())
  imgs = list({d['url']: d for d in all_imgs}.values())
  return pdfs, imgs, len(queue), None


# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(
    page_title='Первый Снег | Поисковик ЕАЭС', page_icon='❄️', layout='wide'
)

st.title('❄️ Поисковик и Экстрактор Новогодних Каталогов')
st.caption(
    'Живой веб-поиск официальных сайтов компаний (Яндекс/Search Engine).'
    ' Отсеиваются непрофильные отраслевые сайты и собираются наборы (картон,'
    ' МГК, тубы).'
)

company_input = st.text_input(
    'Введите название компании (заказчика / конкурента):',
    placeholder='Абинекс, СолБигТрейд, Коммунарка, Спартак, Рубин, Рахат...',
)

if st.button(
    '🚀 НАЙТИ В ИНТЕРНЕТЕ И СОБРАТЬ КАТАЛОГИ',
    type='primary',
    use_container_width=True,
):
  if not company_input.strip():
    st.warning('Пожалуйста, введите название компании.')
    st.stop()

  with st.spinner(f'Поиск официального сайта «{company_input}» в Яндекс/Web...'):
    site_info = find_official_website(company_input.strip())

  if not site_info:
    st.error(
        f'❌ Не удалось найти сайт для «{company_input}», связанный с'
        ' новогодними подарками, конфетами или упаковкой.'
    )
    st.stop()

  st.success(
      f"🌐 Найден официальный сайт: **[{site_info['url']}]({site_info['url']})**  \n"
      f"Заголовок: *{site_info['title']}*"
  )

  with st.spinner('Глубокий обход каталогов и карточек товаров...'):
    pdfs, imgs, pages_count, errors = deep_scan_catalog(site_info['url'])

  if pdfs is None:
    st.error(f'Сайт {site_info['url']} найден, но не отвечает на запросы.')
    st.stop()

  st.info(f'Просканировано страниц: **{pages_count}**')
  col1, col2 = st.columns(2)

  with col1:
    st.subheader(f'📄 PDF / Excel Каталоги ({len(pdfs)})')
    if pdfs:
      for d in pdfs:
        st.markdown(
            f'• **[{d["name"]}]({d["url"]})**', unsafe_allow_html=True
        )
    else:
      st.info('Официальные PDF-каталоги на ресурсе не найдены.')

  with col2:
    st.subheader(f'📦 Наборы и Коробки ({len(imgs)})')
    if imgs:
      buf = io.BytesIO()
      with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(imgs[:400], 1):
          try:
            r = SESSION.get(item['url'], timeout=8)
            if r.status_code != 200 or len(r.content) < 3000:
              continue
            name = re.sub(r'[^\w\-]+', '_', item['title'])[:35] or 'box_item'
            ext = (
                'png'
                if '.png' in item['url'].lower()
                else 'webp' if '.webp' in item['url'].lower() else 'jpg'
            )
            zf.writestr(f'{i:03d}_{name}.{ext}', r.content)
          except Exception:
            continue

      st.download_button(
          f'📥 СКАЧАТЬ ZIP С НАБОРАМИ ({len(imgs)} шт.)',
          data=buf.getvalue(),
          file_name=f"{site_info['host']}_packaging.zip",
          mime='application/zip',
          type='primary',
      )

      grid = st.columns(3)
      for i, item in enumerate(imgs[:9]):
        with grid[i % 3]:
          st.image(item['url'], use_container_width=True)
          st.caption(
              f"**{item['title']}**"
              + (f" | ⚖️ {item['weight']}" if item['weight'] else '')
          )
    else:
      st.info('Подарочные наборы и коробки не найдены.')

st.divider()
st.caption('Инструмент «Первый Снег» | Живой веб-поисковик ЕАЭС.')
