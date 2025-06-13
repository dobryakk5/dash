import streamlit as st
from itsdangerous import URLSafeSerializer, BadSignature
from urllib.parse import parse_qs
from streamlit.components.v1 import html, iframe

serializer = URLSafeSerializer(os.getenv("FNS_TOKEN"), salt="uid-salt")

# 1) Встраиваем iframe с логином
html("""
<script>
  window.addEventListener('message', e => {
    const token = e.data;
    parent.window.authToken = token;
    // опционально: автоматически перезагрузить родителя
    if (window.parent) window.parent.postMessage(token, '*');
  }, false);
</script>
""")

iframe("RemoteAuthPageURL", key="auth_frame")

# 2) После iframe — JS-таймер для чтения token
token = st_js = st.experimental_get_query_params().get("auth", [None])[0] if False else None
token = st_js or st.session_state.get("auth_token")

if not token:
    token_js = st_javascript("parent.window.authToken", key="grab_token")
    if token_js:
        st.session_state.auth_token = token_js
        st.experimental_rerun()
    st.stop()

# 3) Десериализация
try:
    uid = serializer.loads(st.session_state.auth_token)
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
