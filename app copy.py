import streamlit as st
from itsdangerous import URLSafeSerializer, BadSignature
import os
from dotenv import load_dotenv
from streamlit.components.v1 import html, iframe as components_iframe
import pandas as pd
from sqlalchemy import create_engine, text

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    st.error("Не найдена переменная DB_URL: задайте строку подключения к базе данных")
    st.stop()
engine = create_engine(DB_URL, echo=False)

# Настройка сериализатора
token_key = os.getenv("FNS_TOKEN")
if not token_key:
    st.error("Не удалось получить FNS_TOKEN: задайте переменную окружения или добавьте в secrets.toml")
    st.stop()

serializer = URLSafeSerializer(token_key, salt="uid-salt")

# Встраиваем JS для получения токена
html("""
<script>
  window.addEventListener('message', e => {
    const token = e.data;
    parent.window.authToken = token;
    parent.postMessage({ auth: token }, "*");
  }, false);
</script>
""", height=0)

components_iframe(src="https://ai5.space", height=60, scrolling=True)

# Получаем query-параметр auth
query_params = st.experimental_get_query_params()
token = query_params.get("auth", [None])[0] or st.session_state.get("auth_token")

# Если токена ещё нет — пробуем через JS
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

# Десериализуем token
try:
    uid = serializer.loads(token)
except BadSignature:
    st.error("Некорректный или просроченный токен")
    st.stop()

# uid есть — переходим к работе с БД
st.success(f"✅ Logged in as user: {uid}")

# Здесь настраиваем подключение к базе
# Пример:
# engine = create_engine(os.getenv("DATABASE_URL"))
# import pandas as pd

# Выполняем select после уверенности, что uid определён
try:
    df = pd.read_sql(
        text("SELECT * FROM purchases WHERE user_id = :uid"),
        engine,
        params={"uid": uid}
    )
except Exception as e:
    st.error(f"Ошибка при загрузке данных: {e}")
    st.stop()

st.write("📋 **Ваши покупки**")
edited = st.data_editor(df, use_container_width=True)

# Кнопка "Сохранить изменения"
if st.button("💾 Сохранить изменения"):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM purchases WHERE user_id = :uid"), {"uid": uid})
        edited["user_id"] = uid
        edited.to_sql("purchases", engine, if_exists="append", index=False)
        st.success("✅ Изменения сохранены")
    except Exception as e:
        st.error(f"Ошибка при сохранении: {e}")
