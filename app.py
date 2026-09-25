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
# КОНСТИТУЦИЯ ДИЗАЙНА "ПЕРВЫЙ СНЕГ"
# -----------------------------

st.set_page_config(page_title="Первый Снег | Экстрактор Картона", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    
    /* Официальный красно-белый логотип */
    .brand-header {
        position: fixed; top: 15px; right: 20px; z-index: 99999;
        background-color: #dc2626; color: #ffffff !important;
        font-weight: 900; font-size: 16px; padding: 10px 22px;
        border-radius: 6px; border: 2px solid #ffffff;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
        letter-spacing: 1px;
    }
    
    /* Нежный медленный снег */
    @keyframes snowfall {
        0% { transform: translateY(-10px); opacity: 0; }
        20% { opacity: 0.4; }
        100% { transform: translateY(100vh); opacity: 0; }
    }
    .flake { position: fixed; top: -10px; color: #bae6fd; pointer-events: none; z-index: 0; font-size: 14px; }
    
    .product-card {
        background: white; border: 1px solid #e2e8f0;
        padding: 10px; border-radius: 12px; text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.03); margin-bottom: 20px;
    }
    .badge-material {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 3px 8px; font-size: 11px; border-radius: 4px;
        display: inline-block; margin-bottom: 5px;
    }
    .item-title { font-weight: 700; font-size: 13px; color: #1e293b; min-height: 40px; }
    </style>
    
    <div class="brand-header">❄️ ПЕРВЫЙ СНЕГ</div>
    <div class="flake" style="left:10%; animation: snowfall 18s linear infinite;">❄</div>
    <div class="flake" style="left:40%; animation: snowfall 22s linear infinite 3s;">❅</div>
    <div class="flake" style="left:80%; animation: snowfall 20s linear infinite 1s;">❆</div>
""", unsafe_allow_html=True)

st.title(f"📦 Экстрактор Картонной Упаковки {TARGET_YEAR}")
st.caption("Уникальный алгоритм: сам находит разделы с картоном и МГК, отсекая текстиль и баннеры.")

# -----------------------------
# УНИКАЛЬНЫЕ ПРАВИЛА (ФИЛЬТРЫ)
# -----------------------------

# БЛОКИРОВКА МЯГКИХ ИГРУШЕК И ТЕКСТИЛЯ
TEXTILE_JUNK = ["текстиль", "мягкая", "игрушка", "плюш", "ткань", "рюкзак", "подушка", "мешок", "состав", "вложение", "оплата", "доставка"]

# КЛЮЧИ ДЛЯ ПОИСКА КАРТОНА
CARDBOARD_KEYS = ["картон", "мгк", "karton", "upakovka", "box", "catalog", "podarki", "produk", "shop", "present"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ЛОГИКА "СЛЕДОПЫТА"
# -----------------------------

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if res.status_code == 200: return res.url, res.text
    except: pass
    return None, None

def find_catalog_link(base_url, domain):
    """Ищет на сайте ПРЯМУЮ ссылку на раздел с картонными коробками"""
    _, html = get_html(base_url)
    if not html: return [base_url]
    
    soup = BeautifulSoup(html, "html.parser")
    found_links = [base_url]
    
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        text = a.get_text().lower()
        full = urllib.parse.urljoin(base_url, a['href'])
        
        # Если ссылка ведет на картон, МГК или подарки в упаковке - берем!
        if domain in full:
            if any(key in href or key in text for key in ["karton", "картон", "upakovka", "box", "catalog", "present"]):
                if not any(bad in href or bad in text for bad in ["tekstil", "текстиль", "oplata", "dostavka"]):
                    if full not in found_links: found_links.append(full)
    
    return found_links[:10] # Возвращаем топ-10 вероятных путей

def parse_items(url):
    """Извлекает только коробки из картона с конкретной страницы"""
    prods = []
    final_url, html = get_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, "html.parser")
    # Ищем картинки в контейнерах (product, card, item)
    cards = soup.find_all(["div", "li", "article"], class_=re.compile(r"product|card|item|entry", re.I))
    if not cards: cards = soup.find_all("img")

    seen_imgs = set()
    for card in cards:
        img = card if card.name == "img" else card.find("img")
        if not img: continue
        
        src = img.get("data-src") or img.get("src")
        if not src or any(bad in src.lower() for bad in ["logo", "icon", "banner", "bg-", "delivery", "payment"]): continue
        
        full_img = urllib.parse.urljoin(final_url, src)
        # Убираем ресайзы для высокого качества
        full_img = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full_img)
        
        if full_img in seen_imgs: continue
        
        text = card.get_text(" ", strip=True) if card.name != "img" else ""
        title = img.get("alt") or img.get("title") or text[:60]
        
        # ЖЕСТКИЙ ФИЛЬТР ТЕКСТИЛЯ И МЯГКОЙ УПАКОВКИ
        if any(bad in title.lower() or bad in text.lower() for bad in TEXTILE_JUNK): continue
        
        # ФИЛЬТР ПРОПОРЦИЙ (Блокирует горизонтальные баннеры оплаты/доставки)
        if HAS_PIL:
            try:
                img_data = requests.get(full_img, timeout=5).content
                img_pil = Image.open(io.BytesIO(img_data))
                w, h = img_pil.size
                if (w / h) > 1.6 or (w / h) < 0.4: continue # Только вертикальные или квадратные коробки
                img_ready = img_data
            except: continue
        else: img_ready = None

        seen_imgs.add(full_img)
        prods.append({"title": title.strip(), "img": full_img, "bytes": img_ready})
    return prods

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

company_input = st.text_input("Введите название фабрики или адрес её сайта:", 
                             placeholder="Рэйд-21, Рубин, Лаконд, chocolate-academy.ru...")

if st.button("🚀 ПОЛУЧИТЬ КАРТОННУЮ УПАКОВКУ", type="primary", use_container_width=True):
    if company_input:
        # Авто-определение домена
        domain = company_input.strip().lower()
        if "рэйд" in domain or "reid" in domain: domain = "podarki-reid21.ru"
        if not "." in domain: domain += ".ru"
        
        base_url = f"https://{domain}"
        st.success(f"🌐 Инициализация сканера для: `{domain}`")
        
        with st.spinner("Следопыт ищет разделы с картонной упаковкой..."):
            target_links = find_catalog_link(base_url, domain)
        
        all_items = []
        with st.spinner(f"Захожу в {len(target_links)} разделов и выгружаю коробки..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = executor.map(parse_items, target_links)
                for res in results: all_items.extend(res)
        
        # Удаляем дубли
        unique_items = {it['img']: it for it in all_items}.values()
        
        if unique_items:
            st.success(f"Найдено оригинальных коробок: **{len(unique_items)} шт.**")
            
            # ZIP
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for i, it in enumerate(unique_items):
                    if it['bytes']:
                        zf.writestr(f"box_{i+1:02d}.jpg", it['bytes'])
            st.download_button("📥 СКАЧАТЬ ВСЕ КОРОБКИ В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")

            st.markdown("---")
            cols = st.columns(4)
            for i, it in enumerate(unique_items):
                with cols[i % 4]:
                    st.markdown('<div class="product-card">', unsafe_allow_html=True)
                    st.image(it['bytes'] if it['bytes'] else it['img'], use_container_width=True)
                    st.markdown(f'<span class="badge-material">📦 КАРТОН / МГК</span><br><div class="item-title">{it["title"][:60]}</div></div>', unsafe_allow_html=True)
        else:
            st.error("Не удалось найти картонную упаковку. Попробуйте ввести прямую ссылку на раздел сайта.")
