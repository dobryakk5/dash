import streamlit as st
from itsdangerous import URLSafeSerializer, BadSignature
import os
from dotenv import load_dotenv
from streamlit.components.v1 import html, iframe as components_iframe
import pandas as pd
from sqlalchemy import create_engine, text
import locale
import warnings
import logging

load_dotenv()

# Убираем меню, хедер и футер через CSS
st.markdown(
    """
    <style>
      /* Скрываем тулбар (Deploy‑кнопку и гамбургер‑меню) */
      .stAppToolbar,
      [data-testid="stToolbar"],
      [data-testid="stAppDeployButton"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
      }

      /* Остальные правила — по вашему усмотрению */
      iframe.stIFrame {
        display: none !important;
        height: 0 !important;
        visibility: hidden !important;
      }
      #MainMenu, header, footer {
        visibility: hidden !important;
      }
      .reportview-container .main .block-container,
      .stApp .main .block-container,
      section.stMain .block-container,
      div[data-testid="stMainBlockContainer"] {
        padding-top: 0 !important;
        margin-top: 0 !important;
      }
      section[data-testid="stSidebar"] > div:first-child {
        top: 0 !important;
        height: 100vh !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── 0.1. Скрываем Deprecation-warnings от Streamlit в консоли ─────────────────────
warnings.filterwarnings(
    "ignore",
    message=r".*st\.experimental_get_query_params.*",
)
logging.getLogger("streamlit").setLevel(logging.ERROR)


serializer = URLSafeSerializer(os.getenv("FNS_TOKEN", ""), salt="uid-salt")

html("""
<script>
  window.addEventListener('message', e => {
    parent.window.authToken = e.data;
    parent.postMessage({ auth: e.data }, "*");
  }, false);
</script>
""", height=0)

components_iframe(src="https://ai5.space", height=60, scrolling=True)

# Заменяем устаревший метод на новый
query_params = st.experimental_get_query_params()
token = query_params.get("auth", [None])[0] or st.session_state.get("auth_token")

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

try:
    uid = serializer.loads(token)
except BadSignature:
    st.error("Некорректный или просроченный токен")
    st.stop()

#st.success(f"✅ Logged in as user: {uid}")

# Подключение к БД
engine = create_engine(os.getenv("DATABASE_URL"))

# Устанавливаем локаль (пример для России)
try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    # Если локаль недоступна на сервере, можно пропустить
    pass

# Выполняем SQL-запрос, выбирая только нужные поля
df = pd.read_sql(
    text("""
        SELECT
            category,
            subcategory,
            price,
            ts  
        FROM purchases
        WHERE user_id = :uid
    """),
    engine,
    params={"uid": uid}
)

# 1) Конвертируем в datetime
df['ts'] = pd.to_datetime(df['ts'], errors='coerce')

# 2) Форматируем локально (например, '14 июня 2025')
df['Дата'] = df['ts'].dt.strftime('%-d %B %Y')

# 3) Переименовываем и оставляем только нужные поля
df = df[['category', 'subcategory', 'price', 'ts']]
df.columns = ['Категория', 'Подкатегория', 'Цена', 'Дата']

st.write("📋 Отредактируйте любое поле и нажмите 💾Сохранить под таблицей")
edited = st.data_editor(df, use_container_width=True)

# создаём копию, чтобы не испортить оригинал
df_to_save = edited.copy()

# переименовываем назад в структуру БД
df_to_save = df_to_save.rename(columns={
    "Категория": "category",
    "Подкатегория": "subcategory",
    "Цена": "price",
    "Дата": "ts"
})

# если дата — строка, переводим обратно в datetime
df_to_save["ts"] = pd.to_datetime(df_to_save["ts"], format='%d %B %Y')

# добавляем столбец user_id
df_to_save["user_id"] = uid

if st.button("💾 Сохранить изменения"):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM purchases WHERE user_id = :uid"), {"uid": uid})
        edited["user_id"] = uid
        edited.to_sql("purchases", engine, if_exists="append", index=False)
        st.success("✅ Изменения сохранены")
    except Exception as e:
        st.error(f"Ошибка при сохранении: {e}")