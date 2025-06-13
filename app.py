import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from itsdangerous import URLSafeSerializer, BadSignature

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))


serializer = URLSafeSerializer(os.getenv("FNS_TOKEN"), salt="uid-salt")
token = st.query_params.get("token", [None])[0]
# 🧪 Распечатаем токен для отладки
st.write("📝 Полученный token:", token)
if not token:
    st.error("Неверная ссылка.")
    st.stop()

try:
    uid = serializer.loads(token)
except BadSignature:
    st.error("Просроченный или некорректный токен.")
    st.stop()

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
