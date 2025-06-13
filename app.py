import streamlit as st
import pandas as pd
from itsdangerous import URLSafeSerializer, BadSignature
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from streamlit.components.v1 import html, iframe as components_iframe

# Load environment variables
load_dotenv()

# Database connection
# Ensure you have DB_URL defined in .env or Streamlit secrets
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    st.error("Не найдена переменная DB_URL: задайте строку подключения к базе данных")
    st.stop()
engine = create_engine(DB_URL, echo=False)

# Настройка сериализатора (iframe auth)
token_key = os.getenv("FNS_TOKEN")
if not token_key:
    st.error("Не удалось получить FNS_TOKEN: задайте переменную окружения или добавьте в secrets.toml")
    st.stop()
serializer = URLSafeSerializer(token_key, salt="uid-salt")

# 1) Приём токена из дочернего окна через JS
html("""
<script>
  window.addEventListener('message', e => {
    const token = e.data;
    parent.window.authToken = token;
    parent.postMessage({ auth: token }, "*");
  }, false);
</script>
""", height=0)

# 2) Встраиваем iframe для логина
def show_login_iframe():
    components_iframe(src="https://ai5.space", height=60, scrolling=True)

show_login_iframe()

# 3) Получаем токен из query params или сессии
query_params = st.experimental_get_query_params()
token = query_params.get("auth", [None])[0] or st.session_state.get("auth_token")

# 4) Если токена нет, пытаемся через JS-глобальную переменную или останавливаем
if not token:
    try:
        from streamlit_javascript import st_javascript
        token_js = st_javascript("window.authToken")
    except ImportError:
        token_js = None

    if token_js:
        st.session_state.auth_token = token_js
        st.experimental_rerun()
    else:
        st.info("Пожалуйста, выполните логин в iframe выше.")
        st.stop()

# 5) Десериализуем токен и выводим приветствие
try:
    uid_iframe = serializer.loads(token)
    st.success(f"Добро пожаловать, iframe user_id = {uid_iframe}")
except BadSignature:
    st.error("Некорректный или просроченный токен")
    st.stop()

# === Основная логика приложения ===

# DEV MODE переключатель (без авторизации Telegram)
DEV_MODE = st.sidebar.checkbox("DEV_MODE (без авторизации Telegram)", value=False)

if DEV_MODE:
    uid = st.sidebar.text_input("Введите user_id для теста", value=str(uid_iframe))
    if not uid:
        st.warning("Введите user_id в режиме DEV_MODE")
        st.stop()
    st.info(f"🔧 Режим DEV: используем user_id = {uid}")
else:
    # Telegram Login
    from streamlit_telegram_login import TelegramLoginWidgetComponent
    API_TOKEN = os.getenv("API_TOKEN")
    if not API_TOKEN:
        st.error("Не найдена переменная API_TOKEN для Telegram Login")
        st.stop()
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

# Загрузка данных из базы для текущего user_id
df = pd.read_sql(
    text("SELECT * FROM purchases WHERE user_id = :uid"),
    engine,
    params={"uid": uid}
)

st.write("📋 **Ваши покупки**")
edited = st.data_editor(df, use_container_width=True)

# Сохранение изменений при клике
if st.button("💾 Сохранить изменения"):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM purchases WHERE user_id = :uid"),
            {"uid": uid}
        )
    edited["user_id"] = uid
    edited.to_sql("purchases", engine, if_exists="append", index=False)
    st.success("✅ Изменения сохранены")
