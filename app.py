import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from streamlit_telegram_login import TelegramLoginWidgetComponent

# Загрузка .env
load_dotenv()

# Подключение к базе
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    st.error("Не найдена переменная DB_URL: задайте строку подключения к базе данных")
    st.stop()

engine = create_engine(DB_URL, echo=False)
st.title("Ваше приложение")

# Выбор режима: DEV или PROD
DEV_MODE = st.sidebar.checkbox("DEV_MODE (без авторизации)", value=False)

if DEV_MODE:
    uid = st.sidebar.text_input("Введите user_id для теста", value="7852511755")
    if not uid:
        st.warning("Введите user_id")
        st.stop()
    st.info(f"🔧 Режим DEV: работаем с user_id = {uid}")
else:
    API_TOKEN = os.getenv("API_TOKEN")
    if not API_TOKEN:
        st.error("Не найдена переменная API_TOKEN")
        st.stop()
    telegram_login = TelegramLoginWidgetComponent(
        bot_username="fin_a_bot",
        secret_key=API_TOKEN
    )
    user_info = telegram_login.button
    if not user_info:
        st.info("🔐 Пожалуйста, войдите через Telegram")
        st.stop()
    uid = user_info.get("id")
    if not uid:
        st.error("Не удалось получить Telegram ID")
        st.stop()
    st.success(f"✔️ Вы авторизованы как Telegram ID: {uid}")

# Выполнение SELECT
df = pd.read_sql(
    text("SELECT * FROM purchases WHERE user_id = :uid"),
    engine,
    params={"uid": uid}
)

st.write("📋 **Ваши покупки**")
edited = st.data_editor(df, use_container_width=True)

# Сохранение
if st.button("💾 Сохранить изменения"):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM purchases WHERE user_id = :uid"), {"uid": uid})
    edited["user_id"] = uid
    edited.to_sql("purchases", engine, if_exists="append", index=False)
    st.success("✅ Изменения сохранены")
