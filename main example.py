from dash import Dash, dash_table, dcc, html, Input, Output, State
import pandas as pd, sqlalchemy

engine = sqlalchemy.create_engine(...)
app = Dash(__name__)
app.layout = html.Div([
  dcc.Input(id="userid", type="text", placeholder="User ID"),
  html.Button("Load", id="load-btn"),
  dash_table.DataTable(id="table", columns=[], data=[], editable=True),
  html.Button("Save", id="save-btn"),
  html.Div(id="status")
])

@app.callback(
  [Output("table", "columns"), Output("table", "data")],
  Input("load-btn", "n_clicks"),
  State("userid", "value")
)
def load(n, uid):
  df = pd.read_sql(... WHERE user_id=uid)
  return [{"name":i,"id":i} for i in df.columns], df.to_dict("records")

@app.callback(
  Output("status", "children"),
  Input("save-btn", "n_clicks"),
  State("table", "data")
)
def save(n, rows):
  if n:
    df = pd.DataFrame(rows)
    df.to_sql(..., if_exists="replace")
    return "Данные сохранены"
