import time
import traceback
from datetime import datetime, timezone

import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Проверка подключения",
    page_icon="🔎",
    layout="wide",
)

# Здесь проверяются адреса из текущего приложения.
# Это не реестр для поиска новых компаний.
SITES = {
    "Спартак": "spartak.by",
    "Коммунарка": "kommunarka.by",
    "Рубин": "rubin-2000.ru",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
}


def check_url(url):
    row = {
        "Проверяемый адрес": url,
        "HTTP": "",
        "Итоговый адрес": "",
        "Заголовок страницы": "",
        "Ошибка": "",
        "Время, сек.": 0.0,
    }
    details = [f"Проверка: {url}"]
    started = time.perf_counter()

    try:
        # Проверка сертификатов включена.
        # Никаких прокси, скрытых повторов или параллельных запросов.
        with requests.get(
            url,
            headers=HEADERS,
            timeout=(6, 12),
            allow_redirects=True,
            stream=True,
            verify=True,
        ) as response:
            row["HTTP"] = str(response.status_code)
            row["Итоговый адрес"] = response.url

            for previous in response.history:
                details.append(
                    f"Перенаправление: HTTP {previous.status_code} "
                    f"{previous.url} -> "
                    f"{previous.headers.get('Location', '')}"
                )

            details.append(f"Итоговый адрес: {response.url}")
            details.append(f"HTTP: {response.status_code}")
            details.append(
                "Content-Type: "
                + response.headers.get("Content-Type", "не указан")
            )

            # Для проверки достаточно начала страницы.
            # Не скачиваем весь сайт и не создаём ZIP.
            content = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    content.extend(chunk)
                if len(content) >= 65536:
                    break

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "html" in content_type or not content_type:
                soup = BeautifulSoup(bytes(content), "html.parser")

                if soup.title:
                    row["Заголовок страницы"] = soup.title.get_text(
                        " ", strip=True
                    )

                preview = soup.get_text(" ", strip=True)[:400]
                details.append(
                    "Заголовок: " + row["Заголовок страницы"]
                )
                details.append("Начало текста страницы: " + preview)

            # HTTP-отказы сохраняем как HTTP-отказы,
            # а не называем их географической блокировкой.
            if response.status_code >= 400:
                row["Ошибка"] = f"HTTP {response.status_code}"

    except Exception as error:
        row["Ошибка"] = type(error).__name__
        details.append(f"Тип исключения: {type(error).__name__}")
        details.append(f"Сообщение: {error}")
        details.append(traceback.format_exc())

    row["Время, сек."] = round(time.perf_counter() - started, 1)
    details.append(f"Время: {row['Время, сек.']} сек.")

    return row, "\n".join(details)


st.title("🔎 Проверка доступа к сайтам из Streamlit")
st.write(
    "Проверяем настоящие ответы сервера. "
    "Никаких предположений о блокировке."
)

with st.form("connection_test"):
    company = st.selectbox("Компания:", list(SITES))
    submitted = st.form_submit_button("Проверить подключение")

if submitted:
    host = SITES[company]
    urls = [
        f"https://{host}/",
        f"https://www.{host}/",
        f"http://{host}/",
        f"http://www.{host}/",
    ]

    rows = []
    reports = []

    for url in urls:
        row, report = check_url(url)
        rows.append(row)
        reports.append(report)

    header = (
        f"Компания: {company}\n"
        f"Дата: {datetime.now(timezone.utc).isoformat()}\n"
        f"Streamlit: {st.__version__}\n"
        f"Requests: {requests.__version__}\n"
    )

    st.session_state["connection_test_result"] = {
        "company": company,
        "rows": rows,
        "report": header + "\n\n" + "\n\n".join(reports),
    }

result = st.session_state.get("connection_test_result")

if result:
    st.subheader(f"Результаты: {result['company']}")
    st.dataframe(
        result["rows"],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("Технический отчёт", expanded=True):
        st.code(result["report"], language="text")

    st.download_button(
        "Скачать отчёт",
        data=result["report"].encode("utf-8"),
        file_name="connection_report.txt",
        mime="text/plain",
    )
