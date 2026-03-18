# ─────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from google.cloud import bigquery

# ─────────────────────────────────────────────
# PAGE CONFIG — must be first st call
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="GRID-ish-Zero",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.stApp { background-color: #0d1117; color: #e6edf3; }

section[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #21262d;
}

.metric-card {
    background: #161b22; border: 1px solid #21262d;
    border-radius: 10px; padding: 20px 24px; text-align: center;
}
.metric-label {
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    color: #8b949e; margin-bottom: 6px; font-family: 'Space Mono', monospace;
}
.metric-value {
    font-size: 32px; font-weight: 600; color: #e6edf3;
    font-family: 'Space Mono', monospace;
}
.metric-unit { font-size: 13px; color: #8b949e; margin-top: 2px; }
.metric-delta-good { font-size: 12px; color: #3fb950; margin-top: 4px; }
.metric-delta-bad  { font-size: 12px; color: #f85149; margin-top: 4px; }

.section-header {
    font-family: 'Space Mono', monospace; font-size: 11px;
    letter-spacing: 0.15em; text-transform: uppercase; color: #58a6ff;
    border-bottom: 1px solid #21262d; padding-bottom: 8px;
    margin-bottom: 16px; margin-top: 8px;
}

.badge-green { background:#1a3a2a; color:#3fb950; border:1px solid #3fb950;
    border-radius:20px; padding:3px 10px; font-size:11px; font-family:'Space Mono',monospace; }
.badge-amber { background:#3a2a0a; color:#d29922; border:1px solid #d29922;
    border-radius:20px; padding:3px 10px; font-size:11px; font-family:'Space Mono',monospace; }
.badge-red   { background:#3a1a1a; color:#f85149; border:1px solid #f85149;
    border-radius:20px; padding:3px 10px; font-size:11px; font-family:'Space Mono',monospace; }

.js-plotly-plot .plotly .bg { fill: transparent !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTS — matched to your real BQ columns
# ─────────────────────────────────────────────
SOURCES = [
    "nuclear", "fossil_gas", "fossil_hard_coal",
    "wind_offshore", "wind_onshore", "solar",
    "biomass", "hydro_run_of_river_and_poundage",
    "hydro_pumped_storage", "other",
]

SOURCE_COLORS = {
    "nuclear":                         "#f0c040",
    "fossil_gas":                      "#f85149",
    "fossil_hard_coal":                "#8b4513",
    "wind_offshore":                   "#58a6ff",
    "wind_onshore":                    "#79c0ff",
    "solar":                           "#e3b341",
    "biomass":                         "#3fb950",
    "hydro_run_of_river_and_poundage": "#76e3ea",
    "hydro_pumped_storage":            "#40c0c0",
    "other":                           "#8b949e",
}

SOURCE_LABELS = {
    "nuclear":                         "Nuclear",
    "fossil_gas":                      "Fossil Gas",
    "fossil_hard_coal":                "Hard Coal",
    "wind_offshore":                   "Offshore Wind",
    "wind_onshore":                    "Onshore Wind",
    "solar":                           "Solar",
    "biomass":                         "Biomass",
    "hydro_run_of_river_and_poundage": "Hydro RoR",
    "hydro_pumped_storage":            "Hydro Pumped",
    "other":                           "Other",
}

CARBON_FACTORS = {
    "nuclear":                         12,
    "fossil_gas":                      490,
    "fossil_hard_coal":                820,
    "wind_offshore":                   9,
    "wind_onshore":                    11,
    "solar":                           45,
    "biomass":                         230,
    "hydro_run_of_river_and_poundage": 4,
    "hydro_pumped_storage":            4,
    "other":                           300,
}

RENEWABLES = ["wind_offshore", "wind_onshore", "solar",
              "hydro_run_of_river_and_poundage", "hydro_pumped_storage"]

LOCATION_COORDS = {
    "London (default)":   (51.5074, -0.1278),# London - what the model is trainined on currently
    "Edinburgh": (57.0, -3.2),      # Edinburgh - Scottish Highlands wind (models not trained on this)
    "Cardiff":    (51.5, -3.2),      # Cardiff (models not trained on this)
    "Aberystwyth": (52.41, -4.08),    # Mid Wales - wind farms
    "Manchester":    (53.5, -2.2),      # Manchester - Northern England (models not trained on this)
    "Birmingham": (52.5, -1.9),      # Birmingham - (models not trained on this)
    "Aberdeen": (57.1, -2.1),      # North Sea / high wind resource (models not trained on this)
    "Exeter":      (50.7, -3.5),      # Exeter - SW England solar
    "Penzance":    (50.1, -5.5),      # Penzance - Highest sunshine hours in UK
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def intensity_label(val: float):
    if val < 100:   return "Very Low",  "#3fb950", "badge-green"
    elif val < 200: return "Low",       "#79c0ff", "badge-green"
    elif val < 300: return "Moderate",  "#d29922", "badge-amber"
    elif val < 400: return "High",      "#f0883e", "badge-amber"
    else:           return "Very High", "#f85149", "badge-red"

def carbon_from_mix(mix_mw: dict) -> float:
    total = sum(mix_mw.values())
    if total == 0: return 0.0
    return sum(mix_mw[s] * CARBON_FACTORS[s] for s in SOURCES) / total

def make_dummy_forecast(start_date, n_periods=336):
    """Generate 7 days of realistic-looking half-hourly dummy forecast data."""
    times = pd.date_range(start=start_date, periods=n_periods, freq="30min", tz="UTC")
    np.random.seed(42)
    t = np.arange(n_periods)

    # Realistic daily cycles
    solar_cycle = np.maximum(0, np.sin((t % 48 - 12) * np.pi / 24)) * 3000
    demand_cycle = 28000 + 4000 * np.sin((t % 48 - 20) * np.pi / 24)

    df = pd.DataFrame({"datetime": times})
    df["nuclear"]                         = np.clip(5200 + np.random.normal(0, 100, n_periods), 4000, 6000)
    df["fossil_gas"]                      = np.clip(demand_cycle * 0.15 + np.random.normal(0, 300, n_periods), 0, 12000)
    df["fossil_hard_coal"]                = np.clip(200 + np.random.normal(0, 50, n_periods), 0, 800)
    df["wind_offshore"]                   = np.clip(3000 + 1500 * np.sin(t * 0.08) + np.random.normal(0, 400, n_periods), 0, 8000)
    df["wind_onshore"]                    = np.clip(1500 + 800  * np.sin(t * 0.08) + np.random.normal(0, 200, n_periods), 0, 4000)
    df["solar"]                           = np.clip(solar_cycle + np.random.normal(0, 100, n_periods), 0, 8000)
    df["biomass"]                         = np.clip(1800 + np.random.normal(0, 80, n_periods), 0, 3000)
    df["hydro_run_of_river_and_poundage"] = np.clip(350  + np.random.normal(0, 50, n_periods), 0, 1000)
    df["hydro_pumped_storage"]            = np.clip(200  + np.random.normal(0, 80, n_periods), 0, 1500)
    df["other"]                           = np.clip(100  + np.random.normal(0, 20, n_periods), 0, 500)
    df["total_supply_mw"]                 = df[SOURCES].sum(axis=1)
    df["carbon_intensity"]                = (
        df.apply(lambda r: carbon_from_mix({s: r[s] for s in SOURCES}), axis=1)
        + np.random.normal(0, 5, n_periods)
    ).clip(0)
    return df

# ─────────────────────────────────────────────
# BIGQUERY LOADER
# ─────────────────────────────────────────────
@st.cache_data
def load_from_bigquery(start_date: date, end_date: date) -> pd.DataFrame:
    client = bigquery.Client(project="gridzero-489711")
    query = f"""
        SELECT
            datetime,
            biomass, fossil_gas, fossil_hard_coal,
            hydro_pumped_storage, hydro_run_of_river_and_poundage,
            nuclear, other, solar, wind_offshore, wind_onshore,
            totaloutput_mw, carbon_intensity_gco2_kwh
        FROM `gridzero-489711.merged_set.full_feature_engineered_data_test`
        WHERE DATE(datetime) BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY datetime
    """
    df = client.query(query).to_dataframe()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.rename(columns={"carbon_intensity_gco2_kwh": "carbon_intensity",
                             "totaloutput_mw": "total_supply_mw"})
    for col in SOURCES:
        if col in df.columns:
            df[col] = df[col].clip(lower=0)
    return df

# ─────────────────────────────────────────────
# PLOTLY BASE LAYOUT
# ─────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans", color="#8b949e", size=11),
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    xaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False),
    yaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False),
)

# ─────────────────────────────────────────────
# CHART FUNCTIONS
# ─────────────────────────────────────────────
def make_mix_bar(df: pd.DataFrame, title: str = "Generation Mix — 30 min resolution (MW)") -> go.Figure:
    fig = go.Figure()
    for src in SOURCES:
        if src not in df.columns: continue
        fig.add_trace(go.Bar(
            x=df["datetime"], y=df[src],
            name=SOURCE_LABELS[src],
            marker_color=SOURCE_COLORS[src],
            hovertemplate=f"<b>{SOURCE_LABELS[src]}</b><br>%{{y:,.0f}} MW<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        barmode="stack",
        title=dict(text=title, font=dict(size=12, color="#e6edf3")),
        height=340,
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)", font=dict(size=10)))
    return fig


def make_modified_mix_bar(df: pd.DataFrame, hypo_mix: dict) -> go.Figure:
    total_base = df[SOURCES].sum(axis=1)
    mod_df = df.copy()
    hypo_total = sum(hypo_mix.values())
    for src in SOURCES:
        if src not in df.columns: continue
        if hypo_total > 0:
            scale = hypo_mix.get(src, 0) / hypo_total
        else:
            scale = 0
        mod_df[src] = total_base * scale

    fig = go.Figure()
    for src in SOURCES:
        if src not in mod_df.columns: continue
        fig.add_trace(go.Bar(
            x=mod_df["datetime"], y=mod_df[src],
            name=SOURCE_LABELS[src],
            marker_color=SOURCE_COLORS[src],
            hovertemplate=f"<b>{SOURCE_LABELS[src]}</b><br>%{{y:,.0f}} MW<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        barmode="stack",
        height=340,
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)", font=dict(size=10)))
    return fig


def make_carbon_line(df: pd.DataFrame, hypothetical=None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df["carbon_intensity"],
        mode="lines", name="Predicted",
        line=dict(color="#58a6ff", width=2.5),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
        hovertemplate="<b>%{x|%d %b %H:%M}</b><br>%{y:.0f} gCO₂/kWh<extra></extra>",
    ))
    if hypothetical is not None:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=hypothetical,
            mode="lines", name="Modified",
            line=dict(color="#3fb950", width=2, dash="dash"),
            hovertemplate="<b>%{x|%d %b %H:%M}</b><br>%{y:.0f} gCO₂/kWh<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=pd.concat([df["datetime"], df["datetime"][::-1]]),
            y=pd.concat([hypothetical, df["carbon_intensity"][::-1]]),
            fill="toself",
            fillcolor="rgba(63,185,80,0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Delta",
            hoverinfo="skip",
            showlegend=True,
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="Carbon Intensity — Predicted vs Modified (gCO₂/kWh)", font=dict(size=12, color="#e6edf3")),
        height=300,
    )
    fig.update_layout(yaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False, title="gCO₂/kWh"))
    return fig


def make_supply_demand(df: pd.DataFrame, hypo_supply_mw: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df["total_supply_mw"],
        name="Predicted Supply", mode="lines",
        line=dict(color="#58a6ff", width=2.5),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.05)",
        hovertemplate="%{y:,.0f} MW<extra>Predicted Supply</extra>",
    ))
    fig.add_hline(
        y=hypo_supply_mw, line_color="#3fb950", line_dash="dash",
        annotation_text=f"Hypothetical: {hypo_supply_mw:,.0f} MW",
        annotation_font_color="#3fb950", annotation_font_size=10,
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="Supply vs Hypothetical (MW)", font=dict(size=12, color="#e6edf3")),
        height=260,
    )
    fig.update_layout(yaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False, title="MW"))
    return fig


def make_gauge(value: float) -> go.Figure:
    label, color, _ = intensity_label(value)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(suffix=" gCO₂/kWh", font=dict(size=20, color="#e6edf3", family="Space Mono")),
        gauge=dict(
            axis=dict(range=[0, 600], tickcolor="#8b949e", tickfont=dict(size=9, color="#8b949e")),
            bar=dict(color=color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            steps=[
                dict(range=[0,   100], color="#0d1f15"),
                dict(range=[100, 200], color="#0d1a2a"),
                dict(range=[200, 300], color="#2a2000"),
                dict(range=[300, 400], color="#2a1500"),
                dict(range=[400, 600], color="#2a0f0f"),
            ],
            threshold=dict(line=dict(color=color, width=3), thickness=0.85, value=value),
        ),
        title=dict(text=f"<span style='font-size:11px;color:#8b949e;'>{label}</span>"),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#8b949e"),
        height=210, margin=dict(l=20, r=20, t=30, b=0),
    )
    return fig


def make_mix_pie(mix_mw: dict) -> go.Figure:
    labels = [SOURCE_LABELS[s] for s in SOURCES if mix_mw.get(s, 0) > 0]
    values = [mix_mw[s]        for s in SOURCES if mix_mw.get(s, 0) > 0]
    colors = [SOURCE_COLORS[s] for s in SOURCES if mix_mw.get(s, 0) > 0]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#0d1117", width=2)),
        hole=0.5, textinfo="percent",
        textfont=dict(size=10, color="#e6edf3"),
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} MW (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#8b949e"),
        height=230, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    return fig

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("""...""", unsafe_allow_html=True)  # your existing title

    # ADD THIS
    st.markdown('<div class="section-header">Mode</div>', unsafe_allow_html=True)
    app_mode = st.radio("Mode", ["Historical", "Forecast"], horizontal=True, label_visibility="collapsed")

with st.sidebar:
    st.markdown("""
    <div style='padding:12px 0 20px 0;'>
        <div style='font-family:Space Mono,monospace;font-size:16px;color:#58a6ff;font-weight:700;'>⚡ CarbonSim</div>
        <div style='font-size:11px;color:#8b949e;margin-top:4px;'>GB Carbon Intensity Simulator</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-header">Date Range</div>', unsafe_allow_html=True)
    date_mode = st.radio("Mode", ["Single Day", "Date Range"], horizontal=True, label_visibility="collapsed")

    if date_mode == "Single Day":
        sel_date   = st.date_input("Date", value=date(2024, 1, 1),
                        min_value=date(2018, 1, 1), max_value=date(2026, 3, 12),
                        label_visibility="collapsed")
        start_date = sel_date
        end_date   = sel_date
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From", value=date(2024, 1, 1),
                            min_value=date(2018, 1, 1), max_value=date(2026, 3, 12))
        with col2:
            end_date = st.date_input("To", value=date(2024, 1, 7),
                            min_value=date(2018, 1, 1), max_value=date(2026, 3, 12))

    st.markdown('<div class="section-header" style="margin-top:20px;">Location</div>', unsafe_allow_html=True)
    location = st.selectbox("GB Region",
        ["London (default)", "Edinburgh", "Cardiff", "Aberystwyth", "Manchester", "Birmingham", "Aberdeen", "Exeter", "Penzance"],
        label_visibility="collapsed")

    lat, lon = LOCATION_COORDS[location]
    st.markdown(f"""
    <div style='font-size:11px;color:#8b949e;margin-top:4px;margin-bottom:16px;font-family:Space Mono,monospace;'>
        📍 {lat}°N, {lon}°E
    </div>
    """, unsafe_allow_html=True)

    # ── Generation Mix Inputs ──
    st.markdown('<div class="section-header" style="margin-top:4px;">Generation Mix (MW)</div>', unsafe_allow_html=True)

    sidebar_nuclear = st.number_input(
        "⚛  Nuclear (MW)", min_value=0, max_value=9000, value=5200, step=100,
        help="Set nuclear generation in MW")
    sidebar_fossil_gas = st.number_input(
        "🔥 Fossil Gas (MW)", min_value=0, max_value=15000, value=2000, step=100,
        help="Set fossil gas generation in MW")
    sidebar_fossil_hard_coal = st.number_input(
        "⛏  Hard Coal (MW)", min_value=0, max_value=3000, value=300, step=50,
        help="Set hard coal generation in MW")
    sidebar_wind_offshore = st.number_input(
        "💨 Offshore Wind (MW)", min_value=0, max_value=10000, value=2800, step=100,
        help="Set offshore wind generation in MW")
    sidebar_wind_onshore = st.number_input(
        "🌬  Onshore Wind (MW)", min_value=0, max_value=6000, value=1400, step=100,
        help="Set onshore wind generation in MW")
    sidebar_solar = st.number_input(
        "☀  Solar (MW)", min_value=0, max_value=8000, value=1500, step=100,
        help="Set solar generation in MW")
    sidebar_biomass = st.number_input(
        "🌿 Biomass (MW)", min_value=0, max_value=4000, value=1800, step=50,
        help="Set biomass generation in MW")
    sidebar_hydro_ror = st.number_input(
        "💧 Hydro RoR (MW)", min_value=0, max_value=2000, value=350, step=50,
        help="Set hydro run of river generation in MW")
    sidebar_hydro_pumped = st.number_input(
        "🔋 Hydro Pumped (MW)", min_value=0, max_value=3000, value=200, step=50,
        help="Set hydro pumped storage generation in MW")
    sidebar_other = st.number_input(
        "➕ Other (MW)", min_value=0, max_value=5000, value=100, step=50,
        help="Set other generation in MW")
    sidebar_total = st.number_input(
        "📊 Total Generation (MW)", min_value=5000, max_value=70000, value=36000, step=500,
        help="Set total grid generation in MW")

    st.markdown('<div class="section-header" style="margin-top:20px;">Status</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style='font-size:11px;color:#8b949e;line-height:1.9;'>
        <span style='color:#3fb950;'>◉</span> Data: <span style='color:#3fb950;'>BigQuery</span><br>
        <span style='color:#f0883e;'>⚠</span> Models: <span style='color:#d29922;'>Not connected</span><br>
        <span style='color:#8b949e;'>○</span> Weather API: <span style='color:#8b949e;'>Not connected</span>
    </div>
    """, unsafe_allow_html=True)

# sidebar mix dict — used as base for hypothetical simulator
sidebar_mix = {
    "nuclear":                         sidebar_nuclear,
    "fossil_gas":                      sidebar_fossil_gas,
    "fossil_hard_coal":                sidebar_fossil_hard_coal,
    "wind_offshore":                   sidebar_wind_offshore,
    "wind_onshore":                    sidebar_wind_onshore,
    "solar":                           sidebar_solar,
    "biomass":                         sidebar_biomass,
    "hydro_run_of_river_and_poundage": sidebar_hydro_ror,
    "hydro_pumped_storage":            sidebar_hydro_pumped,
    "other":                           sidebar_other,
}

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
if app_mode == "Historical":
    with st.spinner("Loading data from BigQuery..."):
        try:
            df = load_from_bigquery(start_date, end_date)
            data_ok = len(df) > 0
        except Exception as e:
            st.error(f"BigQuery error: {e}")
            st.stop()
    if not data_ok:
        st.warning(f"No data found for {start_date} → {end_date}.")
        st.stop()
else:
    # FORECAST MODE — dummy data for now, replace with model output later
    df = make_dummy_forecast(datetime.now())
    data_ok = True
    st.info("⚡ Forecast mode: showing dummy predictions — model integration coming soon.", icon="🔮")
# ─────────────────────────────────────────────
# COMPUTED SUMMARY VALUES
# ─────────────────────────────────────────────
avg_carbon  = df["carbon_intensity"].mean()
peak_carbon = df["carbon_intensity"].max()
min_carbon  = df["carbon_intensity"].min()
avg_supply  = df["total_supply_mw"].mean()

renew_cols_present = [c for c in RENEWABLES if c in df.columns]
renewables_share = (
    df[renew_cols_present].sum(axis=1) / df["total_supply_mw"] * 100
).mean()

label_str, label_color, badge_cls = intensity_label(avg_carbon)

base_avg   = {s: float(df[s].mean()) for s in SOURCES if s in df.columns}
total_base = sum(base_avg.values())

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
date_range_str = (
    start_date.strftime("%d %b %Y")
    if start_date == end_date
    else f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"
)

st.markdown(f"""
<div style='display:flex;align-items:center;justify-content:space-between;
            padding:0 0 20px 0;border-bottom:1px solid #21262d;margin-bottom:24px;'>
    <div>
        <div style='font-family:Space Mono,monospace;font-size:22px;color:#e6edf3;font-weight:700;'>
            GRID-ish-Zero
        </div>
        <div style='font-size:13px;color:#8b949e;margin-top:4px;'>
            {location} · {date_range_str} · {len(df):,} half-hourly periods
        </div>
    </div>
    <div style='text-align:right;'>
        <span class='{badge_cls}'>{label_str}</span>
        <div style='font-size:11px;color:#8b949e;margin-top:6px;font-family:Space Mono,monospace;'>
            avg {avg_carbon:.0f} gCO₂/kWh
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# METRICS ROW
# ─────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
for col, lbl, val, unit, good, bad in [
    (c1, "Avg Carbon Intensity", f"{avg_carbon:.0f}",    "gCO₂/kWh", None, None),
    (c2, "Peak Carbon Intensity", f"{peak_carbon:.0f}",  "gCO₂/kWh", None, None),
    (c3, "Min Carbon Intensity",  f"{min_carbon:.0f}",   "gCO₂/kWh", True, None),
    (c4, "Avg Supply",            f"{avg_supply/1000:.1f}", "GW",     None, None),
    (c5, "Renewables Share",      f"{renewables_share:.0f}", "%",     True, None),
]:
    delta = ""
    if good: delta = '<div class="metric-delta-good">▲ Favourable</div>'
    if bad:  delta = '<div class="metric-delta-bad">▼ Watch</div>'
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-value">{val}</div>
            <div class="metric-unit">{unit}</div>
            {delta}
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECTION 1 — PREDICTED GENERATION MIX
# ─────────────────────────────────────────────
left, right = st.columns([2, 1])
with left:
    st.markdown('<div class="section-header">Predicted Generation Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_bar(df), use_container_width=True, config={"displayModeBar": False})
with right:
    st.markdown('<div class="section-header">Average Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_pie(base_avg), use_container_width=True, config={"displayModeBar": False})
    st.plotly_chart(make_gauge(avg_carbon), use_container_width=True, config={"displayModeBar": False})

# ─────────────────────────────────────────────
# SECTION 2 — PREDICTED CARBON INTENSITY
# ─────────────────────────────────────────────
st.markdown('<div class="section-header">Predicted Carbon Intensity</div>', unsafe_allow_html=True)
st.plotly_chart(make_carbon_line(df), use_container_width=True, config={"displayModeBar": False})

# ─────────────────────────────────────────────
# HYPOTHETICAL SCENARIO SIMULATOR
# ─────────────────────────────────────────────
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='background:#161b22;border:1px solid #21262d;border-radius:10px;
            padding:20px 24px;margin-bottom:4px;'>
    <div style='font-family:Space Mono,monospace;font-size:11px;color:#58a6ff;
                letter-spacing:0.15em;text-transform:uppercase;margin-bottom:4px;'>
        Hypothetical Scenario Simulator
    </div>
    <div style='font-size:12px;color:#8b949e;'>
        Adjust the sliders to change the energy mix proportions.
        Total supply is kept fixed — reducing one source scales others up.
        See how this affects carbon intensity and storage requirements.
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("⚙  Configure Hypothetical Mix", expanded=True):
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style='font-size:11px;color:#8b949e;margin-bottom:12px;'>
        Sliders show % of total generation. Total is kept at the predicted average.
    </div>""", unsafe_allow_html=True)

    base_pct = {s: (base_avg[s] / total_base * 100) if total_base > 0 else 0 for s in SOURCES if s in base_avg}

    slider_cfg = [
        ("nuclear",                         "⚛  Nuclear",       0, 40),
        ("fossil_gas",                      "🔥 Fossil Gas",     0, 60),
        ("fossil_hard_coal",                "⛏  Hard Coal",      0, 20),
        ("wind_offshore",                   "💨 Offshore Wind",  0, 50),
        ("wind_onshore",                    "🌬  Onshore Wind",  0, 30),
        ("solar",                           "☀  Solar",          0, 40),
        ("biomass",                         "🌿 Biomass",         0, 20),
        ("hydro_run_of_river_and_poundage", "💧 Hydro RoR",      0, 15),
        ("hydro_pumped_storage",            "🔋 Hydro Pumped",   0, 15),
        ("other",                           "➕ Other",           0, 10),
    ]

    hypo_pct = {}
    scol1, scol2 = st.columns(2)
    for i, (key, lbl, mn, mx) in enumerate(slider_cfg):
        col = scol1 if i % 2 == 0 else scol2
        with col:
            hypo_pct[key] = st.slider(
                lbl,
                min_value=float(mn), max_value=float(mx),
                value=round(base_pct.get(key, 0), 1),
                step=0.5,
                format="%.1f%%",
                help=f"Predicted avg: {base_pct.get(key, 0):.1f}%",
            )

    pct_total = sum(hypo_pct.values())
    if pct_total > 0:
        hypo_mix = {s: (hypo_pct[s] / pct_total) * total_base for s in SOURCES if s in hypo_pct}
    else:
        hypo_mix = {s: 0 for s in SOURCES}

    hypo_total  = sum(hypo_mix.values())
    hypo_carbon = carbon_from_mix(hypo_mix)

    shortfall_mw  = avg_supply - hypo_total
    n_hours       = len(df) * 0.5
    shortfall_mwh = abs(shortfall_mw) * n_hours

    h_label, h_color, h_badge = intensity_label(hypo_carbon)
    delta_pct = ((hypo_carbon - avg_carbon) / avg_carbon * 100) if avg_carbon else 0

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Modified Carbon Intensity</div>
            <div class="metric-value" style="color:{h_color};">{hypo_carbon:.0f}</div>
            <div class="metric-unit">gCO₂/kWh</div>
        </div>""", unsafe_allow_html=True)
    with rc2:
        arrow = "▲" if delta_pct > 0 else "▼"
        dcls  = "metric-delta-bad" if delta_pct > 0 else "metric-delta-good"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">vs Predicted</div>
            <div class="metric-value">{abs(delta_pct):.1f}%</div>
            <div class="{dcls}">{arrow} {"Higher" if delta_pct > 0 else "Lower"}</div>
        </div>""", unsafe_allow_html=True)
    with rc3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Modified Total Supply</div>
            <div class="metric-value">{hypo_total/1000:.1f}</div>
            <div class="metric-unit">GW avg</div>
        </div>""", unsafe_allow_html=True)
    with rc4:
        sf_color = "#f85149" if shortfall_mw > 0 else "#3fb950"
        sf_label = "Storage Required" if shortfall_mw > 0 else "Surplus Energy"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{sf_label}</div>
            <div class="metric-value" style="color:{sf_color};">{shortfall_mwh/1000:.1f}</div>
            <div class="metric-unit">GWh {"needed" if shortfall_mw > 0 else "available"}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECTION 3 — MODIFIED GENERATION MIX
# ─────────────────────────────────────────────
mod_left, mod_right = st.columns([2, 1])
with mod_left:
    st.markdown('<div class="section-header">Modified Generation Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_modified_mix_bar(df, hypo_mix), use_container_width=True, config={"displayModeBar": False})
with mod_right:
    st.markdown('<div class="section-header">Modified Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_pie(hypo_mix), use_container_width=True, config={"displayModeBar": False})
    st.plotly_chart(make_gauge(hypo_carbon), use_container_width=True, config={"displayModeBar": False})

# ─────────────────────────────────────────────
# SECTION 4 — CARBON INTENSITY: PREDICTED vs MODIFIED + DELTA
# ─────────────────────────────────────────────
hypo_carbon_series = pd.Series([hypo_carbon] * len(df))

st.markdown('<div class="section-header">Carbon Intensity — Predicted vs Modified</div>', unsafe_allow_html=True)
st.plotly_chart(
    make_carbon_line(df, hypothetical=hypo_carbon_series),
    use_container_width=True, config={"displayModeBar": False}
)

# ─────────────────────────────────────────────
# SUPPLY VS HYPOTHETICAL
# ─────────────────────────────────────────────
st.markdown('<div class="section-header">Supply vs Hypothetical</div>', unsafe_allow_html=True)
st.plotly_chart(
    make_supply_demand(df, hypo_total),
    use_container_width=True, config={"displayModeBar": False}
)

# ─────────────────────────────────────────────
# RAW DATA
# ─────────────────────────────────────────────
with st.expander("📋  Raw Data"):
    display_df = df.copy()
    display_df["datetime"] = display_df["datetime"].dt.strftime("%Y-%m-%d %H:%M")
    rename_map = {s: SOURCE_LABELS[s] for s in SOURCES if s in display_df.columns}
    rename_map.update({"carbon_intensity": "Carbon Intensity (gCO₂/kWh)", "total_supply_mw": "Total Supply (MW)"})
    display_df = display_df.rename(columns=rename_map)
    show_cols = ["datetime"] + [SOURCE_LABELS[s] for s in SOURCES if SOURCE_LABELS[s] in display_df.columns] \
                + ["Carbon Intensity (gCO₂/kWh)", "Total Supply (MW)"]
    st.dataframe(display_df[[c for c in show_cols if c in display_df.columns]].round(1),
                 use_container_width=True, height=300, hide_index=True)

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
#st.markdown("""
#<div style='border-top:1px solid #21262d;margin-top:32px;padding-top:16px;
#           font-size:11px;color:#484f58;font-family:Space Mono,monospace;
#            display:flex;justify-content:space-between;'>
#    <span>GRID-ish-Zero · Historical data mode</span>
#    <span>Models: LSTM (Keras) + XGBoost (JSON) · Weather: Open-Meteo · Data: Elexon / BigQuery</span>
#</div>
#""", unsafe_allow_html=True)

st.markdown("---")
st.markdown("""
<div style='text-align:center; font-size:0.9rem; color:#6c757d; line-height:1.6;'>
<strong>Le Wagon Data Science & AI Bootcamp | March 2026</strong><br>
<strong>Team GitHub:</strong>
<a href='https://github.com/mlbh' target='_blank'>Madeleine</a> |
<a href='https://github.com/josephmac02' target='_blank'>Joseph</a> |
<a href='https://github.com/LaSemaj' target='_blank'>James</a> |
<a href='https://github.com/dd4real2k' target='_blank'>Daniel</a>
</div>
""", unsafe_allow_html=True)
