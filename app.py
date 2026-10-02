import concurrent.futures
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

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 🏆 БАЗА ЗНАНИЙ ЕАЭС (СЛОЖНЫЕ ДОМЕНЫ БРЕНДОВ)
# =========================================================
EXPERT_DIRECTORY = {
    'солбигтрейд': 'https://конфета.бел',
    'солбиг трейд': 'https://конфета.бел',
    'солбиг': 'https://конфета.бел',
    'абинекс': 'https://podarok-k.ru',
    'рубин': 'https://rubin-2000.ru',
    'рубин тг': 'https://rubin-tg.ru',
    'академия шоколада': 'https://chocohunter.ru',
    'коммунарка': 'https://www.kommunarka.by',
    'спартак': 'https://spartak.by',
    'рахат': 'https://rakhat.kz',
    'баян сулу': 'https://www.bayansulu.kz',
    'акконд': 'https://akkond.ru',
    'лаконд': 'https://lakond.ru',
    'дилявер': 'https://dilyaver.ru',
    'главупак': 'https://glavupak.ru',
    'дедморозов': 'https://dedmorozov.ru',
    'славянка': 'https://slavyanka.ru',
    'миракс': 'https://mirax-gifts.ru',
    'москондитер': 'https://mosconditer.ru',
    'росшоколад': 'https://roschocolate.ru',
    'микс ко': 'https://podarki-opt.ru',
    'рэйд 21': 'https://podarki-reid21.ru',
}

# Исключаемые площадки (маркетплейсы, соцсети, справочники)
MARKETPLACES_AND_SOCIAL = [
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
]

# Фильтры тематики
GIFTS_KEYWORDS = [
    'подар',
    'конфет',
    'сладк',
    'упаков',
    'коробк',
    'туб',
    'набор',
    'новогод',
    'шоколад',
    'картон',
    'мгк',
]
FORBIDDEN_INDUSTRIES = [
    'металлопрокат',
    'арматура',
    'бетон',
    'кирпич',
    'автосервис',
    'шины',
    'ювелирный',
    'окна пвх',
    'сантехника',
]

FORBIDDEN_SINGLE_ITEMS = [
    'конфета весовая',
    'батончик',
    'плитка шоколада',
    'шоколадка',
    'драже',
    'карамелька',
    'вафля',
    'печенье',
    'зефир',
]
FORBIDDEN_MATERIALS = [
    'жесть',
    'металл',
    'текстиль',
    'ткань',
    'мешок',
    'рюкзак',
    'мягкая игрушка',
    'дерево',
    'пластик',
]

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

# =========================================================
# ⚙️ СЕТЕВОЙ МОДУЛЬ С ПОДДЕРЖКОЙ IDN (.БЕЛ / .РФ)
# =========================================================


def create_session():
  s = requests.Session()
  s.headers.update(HEADERS)
  s.verify = False
  retry = Retry(
      total=2,
      backoff_factor=0.3,
      status_forcelist=[500, 502, 503, 504],
      raise_on_status=False,
  )
  adapter = HTTPAdapter(
      max_retries=retry, pool_connections=12, pool_maxsize=12
  )
  s.mount('https://', adapter)
  s.mount('http://', adapter)
  return s


SESSION = create_session()


def fix_idn_url(url: str) -> str:
  """Конвертирует кириллические домены (конфета.бел) в Punycode"""
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


def safe_fetch(url, timeout=(8, 15)):
  try:
    target_url = fix_idn_url(url)
    r = SESSION.get(target_url, timeout=timeout, allow_redirects=True)
    if r.status_code == 200 and len(r.content) > 300:
      r.encoding = r.apparent_encoding or 'utf-8'
      return r.text, r.url
  except Exception:
    pass
  return None, url


# =========================================================
# 🔎 ПОИСКОВЫЙ ДВИЖОК (НАСТОЯЩИЙ ПОИСК В СЕТИ)
# =========================================================


def parse_engine_links(html):
  urls = []
  soup = BeautifulSoup(html, 'lxml')
  for a in soup.find_all('a', href=True):
    href = a['href']
    if 'uddg=' in href:
      qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
      if 'uddg' in qs:
        href = qs['uddg'][0]
    if href.startswith('http') and not any(
        m in href.lower() for m in MARKETPLACES_AND_SOCIAL
    ):
      p = urllib.parse.urlparse(href)
      urls.append(f'{p.scheme}://{p.netloc}')
  return list(dict.fromkeys(urls))


def search_web_for_company(company_name):
  """Запрашивает реальные поисковые системы без додумывания .ru"""
  candidates = []
  queries = [
      f'"{company_name}" официальный сайт новогодние подарки',
      f'компания {company_name} новогодние подарки каталог',
  ]

  for q in queries:
    # 1. Поиск через DuckDuckGo Lite
    try:
      url = 'https://lite.duckduckgo.com/lite/?q=' + urllib.parse.quote(q)
      _, html = safe_fetch(url, timeout=(5, 10))
      if html:
        candidates.extend(parse_engine_links(html))
    except Exception:
      pass

    # 2. Поиск через Mojeek
    try:
      url = 'https://www.mojeek.com/search?q=' + urllib.parse.quote(q)
      _, html = safe_fetch(url, timeout=(5, 10))
      if html:
        candidates.extend(parse_engine_links(html))
    except Exception:
      pass

  return list(dict.fromkeys(candidates))


def evaluate_site_relevance(company_query, site_url):
  """Проверяет: действительно ли сайт принадлежит искомой компании и связан с подарками"""
  html, final_url = safe_fetch(site_url)
  if not html:
    return None

  soup = BeautifulSoup(html, 'lxml')
  title = soup.title.get_text(' ', strip=True) if soup.title else ''
  text_body = (
      title + ' ' + soup.get_text(' ', strip=True)[:60000]
  ).lower().replace('ё', 'е')
  host = urllib.parse.urlparse(final_url).netloc.lower()

  # 1. Отсекаем посторонние сферы
  if any(bad in text_body for bad in FORBIDDEN_INDUSTRIES):
    return None

  # 2. Сайт обязан иметь отношение к подаркам / конфетам / упаковке
  theme_score = sum(10 for kw in GIFTS_KEYWORDS if kw in text_body)
  if theme_score == 0:
    return None

  # 3. Совпадение бренда в названии, тексте или футере
  company_clean = company_query.lower().strip()
  words = [w for w in re.split(r'\W+', company_clean) if len(w) >= 3]

  brand_score = 0
  for word in words:
    if word in text_body:
      brand_score += 20
    if word in title.lower():
      brand_score += 30

  total_score = theme_score + brand_score

  return {
      'url': final_url,
      'host': host,
      'title': title[:90] or host,
      'score': total_score,
  }


def find_official_website(company_input):
  q = company_input.lower().strip()

  # 1. Проверяем базу известных сложных брендов ЕАЭС
  for key, url in EXPERT_DIRECTORY.items():
    if key == q or key in q:
      return {'url': url, 'host': urllib.parse.urlparse(url).netloc, 'title': url}

  # 2. Если введен прямой адрес (например: конфета.бел или site.ru)
  if q.startswith('http') or ('.' in q and ' ' not in q):
    direct_url = q if q.startswith('http') else 'https://' + q
    evaluated = evaluate_site_relevance(company_input, direct_url)
    if evaluated:
      return evaluated
    p = urllib.parse.urlparse(direct_url)
    return {'url': direct_url, 'host': p.netloc, 'title': p.netloc}

  # 3. Настоящий веб-поиск (без глупой подстановки .RU)
  candidates = search_web_for_company(company_input)
  if not candidates:
    return None

  evaluated_sites = []
  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(evaluate_site_relevance, company_input, url)
        for url in candidates[:10]
    ]
    for f in concurrent.futures.as_completed(futures):
      try:
        res = f.result()
        if res:
          evaluated_sites.append(res)
      except Exception:
        continue

  if not evaluated_sites:
    return None

  evaluated_sites.sort(key=lambda x: x['score'], reverse=True)
  return evaluated_sites[0]


# =========================================================
# 📦 ИЗВЛЕЧЕНИЕ КАТАЛОГОВ И УПАКОВКИ (КАРТОН / МГК / ТУБЫ)
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
    'кашир',
    'сладкий подарок',
]

JUNK_DOCS = [
    'презентация',
    'соглашение',
    'политика',
    'конфиденциальн',
    'персональн',
    'договор',
    'оферта',
    'вакансии',
    'устав',
]
DOC_KEYWORDS = [
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


def is_target_item(title, url):
  blob = (title + ' ' + url).lower().replace('ё', 'е')
  if any(bad in blob for bad in FORBIDDEN_MATERIALS):
    return False
  has_single = any(single in blob for single in FORBIDDEN_SINGLE_ITEMS)
  has_box = any(box in blob for box in TARGET_BOX_KEYWORDS)
  if has_single and not has_box:
    return False
  return has_box or 'podar' in url.lower() or 'novogod' in url.lower()


def scan_single_page(url):
  html, final_url = safe_fetch(url)
  if not html:
    return [], []

  soup = BeautifulSoup(html, 'lxml')
  for junk in soup.select('script, style, noscript, footer, header, nav'):
    junk.decompose()

  page_ctx = (soup.title.get_text(' ', strip=True) if soup.title else '') + ' ' + url
  pdfs, imgs = [], []

  # PDF Каталоги
  for a in soup.find_all('a', href=True):
    href = fix_url(final_url, a['href'])
    if href.lower().split('?')[0].endswith(('.pdf', '.xlsx', '.xls')):
      text = ' '.join(a.get_text().split())
      comb = (text + ' ' + href).lower()
      if any(bad in comb for bad in JUNK_DOCS):
        continue
      if any(good in comb for good in DOC_KEYWORDS):
        pdfs.append({'name': text or 'Официальный каталог PDF', 'url': href})

  # Фото коробок/наборов
  for img in soup.find_all('img'):
    src = (
        img.get('src')
        or img.get('data-src')
        or img.get('data-original')
        or img.get('data-lazy-src')
    )
    if not src:
      continue
    full = fix_url(final_url, src)
    if not full or any(
        j in full.lower()
        for j in ['logo', 'icon', 'banner', 'slider', 'social']
    ):
      continue
    if not re.search(r'\.(jpg|jpeg|png|webp)', full.lower()):
      continue

    alt = (img.get('alt') or img.get('title') or '').strip()
    parent_text = (
        img.parent.get_text(' ', strip=True) if img.parent else ''
    )[:300]
    title = alt or parent_text[:60] or 'Подарочный набор'

    if is_target_item(title, parent_text + ' ' + page_ctx + ' ' + full):
      m = WEIGHT_REGEX.search(parent_text + ' ' + title)
      imgs.append({
          'title': title[:100],
          'weight': m.group(1) if m else None,
          'url': full,
      })

  return pdfs, imgs


def deep_scan(site_url):
  html, final_url = safe_fetch(site_url)
  if not html:
    return None, None, 0

  domain = urllib.parse.urlparse(final_url).netloc.replace('www.', '')
  soup = BeautifulSoup(html, 'lxml')

  pages = {final_url}
  for path in (
      '/catalog/',
      '/products/',
      '/podarki/',
      '/novogodnie-podarki/',
      '/upakovka/',
  ):
    pages.add(urllib.parse.urljoin(final_url, path))

  for a in soup.find_all('a', href=True):
    href = fix_url(final_url, a['href'])
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

  queue = list(pages)[:35]
  all_pdfs, all_imgs = [], []

  with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    for p, i in ex.map(scan_single_page, queue):
      all_pdfs.extend(p)
      all_imgs.extend(i)

  pdfs = list({d['url']: d for d in all_pdfs}.values())
  imgs = list({d['url']: d for d in all_imgs}.values())
  return pdfs, imgs, len(queue)


# =========================================================
# 🖥 ИНТЕРФЕЙС STREAMLIT
# =========================================================

st.set_page_config(
    page_title='Первый Снег | Поисковик ЕАЭС', page_icon='❄️', layout='wide'
)

st.title('❄️ Первый Снег | Живой Веб-Поисковик Каталогов')
st.caption(
    'Поиск официальных сайтов компаний без генерации фейковых доменов .RU. Сбор'
    ' подарочных наборов и упаковки (картон, МГК, тубы).'
)

company_input = st.text_input(
    'Введите название компании (заказчика / конкурента):',
    placeholder='СолБигТрейд, Абинекс, Спартак, Коммунарка, Рубин, Рахат...',
)

if st.button(
    '🚀 НАЙТИ ОФИЦИАЛЬНЫЙ САЙТ И СОБРАТЬ КАТАЛОГИ',
    type='primary',
    use_container_width=True,
):
  if not company_input.strip():
    st.warning('Пожалуйста, введите название компании.')
    st.stop()

  with st.spinner(
      f'Поиск и проверка официального сайта «{company_input}» в сети...'
  ):
    site_info = find_official_website(company_input.strip())

  if not site_info:
    st.error(
        f'❌ Не удалось автоматически найти официальный сайт для компании'
        f' «{company_input}». Пожалуйста, укажите адрес сайта напрямую'
        ' (например: конфета.бел или abinex.ru).'
    )
    st.stop()

  st.success(
      f"🌐 Найден и подтвержден сайт: **[{site_info['url']}]({site_info['url']})**"
  )

  with st.spinner('Глубокий обход каталогов и выгрузка подарков...'):
    pdfs, imgs, pages_count = deep_scan(site_info['url'])

  if pdfs is None:
    st.error(f"Сайт {site_info['url']} найден, но не отвечает на запросы.")
    st.stop()

  st.info(f'Просканировано целевых страниц: **{pages_count}**')
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
st.caption('Инструмент «Первый Снег» | Семантический веб-поисковик ЕАЭС.')
