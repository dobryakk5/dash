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
#import page_main, page_detail

#main = st.Page(page_main.app, title="Главная")
#detail = st.Page(page_detail.app, title="Детальная", icon="🔍")
#current = st.navigation([main, detail])
#current.run()


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
#warnings.filterwarnings("ignore", message=r"*query_params*",)
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

st.session_state["uid"] = uid
#st.success(f"✅ Logged in as user: {uid}")

# ─── Подключение к БД и локаль ────────────────────────────────────────────────
engine = create_engine(os.getenv("DATABASE_URL"))

try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except locale.Error:
    pass  # если локаль недоступна

# ─── Загрузка данных и подготовка для редактирования ──────────────────────────
df = pd.read_sql(
    text("""
        SELECT id,
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

# Конвертация и локальное форматирование даты
df['ts'] = pd.to_datetime(df['ts'], errors='coerce')
df['Дата'] = df['ts'].dt.strftime('%d.%m.%Y')

# Оставляем только видимые пользователю столбцы
df = df[['id', 'category', 'subcategory', 'price', 'Дата']]
df.columns = ['id', 'Категория', 'Подкатегория', 'Цена', 'Дата']

# Сохраняем оригинал в сессии для диффа
if 'orig_df' not in st.session_state:
    st.session_state.orig_df = df.copy()

st.write("Отредактируйте любое поле и нажмите 📥 под таблицей")
edited = st.data_editor(
    df.drop(columns=['id']),               # id скрываем, но он в orig_df
    use_container_width=True,
    key='data_editor'
)
# Привяжем id обратно к отредактированному df
edited['id'] = st.session_state.orig_df['id']

# ─── Сохранение изменений в БД (диффовый алгоритм) ───────────────────────────
if st.button("📥 Сохранить изменения"):
    # Подготовка новых и оригинальных табличек
    new = edited.rename(columns={
        "Категория": "category",
        "Подкатегория": "subcategory",
        "Цена": "price",
        "Дата": "ts"
    }).copy()
    new['ts'] = pd.to_datetime(new['ts'], format='%d %B %Y', errors='coerce')
    new['user_id'] = uid

    orig = st.session_state.orig_df.rename(columns={
        "Категория": "category",
        "Подкатегория": "subcategory",
        "Цена": "price",
        "Дата": "ts"
    }).copy()
    orig['ts'] = pd.to_datetime(orig['ts'], format='%d %B %Y', errors='coerce')
    orig['user_id'] = uid

    key = ['id']

    # 1) Новые строки (id == NaN или не в orig)
    new_rows = new[~new['id'].isin(orig['id'])]
    # 2) Удалённые (были в orig, нет в new)
    deleted_ids = orig.loc[~orig['id'].isin(new['id']), 'id'].tolist()
    # 3) Изменённые: общие id, но есть расхождения
    common_ids = set(orig['id']).intersection(new['id'])
    diffs = []
    for idx in common_ids:
        o = orig.set_index('id').loc[idx]
        n = new.set_index('id').loc[idx]
        if not o[['category','subcategory','price','ts']].equals(n[['category','subcategory','price','ts']]):
            diffs.append(idx)
    updated_rows = new.set_index('id').loc[diffs].reset_index()

    # Запись в БД
    with engine.begin() as conn:
        # удаляем
        if deleted_ids:
            conn.execute(
                text("DELETE FROM purchases WHERE id = ANY(:ids)"),
                {"ids": deleted_ids}
            )
        # обновляем
        for _, row in updated_rows.iterrows():
            conn.execute(
                text("""
                    UPDATE purchases
                       SET category    = :category,
                           subcategory = :subcategory,
                           price       = :price,
                           ts          = :ts
                     WHERE id = :id
                """),
                {
                    "category": row["category"],
                    "subcategory": row["subcategory"],
                    "price": row["price"],
                    "ts": row["ts"],
                    "id": row["id"],
                }
            )
        # вставляем новые
        if not new_rows.empty:
            new_rows.drop(columns=['id']).to_sql(
                "purchases", conn, if_exists="append", index=False
            )

    st.success("✅ Изменения успешно применены в базе!")
    # Обновляем orig_df
    st.session_state.orig_df = edited.copy()
