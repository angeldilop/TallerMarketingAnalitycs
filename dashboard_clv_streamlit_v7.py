# dashboard_clv_streamlit_v7.py
# -------------------------------------------------------------
# Versión simple (Plotly):
#  - Chart 1: Clientes por Estado (barras) + CLV promedio (línea, eje derecho)
#  - Chart 2: Clientes por Canal de Venta (barras) con color = Género (H/M)
#  - Filtros: Estado, Respuesta, Cobertura, Género
#  - Parsing CLV sencillo y robusto
# -------------------------------------------------------------
# Ejecuta:
#   py -m streamlit run dashboard_clv_streamlit_v7.py --server.port=8530
# -------------------------------------------------------------

import io
import re
import numpy as np
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Storytelling CLV (Simple)", layout="wide")

# --------------- utilidades simples -----------------
def find_col(df, candidates):
    cols = [re.sub(r"[^a-z0-9]+", "_", c.lower().strip()) for c in df.columns]
    for i, c in enumerate(cols):
        if any(tok in c for tok in candidates):
            return df.columns[i]
    return None

def load_any(file):
    if file is None:
        return None
    name = getattr(file, "name", "uploaded")
    if name.lower().endswith(".csv"):
        data = file.read()
        sample = data[:2048].decode("utf-8", errors="ignore")
        sep = ";" if sample.count(";") > sample.count(",") else ","
        return pd.read_csv(io.BytesIO(data), sep=sep)
    return pd.read_excel(file)

def parse_clv(series: pd.Series) -> pd.Series:
    """Regla simple:
    - Si el valor tiene varios puntos y NO tiene comas (ej. '2.763.519.279')
      => quitar todo lo no dígito y dividir entre 1e6  -> 2763.519279
    - En caso contrario: quitar símbolos, quitar comas de miles, coma como decimal.
    """
    s = series.astype(str).str.strip()
    multi_dot = s.str.contains(r"\.") & ~s.str.contains(",")
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    if multi_dot.any():
        digits = s[multi_dot].str.replace(r"\D", "", regex=True)
        out.loc[multi_dot] = pd.to_numeric(digits, errors="coerce") / 1_000_000
    rest = ~multi_dot
    if rest.any():
        t = s[rest].str.replace(r"[^0-9,.\-]", "", regex=True)
        both = t.str.contains(",") & t.str.contains(r"\.")
        t = t.where(~both, t.str.replace(",", "", regex=False))          # coma de miles
        t = t.str.replace(r"(?<=\d),(?=\d{3}(\D|$))", "", regex=True)    # 12,345 -> 12345
        t = t.str.replace(",", ".", regex=False)                         # coma decimal -> punto
        out.loc[rest] = pd.to_numeric(t, errors="coerce")
    return out

# ------------------- app ----------------------------
st.title("📊 Storytelling CLV (versión simple)")

up = st.sidebar.file_uploader("CSV o Excel", type=["csv","xlsx","xls"])
df = load_any(up)
if df is None:
    st.info("Sube un archivo para comenzar.")
    st.stop()

# detectar columnas
col_state   = find_col(df, ["state","estado"])
col_clv     = find_col(df, ["customer_lifetime_value","clv","lifetime"])
col_resp    = find_col(df, ["response","respondio","renewal"])
col_cov     = find_col(df, ["coverage","cobertura"])
col_gender  = find_col(df, ["gender","genero"])
col_sales   = find_col(df, ["sales_channel","channel","canal"])  # NUEVO

# parsear CLV
if col_clv:
    df[col_clv] = parse_clv(df[col_clv])

# filtros
st.sidebar.subheader("Filtros")
states = st.sidebar.multiselect("Estado", sorted(df[col_state].dropna().unique().tolist())) if col_state else []
resp   = st.sidebar.multiselect("Respuesta", sorted(df[col_resp].dropna().unique().tolist())) if col_resp else []
cov    = st.sidebar.multiselect("Cobertura", sorted(df[col_cov].dropna().unique().tolist())) if col_cov else []
gnd    = st.sidebar.multiselect("Género", sorted(df[col_gender].dropna().unique().tolist())) if col_gender else []

mask = pd.Series(True, index=df.index)
if states and col_state: mask &= df[col_state].isin(states)
if resp   and col_resp:  mask &= df[col_resp].isin(resp)
if cov    and col_cov:   mask &= df[col_cov].isin(cov)
if gnd    and col_gender:mask &= df[col_gender].isin(gnd)
df_f = df[mask].copy()

# ---------------- Chart 1 ----------------
st.subheader("1) Clientes por Estado + CLV promedio (eje derecho, 2 decimales)")

if col_state is None:
    st.warning("No se encontró la columna de Estado.")
else:
    # datos
    cnt = df_f.groupby(col_state).size().reset_index(name="Clientes").sort_values("Clientes", ascending=False)
    if col_clv:
        clv = df_f.groupby(col_state)[col_clv].mean().reset_index(name="CLV promedio")
        base = cnt.merge(clv, on=col_state, how="left")
    else:
        base = cnt.copy(); base["CLV promedio"] = np.nan
    base = base.rename(columns={col_state:"Estado"})

    # límites limpios para eje derecho
    if base["CLV promedio"].notna().any():
        mmin = float(base["CLV promedio"].min())
        mmax = float(base["CLV promedio"].max())
        pad = (mmax - mmin) * 0.05 if mmax > mmin else 1.0
        y2_range = [mmin - pad, mmax + pad]
    else:
        y2_range = None

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # barras (clientes)
    fig.add_trace(
        go.Bar(
            x=base["Estado"],
            y=base["Clientes"],
            name="Clientes",
            text=[f"{v:,d}" for v in base["Clientes"]],
            textposition="outside",
            marker_color="#1f77b4"
        ),
        secondary_y=False
    )

    # línea (CLV promedio)
    fig.add_trace(
        go.Scatter(
            x=base["Estado"],
            y=base["CLV promedio"],
            name="CLV promedio",
            mode="lines+markers",
            marker=dict(size=6, color="#F58518"),
            line=dict(width=2, color="#F58518"),
            hovertemplate="Estado: %{x}<br>CLV promedio: %{y:.2f}<extra></extra>"
        ),
        secondary_y=True
    )

    fig.update_layout(
        height=520,
        margin=dict(l=40, r=40, t=30, b=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        bargap=0.25
    )

    # eje izquierdo (clientes)
    fig.update_yaxes(
        title_text="Clientes",
        showgrid=True,
        tickformat=",d",
        secondary_y=False
    )
    # eje derecho (CLV) — limpio, 2 decimales
    fig.update_yaxes(
        title_text="CLV promedio",
        showgrid=False,
        tickformat=".2f",
        range=y2_range,
        secondary_y=True
    )
    fig.update_xaxes(title_text="Estado")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Ver tabla base (grafico 1)"):
        st.dataframe(base.style.format({"Clientes": "{:,d}", "CLV promedio": "{:,.2f}"}), use_container_width=True)

# ---------------- Chart 2 ----------------
st.subheader("2) Clientes por Canal de Venta (barras) con Género")

if (col_sales is None) or (col_gender is None):
    st.info("No se encontraron las columnas de Canal de Venta y/o Género.")
else:
    # Normalizamos etiquetas de género a 'Male'/'Female' o similar si vienen con espacios/upper
    df_f[col_gender] = df_f[col_gender].astype(str).str.strip().str.title()  # 'male' -> 'Male'

    df_c2 = (df_f
             .groupby([col_sales, col_gender])
             .size()
             .reset_index(name="Clientes"))

    # Orden de canales por total (desc)
    order_channels = (df_c2.groupby(col_sales)["Clientes"]
                      .sum()
                      .sort_values(ascending=False)
                      .index.tolist())

    fig2 = px.bar(
        df_c2,
        x=col_sales,
        y="Clientes",
        color=col_gender,
        category_orders={col_sales: order_channels},
        barmode="group",
        text="Clientes",
        color_discrete_sequence=["#4E79A7", "#F28E2B"]  # Hombre, Mujer (si aplica ese orden)
    )
    fig2.update_traces(textposition="outside")
    fig2.update_layout(
        height=520,
        margin=dict(l=40, r=40, t=30, b=60),
        legend_title_text="Género",
        xaxis_title="Canal de Venta",
        yaxis_title="Clientes"
    )
    fig2.update_yaxes(tickformat=",d")

    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Ver tabla base (grafico 2)"):
        st.dataframe(df_c2.sort_values(["Clientes"], ascending=False).style.format({"Clientes":"{:,.0f}"}),
                     use_container_width=True)
