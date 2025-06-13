import streamlit as st
from itsdangerous import URLSafeSerializer, BadSignature
import os
from dotenv import load_dotenv
from streamlit.components.v1 import html, iframe as components_iframe
load_dotenv()  

# Настройка сериализатора
token_key = os.getenv("FNS_TOKEN") 
if not token_key:
    st.error("Не удалось получить FNS_TOKEN: задайте переменную окружения или добавьте в secrets.toml")
    st.stop()

serializer = URLSafeSerializer(token_key, salt="uid-salt")

# 1) Встраиваем скрипт для приёма токена из дочернего окна
html("""
<script>
  window.addEventListener('message', e => {
    const token = e.data;
    // сохраняем токен в родительском окне
    parent.window.authToken = token;
    // сразу же шлём сообщение назад, чтобы Streamlit мог его поймать
    parent.postMessage({ auth: token }, "*");
  }, false);
</script>
""", height=0)

# 2) Встраиваем сам iframe без key-параметра (он не поддерживается)
components_iframe(
    src="https://ai5.space",
    height=60,
    scrolling=True
)

# 3) Ждём сообщения от iframe — оно попадёт в query-параметр ?auth=...
query_params = st.experimental_get_query_params()
token = query_params.get("auth", [None])[0] or st.session_state.get("auth_token")

# 4) Если токена ещё нет, пробуем его подхватить через JS
if not token:
    # st_javascript — если вы используете сторонний компонент для выполнения JS-кода
    try:
        from streamlit_javascript import st_javascript
        token_js = st_javascript("window.authToken")  # берём токен из глобальной переменной
    except ImportError:
        token_js = None

    if token_js:
        st.session_state.auth_token = token_js
        st.experimental_rerun()
    else:
        st.info("Пожалуйста, выполните логин в iframe выше.")
        st.stop()

# 5) Десериализуем токен и показываем результат
try:
    uid = serializer.loads(token)
    st.success(f"Logged in as user: {uid}")
except BadSignature:
    st.error("Некорректный или просроченный токен")



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
