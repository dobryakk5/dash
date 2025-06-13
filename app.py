import os
import streamlit as st
from itsdangerous import URLSafeSerializer, BadSignature
from streamlit_javascript import st_javascript
from urllib.parse import parse_qs, urlparse

# ─── 0) Настройка ────────────────────────────────────────────────────────────────
serializer = URLSafeSerializer(os.getenv("FNS_TOKEN"), salt="uid-salt")

# ─── 1) Инициализация session_state ─────────────────────────────────────────────
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None

# ─── 2) Если токена ещё нет, получаем его через JS и сразу же перезапускаем скрипт ──
if not st.session_state.auth_token:
    # собираем полный URL родителя
    parent_url = st_javascript(
        "await fetch('').then(_ => window.parent.location.href)",
        key="js_url"
    )
    if parent_url:
        # достаём из него auth-параметр
        params = parse_qs(urlparse(parent_url).query)
        auth = params.get("auth", [None])[0]
        if auth:
            st.session_state.auth_token = auth
            # перезапускаем весь скрипт, чтобы дальше он пошёл с session_state.auth_token
            st.experimental_rerun()
    # если parent_url ещё не пришёл или в нём нет auth — показываем спиннер и жмём Stop
    st.spinner("Ждём токен…")
    st.stop()

# ─── 3) У нас в session_state.auth_token уже есть значение ────────────────────────
token = st.session_state.auth_token
st.write("Используемый токен:", token)

# ─── 4) Десериализуем и получаем uid ──────────────────────────────────────────────
try:
    uid = serializer.loads(token)
    st.success(f"Десериализовали uid: {uid}")
except BadSignature:
    st.error("Токен некорректен или просрочен.")
    st.stop()
except Exception as e:
    st.error(f"При десериализации токена ошибка: {e}")
    st.stop()

# ─── 5) Токен и uid валидны — дальше ваша логика ──────────────────────────────────
st.write("Добро пожаловать, user_id =", uid)
# …здесь ваши запросы в базу, выдача таблиц и т.д.

# 1. Режим разработки vs. продакшн
DEV_MODE = st.sidebar.checkbox("DEV_MODE (без авторизации)", value=False)

if DEV_MODE:
    # — Без логина: берём user_id из сайдбара
    uid = st.sidebar.text_input("Введите user_id для теста", value="7852511755")
    if not uid:
        st.warning("Введите user_id")
        st.stop()
    st.info(f"🔧 Режим DEV: показываем данные для user_id = {uid}")
else:
    # — Telegram Login
    from streamlit_telegram_login import TelegramLoginWidgetComponent
    API_TOKEN = os.getenv("API_TOKEN")
    telegram_login = TelegramLoginWidgetComponent(
        bot_username="fin_a_bot",
        secret_key=API_TOKEN
    )
    user_info = telegram_login.button
    if not user_info:
        st.info("🔐 Пожалуйста, войдите через Telegram")
        st.stop()
    uid = user_info["id"]
    st.success(f"Вы авторизованы как Telegram ID: {uid}")

# 2. Загрузка данных для user_id
#
# Чтобы избежать ошибок синтаксиса в psycopg2, используем SQLAlchemy.text + плейсхолдеры :uid.
# Это наиболее надёжный способ: драйвер сам переводит плейсхолдер в правильный формат.
# Производительность при этом не отличается от прямого pyformat, но надёжность и читаемость выше.

df = pd.read_sql(
    text("SELECT * FROM purchases WHERE user_id = :uid"),
    engine,
    params={"uid": uid}
)

st.write("📋 **Ваши покупки**")
edited = st.data_editor(df, use_container_width=True)

# 3. Сохранение изменений
if st.button("💾 Сохранить изменения"):
    with engine.begin() as conn:
        # сначала удаляем старые записи этого пользователя
        conn.execute(
            text("DELETE FROM purchases WHERE user_id = :uid"),
            {"uid": uid}
        )
    # затем вставляем новые строки из edited
    edited["user_id"] = uid
    edited.to_sql("purchases", engine, if_exists="append", index=False)
    st.success("✅ Изменения сохранены")
