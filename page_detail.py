import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

@st.cache_data
def get_data():
    df = pd.DataFrame({
        "region": np.random.choice(["A", "B", "C"], size=1000),
        "value": np.random.randn(1000),
    })
    return df

df = get_data()
df_group = (
    df.groupby("region")["value"]
      .sum()
      .reset_index()  # 👉 важно! чтобы region стала колонкой
)

sel = alt.selection_single(fields=["region"], empty="all")

base = (
    alt.Chart(df_group)
    .mark_bar()
    .encode(
        x="region:N",  # явно указываем nominal
        y="value:Q",   # quantitative
        color=alt.condition(sel, alt.Color("region:N"), alt.value("lightgray"))
    )
    .add_selection(sel)
)

details = (
    alt.Chart(df)
    .mark_point()
    .encode(
        x="value:Q",
        y="count()",
    )
    .transform_filter(sel)
)

st.altair_chart(base & details, use_container_width=True)
