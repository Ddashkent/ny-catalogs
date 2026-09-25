import concurrent.futures
import datetime
import io
import re
import urllib.parse
import zipfile
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

st.set_page_config(page_title="Первый Снег | Анализ Упаковки", page_icon="❄️", layout="wide")

TARGET_YEAR = 2026

# ДИЗАЙН: Логотип + Нежный снег
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9; }
    .brand-logo {
        position: fixed; top: 12px; right: 15px; z-index: 9999;
        background-color: #dc2626; color: #fff !important;
        font-weight: 900; font-size: 14px; padding: 8px 16px;
        border-radius: 8px; border: 2px solid #fff;
        box-shadow: 0 4px 15px rgba(220,38,38,0.3);
        letter-spacing: 1px;
    }
    @keyframes snowfall {
        0% { transform: translateY(-10px) translateX(0); opacity: 0; }
        15% { opacity: 0.4; }
        100% { transform: translateY(100vh) translateX(20px); opacity: 0; }
    }
    .flake { position: fixed; top: -12px; color: #bae6fd; font-size: 12px; pointer-events: none; z-index: 0; }
    .f1 { left: 12%; animation: snowfall 20s linear infinite; }
    .f2 { left: 40%; animation: snowfall 24s linear infinite 4s; }
    .f3 { left: 72%; animation: snowfall 22s linear infinite 2s; }
    
    .product-card {
        background-color: #ffffff; border: 1px solid #e2e8f0;
        border-radius: 10px; padding: 10px; text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 12px;
    }
    .badge-cardboard {
        background-color: #16a34a; color: white; font-weight: bold;
        padding: 2px 8px; font-size: 10px; border-radius: 4px;
        display: inline-block; margin-bottom: 4px;
    }
    <style>
""", unsafe_allow_html=True)

# Логотип в углу
st.markdown("""
<div class="brand-logo">❄️ ПЕРВЫЙ СНЕГ</div>
<div class="flake f1">❄</div><div class="flake f2">❅</div><div class="flake f3">❆</div>
""", unsafe_allow_html=True)

st.title("📦 Анализ Картонной Упаковки 2026")
st.caption("Приоритет: Официальные каталоги PDF/Excel. Без презентаций, без текстиля, без баннеров.")

# -----------------------------
# ЖЕСТКОЙ СПИСОК (НЕ МЕНЯТСЯ) — ГАРАНТИРУЕТ РАБОТУ
# -----------------------------

SITE_MAP = {
    "rubin": "rubin-2000.ru",
    "рубин": "rubin-2000.ru",
    "академия шоколада": "chocolate-academy.ru",
    "лаконд": "lakond.ru",
    "акконд": "akkond.ru",
    "донко": "donko.su",
    "рэйд": "podarki-reid21.ru",
    "рэйд 21": "podarki-reid21.ru",
    "рейд 21": "podarki-reid21.ru",
    "баян сулу": "bayansulu.kz",
    "конфешн": "confashion.ru",
    "тореро": "torero.ru",
    "фортуна": "fortuna-podarki.ru",
    "униконф": "uniconf.ru",
    "красный октябрь": "uniconf.ru",
    "бабаевский": "uniconf.ru",
    "спартак": "spartak.by",
    "коммунарка": "kommunarka.by",
    "рахат": "rakhat.kz",
    "сибпродторг": "sibprodtorg.ru",
    "столичные": "stolichnye.ru",
    "рэйд-21": "podarki-reid21.ru",
}

# Фильтры мусора
JUNK_DOC_WORDS = ["политика", "согласие", "презентация", "реквизиты", "договор", "оферта", "вакансии", "cookies", "инвесторам"]
GOOD_DOC_WORDS = ["каталог", "прайс", "подарки", "упаковка", "2026", "2025", "catalog", "price"]

# Фильтры для картинок
BAN_KEYWORDS = ["logo", "icon", "social", "avatar", "banner", "slider", "bg-", "delivery", "payment"]
TEXTILE_KEYWORDS = ["текстиль", "мягкая", "плюш", "игрушка", "ткань", "мешок", "подушка", "рюкзак"]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# -----------------------------
# ФУНКЦИИ
# -----------------------------

def get_domain(name: str) -> str:
    n = name.strip().lower()
    for k in SITE_MAP:
        if k in n:
            return SITE_MAP[k]
    # Прямой ввод
    if "." in n and " " not in n:
        return n.replace("https://", "").replace("http://", "").split("/")[0]
    return "rubin-2000.ru"

def fetch_docs(domain: str):
    docs = []
    seen = set()
    check_urls = [
        f"https://{domain}",
        f"https://{domain}/catalog/",
        f"https://{domain}/catalog/novogodnie-podarki/",
        f"https://{domain}/podarki/",
        f"https://{domain}/katalog/"
    ]
    if domain == "podarki-reid21.ru":
        check_urls.insert(0, "https://podarki-reid21.ru/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/")
    
    for url in check_urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=7, verify=False)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].lower()
                    text = a.get_text().strip().lower()
                    if any(ext in href for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                        if any(bad in text for bad in JUNK_DOC_WORDS): continue
                        if any(good in text or good in href for good in GOOD_DOC_WORDS):
                            full = urllib.parse.urljoin(url, a["href"])
                            if full not in seen:
                                seen.add(full)
                                docs.append({"title": a.get_text().strip() or "Официальный каталог", "url": full})
        except: pass
    return docs

def fetch_images(domain: str):
    # Для Рэйд-21 сразу идем в раздел (если нет PDF)
    base = f"https://{domain}"
    urls = [base + "/present-category/novogodnie-podarki-2027/podarki-v-kartonnoj-upakovke-novogodnie-podarki-2027/"] if domain == "podarki-reid21.ru" else [base + "/catalog/", base]
    
    products = []
    seen = set()
    
    for url in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=8, verify=False)
            if res.status_code != 200: continue
            soup = BeautifulSoup(res.text, "html.parser")
            
            for img in soup.find_all("img"):
                src = img.get("data-src") or img.get("src")
                if not src: continue
                
                # Пропускаем системные элементы
                if any(b in src.lower() for b in BAN_KEYWORDS + ["logo", "icon", "payment", "delivery", "social", "vk", "tg"]):
                    continue
                
                full = urllib.parse.urljoin(url, src)
                # Убираем макетные резайзы
                full = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", full)
                full = re.sub(r"/resize_cache/.*?/\d+_\d+_\d+/", "/upload/", full)
                
                if full in seen: continue
                seen.add(full)
                
                # Фильтр по тексту карточки (убираем мягкое, текстиль)
                card_text = img.parent.get_text(" ", strip=True).lower() if img.parent else ""
                if any(bad in card_text for bad in TEXTILE_KEYWORDS): continue
                
                # Фильтр пропорций (убираем баннеры)
                try:
                    img_res = requests.get(full, timeout=4, verify=False)
                    if img_res.status_code == 200 and len(img_res.content) > 3000:
                        if HAS_PIL:
                            pil = Image.open(io.BytesIO(img_res.content))
                            w, h = pil.size
                            if w < 140 or h < 140: continue
                            if w / h > 1.6: continue  # Баннеры очень широкие
                        products.append({
                            "title": (img.get("alt") or img.get("title") or "Коробка / Упаковка"),
                            "img": full,
                            "bytes": img_res.content
                        })
                except:
                    # Если не можем проверить — всё равно добавляем, но не грузим байты
                    products.append({"title": (img.get("alt") or "Упаковка"), "img": full, "bytes": None})
        except Exception as e:
            pass
    
    return products

# -----------------------------
# ИНТЕРФЕЙС
# -----------------------------

query = st.text_input("Введите название фабрики или адрес сайта:", placeholder="Рубин, Рэйд 21, Лаконд, rubin-2000.ru...")

if st.button("🚀 ПОЛУЧИТЬ КАТАЛОГ / УПАКОВКУ", type="primary", use_container_width=True):
    if not query.strip():
        st.warning("Введите название")
        st.stop()
    
    domain = get_domain(query)
    st.info(f"🌐 Подключено к источнику: `{domain}`")
    
    with st.spinner("Ищу официальные файлы..."):
        docs = fetch_docs(domain)
    
    if docs:
        st.subheader("📄 Официальные Каталоги / Прайсы")
        for d in docs:
            st.markdown(f'<div style="background:white; padding:12px; border-left:6px solid #dc2626; border-radius:8px; margin-bottom:10px;"><b>{d["title"]}</b> <br> <a href="{d["url"]}" target="_blank" style="background:#dc2626;color:white;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold;">📥 СКАЧАТЬ ФАЙЛ</a></div>', unsafe_allow_html=True)
    else:
        with st.spinner("Ищу визуальные карточки упаковки..."):
            items = fetch_images(domain)
        
        if items:
            st.subheader(f"📦 Найдено коробок и упаковки: {len(items)} шт.")
            
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for i, it in enumerate(items):
                    if it["bytes"]:
                        zf.writestr(f"box_{i+1:02d}.jpg", it["bytes"])
                    else:
                        # Если байты не загрузились, скачиваем сейчас
                        try:
                            r = requests.get(it["img"], timeout=5, verify=False)
                            zf.writestr(f"box_{i+1:02d}.jpg", r.content)
                        except: pass
            
            st.download_button("📥 СКАЧАТЬ ВСЕ КОРОБКИ В ZIP", zip_buf.getvalue(), f"{domain}_cardboard.zip", "application/zip")
            
            cols = st.columns(4)
            for idx, it in enumerate(items):
                with cols[idx % 4]:
                    try:
                        img_display = it["bytes"] if it["bytes"] else requests.get(it["img"], timeout=3, verify=False).content
                        st.image(img_display, use_container_width=True)
                    except:
                        st.image(it["img"], use_container_width=True)
                    st.markdown(f'<div style="font-weight:bold; font-size:12px; color:#1e293b; margin-top:8px;">{it["title"][:50]}</div><div style="font-size:11px; color:#16a34a; font-weight:bold;">📦 КАРТОН / УПАКОВКА</div>', unsafe_allow_html=True)
        else:
            st.error("Не удалось найти картонную упаковку. Проверьте название или введите прямой адрес сайта.")
