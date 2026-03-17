import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import sys
import os

path_to_scripts = os.path.join('..', '..', 'python_scripts')
sys.path.append(path_to_scripts)

%load_ext autoreload

from datetime import datetime, timedelta, date
from data_to_bigquery import load_from_bigquery

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

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Dark background */
.stApp {
    background-color: #0d1117;
    color: #e6edf3;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #21262d;
}

/* Metric cards */
.metric-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 20px 24px;
    text-align: center;
}
.metric-label {
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #8b949e;
    margin-bottom: 6px;
    font-family: 'Space Mono', monospace;
}
.metric-value {
    font-size: 32px;
    font-weight: 600;
    color: #e6edf3;
    font-family: 'Space Mono', monospace;
}
.metric-unit {
    font-size: 13px;
    color: #8b949e;
    margin-top: 2px;
}
.metric-delta-good {
    font-size: 12px;
    color: #3fb950;
    margin-top: 4px;
}
.metric-delta-bad {
    font-size: 12px;
    color: #f85149;
    margin-top: 4px;
}

/* Section headers */
.section-header {
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #58a6ff;
    border-bottom: 1px solid #21262d;
    padding-bottom: 8px;
    margin-bottom: 16px;
    margin-top: 8px;
}

/* Gauge label */
.gauge-label {
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    color: #8b949e;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

/* Scenario badge */
.badge-green { background: #1a3a2a; color: #3fb950; border: 1px solid #3fb950;
    border-radius: 20px; padding: 3px 10px; font-size: 11px; font-family: 'Space Mono', monospace; }
.badge-amber { background: #3a2a0a; color: #d29922; border: 1px solid #d29922;
    border-radius: 20px; padding: 3px 10px; font-size: 11px; font-family: 'Space Mono', monospace; }
.badge-red { background: #3a1a1a; color: #f85149; border: 1px solid #f85149;
    border-radius: 20px; padding: 3px 10px; font-size: 11px; font-family: 'Space Mono', monospace; }

/* Slider labels */
.slider-row-label {
    font-size: 12px;
    color: #8b949e;
    display: flex;
    justify-content: space-between;
}

/* Plotly chart bg fix */
.js-plotly-plot .plotly .bg {
    fill: transparent !important;
}

/* Hide Streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MOCK DATA HELPERS
# ─────────────────────────────────────────────
SOURCES = ["nuclear", "gas", "wind_offshore", "wind_onshore", "solar", "biomass", "hydro"]
SOURCE_COLORS = {
    "nuclear":      "#f0c040",
    "gas":          "#f85149",
    "wind_offshore":"#58a6ff",
    "wind_onshore": "#79c0ff",
    "solar":        "#e3b341",
    "biomass":      "#3fb950",
    "hydro":        "#76e3ea",
}
SOURCE_LABELS = {
    "nuclear":      "Nuclear",
    "gas":          "Gas",
    "wind_offshore":"Offshore Wind",
    "wind_onshore": "Onshore Wind",
    "solar":        "Solar",
    "biomass":      "Biomass",
    "hydro":        "Hydro",
}

CARBON_FACTORS = {   # gCO2/kWh rough values
    "nuclear":       12,
    "gas":          490,
    "wind_offshore":  9,
    "wind_onshore":  11,
    "solar":         45,
    "biomass":      230,
    "hydro":          4,
}


def mock_hourly_generation(start_dt: datetime, n_hours: int = 24) -> pd.DataFrame:
    """Returns a DataFrame of hourly mocked generation (MW) + carbon intensity."""
    np.random.seed(int(start_dt.timestamp()) % 10000)
    hours = pd.date_range(start_dt, periods=n_hours, freq="h")
    h = hours.hour

    # Base profiles with daily shape
    solar_curve  = np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)
    wind_curve   = 0.6 + 0.4 * np.random.rand(n_hours)
    demand_curve = 0.7 + 0.3 * np.sin(np.pi * (h - 7) / 13) + 0.05 * np.random.randn(n_hours)

    data = {
        "datetime":      hours,
        "nuclear":       np.full(n_hours, 5200) + np.random.randn(n_hours) * 50,
        "gas":           2000 * demand_curve + np.random.randn(n_hours) * 200,
        "wind_offshore": 2800 * wind_curve + np.random.randn(n_hours) * 100,
        "wind_onshore":  1400 * wind_curve * 0.8 + np.random.randn(n_hours) * 80,
        "solar":         3000 * solar_curve + np.random.randn(n_hours) * 50,
        "biomass":       np.full(n_hours, 1800) + np.random.randn(n_hours) * 30,
        "hydro":         np.full(n_hours, 350) + np.random.randn(n_hours) * 20,
    }

    df = pd.DataFrame(data)
    for col in SOURCES:
        df[col] = df[col].clip(lower=0)

    # Total supply
    df["total_supply_mw"] = df[SOURCES].sum(axis=1)

    # Carbon intensity (MW-weighted average)
    df["carbon_intensity"] = sum(
        df[s] * CARBON_FACTORS[s] for s in SOURCES
    ) / df["total_supply_mw"]

    return df


def carbon_from_mix(mix_mw: dict) -> float:
    """Calculate carbon intensity from a generation mix dict (MW)."""
    total = sum(mix_mw.values())
    if total == 0:
        return 0.0
    return sum(mix_mw[s] * CARBON_FACTORS[s] for s in SOURCES) / total


def intensity_label(val: float):
    if val < 100:
        return "Very Low", "#3fb950", "badge-green"
    elif val < 200:
        return "Low", "#79c0ff", "badge-green"
    elif val < 300:
        return "Moderate", "#d29922", "badge-amber"
    elif val < 400:
        return "High", "#f0883e", "badge-amber"
    else:
        return "Very High", "#f85149", "badge-red"


# ─────────────────────────────────────────────
# CHART HELPERS
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


def make_mix_bar(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for src in SOURCES:
        fig.add_trace(go.Bar(
            x=df["datetime"], y=df[src],
            name=SOURCE_LABELS[src],
            marker_color=SOURCE_COLORS[src],
            hovertemplate=f"<b>{SOURCE_LABELS[src]}</b><br>%{{y:,.0f}} MW<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        barmode="stack",
        title=dict(text="Generation Mix (MW)", font=dict(size=12, color="#e6edf3")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        height=320,
    )
    return fig


def make_carbon_line(df: pd.DataFrame, hypothetical=None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df["carbon_intensity"],
        mode="lines", name="Predicted",
        line=dict(color="#58a6ff", width=2.5),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
        hovertemplate="<b>%{x|%H:%M}</b><br>%{y:.0f} gCO₂/kWh<extra></extra>",
    ))
    if hypothetical is not None:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=hypothetical,
            mode="lines", name="Hypothetical",
            line=dict(color="#3fb950", width=2, dash="dash"),
            hovertemplate="<b>%{x|%H:%M}</b><br>%{y:.0f} gCO₂/kWh<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="Carbon Intensity (gCO₂/kWh)", font=dict(size=12, color="#e6edf3")),
        height=240,
        yaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False, title="gCO₂/kWh"),
    )
    return fig


def make_supply_demand(df: pd.DataFrame, demand_mw: float, hypo_supply: pd.Series = None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df["total_supply_mw"],
        name="Predicted Supply", mode="lines",
        line=dict(color="#58a6ff", width=2.5),
        hovertemplate="%{y:,.0f} MW<extra>Predicted Supply</extra>",
    ))
    if hypo_supply is not None:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=hypo_supply,
            name="Hypothetical Supply", mode="lines",
            line=dict(color="#3fb950", width=2, dash="dash"),
            hovertemplate="%{y:,.0f} MW<extra>Hypo Supply</extra>",
        ))
    fig.add_hline(
        y=demand_mw, line_color="#d29922", line_dash="dot",
        annotation_text=f"Demand: {demand_mw:,.0f} MW",
        annotation_font_color="#d29922", annotation_font_size=10,
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="Supply vs Demand (MW)", font=dict(size=12, color="#e6edf3")),
        height=260,
        yaxis=dict(gridcolor="#21262d", linecolor="#21262d", zeroline=False, title="MW"),
    )
    return fig


def make_gauge(value: float) -> go.Figure:
    label, color, _ = intensity_label(value)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(suffix=" gCO₂/kWh", font=dict(size=22, color="#e6edf3", family="Space Mono")),
        gauge=dict(
            axis=dict(range=[0, 600], tickcolor="#8b949e", tickfont=dict(size=9, color="#8b949e")),
            bar=dict(color=color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            steps=[
                dict(range=[0, 100],   color="#0d1f15"),
                dict(range=[100, 200], color="#0d1a2a"),
                dict(range=[200, 300], color="#2a2000"),
                dict(range=[300, 400], color="#2a1500"),
                dict(range=[400, 600], color="#2a0f0f"),
            ],
            threshold=dict(line=dict(color=color, width=3), thickness=0.85, value=value),
        ),
        title=dict(text=f"<span style='font-size:11px;color:#8b949e;'>{label}</span>", font=dict(size=11)),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#8b949e"),
        height=200,
        margin=dict(l=20, r=20, t=30, b=0),
    )
    return fig


def make_mix_pie(mix_mw: dict) -> go.Figure:
    labels = [SOURCE_LABELS[s] for s in SOURCES if mix_mw.get(s, 0) > 0]
    values = [mix_mw[s] for s in SOURCES if mix_mw.get(s, 0) > 0]
    colors = [SOURCE_COLORS[s] for s in SOURCES if mix_mw.get(s, 0) > 0]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#0d1117", width=2)),
        hole=0.5,
        textinfo="percent",
        textfont=dict(size=10, color="#e6edf3"),
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} MW (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#8b949e"),
        height=220,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )
    return fig


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
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
        sel_date = st.date_input("Date", value=date.today(), label_visibility="collapsed")
        start_dt = datetime.combine(sel_date, datetime.min.time())
        n_hours  = 24
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("From", value=date.today(), label_visibility="visible")
        with col2:
            end_date = st.date_input("To", value=date.today() + timedelta(days=7), label_visibility="visible")
        start_dt = datetime.combine(start_date, datetime.min.time())
        n_hours  = max(1, int((datetime.combine(end_date, datetime.min.time()) - start_dt).total_seconds() / 3600)) + 24
        n_hours  = min(n_hours, 24 * 30)  # cap at 30 days

    st.markdown('<div class="section-header" style="margin-top:20px;">Location</div>', unsafe_allow_html=True)
    location = st.selectbox(
        "GB Region",
        ["All GB", "England", "Scotland", "Wales", "North", "South", "Midlands"],
        label_visibility="collapsed"
    )

    st.markdown('<div class="section-header" style="margin-top:20px;">Generation Mix</div>', unsafe_allow_html=True)
    biomass_mw = st.number_input(
        "Biomass (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total for biomass generation as a proportion of the total generation"
    )
    fossil_gas_mw = st.number_input(
        "Fossil Gas (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total for fossil gas generation as a proportion of the total generation."
    )
    fossil_hard_coal_mw = st.number_input(
        "Fossil Hard Coal (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total for fossil hard coal generation as a proportion of the total generation."
    )
    hydro_pumped_storage_mw = st.number_input(
        "Hydro Pumped Storage (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total for hydro pumped storage generation as a proportion of the total generation."
    )
    hydro_run_of_river_and_poundage_mw = st.number_input(
        "Hydro Run of River and Poundage", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total for hydro run of river and poundage generation as a proportion of the total generation."
    )

    nuclear_mw = st.number_input(
        "Nuclear (MW)", min_value=0, max_value=9000,
        value=5200, step=100, label_visibility="visible",
        help="Set total for nuclear generation as a proportion of the total generation."
    )
    other_mw = st.number_input(
        "Other (MW)", min_value=0, max_value=5000,
        value=100, step=50, label_visibility="visible",
        help="Set total for other generation sources as a proportion of the total generation."
    )
    wind_offshore_mw = st.number_input(
        "Wind Offshore (MW)", min_value=0, max_value=10000,
        value=2800, step=100, label_visibility="visible",
        help="Set total for offshore wind generation as a proportion of the total generation."
    )
    wind_onshore_mw = st.number_input(
        "Wind Onshore (MW)", min_value=0, max_value=6000,
        value=1400, step=100, label_visibility="visible",
        help="Set total for onshore wind generation as a proportion of the total generation."
    )
    solar_mw = st.number_input(
        "Solar (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total solar generation as a proportion of the total generation"
    )
    
    tot_gen_mw = st.number_input(
        "Total Generation (MW)", min_value=5000, max_value=70000,
        value=36000, step=500, label_visibility="visible",
        help="Set total grid generation in Mega watts"
    )

    st.markdown('<div class="section-header" style="margin-top:20px;">Status</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style='font-size:11px;color:#8b949e;line-height:1.8;'>
        <span style='color:#f0883e;'>⚠</span> Models: <span style='color:#d29922;'>Mock data</span><br>
        <span style='color:#58a6ff;'>◉</span> Weather API: <span style='color:#8b949e;'>Not connected</span><br>
        <span style='color:#8b949e;'>○</span> Elexon API: <span style='color:#8b949e;'>Not connected</span>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# GENERATE DATA
# ─────────────────────────────────────────────
df = mock_hourly_generation(start_dt, n_hours)
avg_carbon = df["carbon_intensity"].mean()
peak_carbon = df["carbon_intensity"].max()
avg_supply  = df["total_supply_mw"].mean()
supply_gap  = tot_gen_mw - avg_supply
label_str, label_color, badge_cls = intensity_label(avg_carbon)


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown(f"""
<div style='display:flex;align-items:center;justify-content:space-between;
            padding:0 0 20px 0;border-bottom:1px solid #21262d;margin-bottom:24px;'>
    <div>
        <div style='font-family:Space Mono,monospace;font-size:22px;color:#e6edf3;font-weight:700;'>
            Carbon Intensity Simulator
        </div>
        <div style='font-size:13px;color:#8b949e;margin-top:4px;'>
            {location} · {start_dt.strftime("%d %b %Y")}{"–" + (start_dt + timedelta(hours=n_hours)).strftime("%d %b %Y") if n_hours > 24 else ""}
        </div>
    </div>
    <div style='text-align:right;'>
        <span class='{badge_cls}'>{label_str}</span>
        <div style='font-size:11px;color:#8b949e;margin-top:6px;font-family:Space Mono,monospace;'>avg {avg_carbon:.0f} gCO₂/kWh</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# METRICS ROW
# ─────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
metrics = [
    (c1, "Avg Carbon Intensity", f"{avg_carbon:.0f}", "gCO₂/kWh", None, None),
    (c2, "Peak Carbon Intensity", f"{peak_carbon:.0f}", "gCO₂/kWh", None, None),
    (c3, "Avg Supply", f"{avg_supply/1000:.1f}", "GW", None, None),
    (c4, "Supply/Demand Gap", f"{abs(supply_gap)/1000:.1f}", "GW " + ("surplus" if supply_gap < 0 else "shortfall"),
        supply_gap < 0, supply_gap >= 0),
    (c5, "Renewables Share", f"{(df[['wind_offshore','wind_onshore','solar','hydro']].sum(axis=1) / df['total_supply_mw'] * 100).mean():.0f}", "%", True, None),
]
for col, label, val, unit, good, bad in metrics:
    delta_html = ""
    if good is True:
        delta_html = f'<div class="metric-delta-good">▲ Favourable</div>'
    elif bad is True:
        delta_html = f'<div class="metric-delta-bad">▼ Watch</div>'
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
            <div class="metric-unit">{unit}</div>
            {delta_html}
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MAIN CHARTS — ROW 1
# ─────────────────────────────────────────────
left, right = st.columns([2, 1])

with left:
    st.markdown('<div class="section-header">Generation Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_bar(df), use_container_width=True, config={"displayModeBar": False})

with right:
    st.markdown('<div class="section-header">Current Mix</div>', unsafe_allow_html=True)
    # Use last available hour for pie
    last_row = df.iloc[-1]
    last_mix  = {s: float(last_row[s]) for s in SOURCES}
    st.plotly_chart(make_mix_pie(last_mix), use_container_width=True, config={"displayModeBar": False})

    ci_val = float(last_row["carbon_intensity"])
    st.plotly_chart(make_gauge(ci_val), use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────
# MAIN CHARTS — ROW 2
# ─────────────────────────────────────────────
st.markdown('<div class="section-header">Carbon Intensity Over Time</div>', unsafe_allow_html=True)
st.plotly_chart(make_carbon_line(df), use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────
# HYPOTHETICAL SCENARIO SIMULATOR
# ─────────────────────────────────────────────
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='background:#161b22;border:1px solid #21262d;border-radius:10px;padding:20px 24px;margin-bottom:4px;'>
    <div style='font-family:Space Mono,monospace;font-size:11px;color:#58a6ff;letter-spacing:0.15em;
                text-transform:uppercase;margin-bottom:4px;'>Hypothetical Scenario Simulator</div>
    <div style='font-size:12px;color:#8b949e;'>
        Adjust the energy mix below to model a hypothetical scenario.
        See how changing generation sources affects carbon intensity and storage requirements.
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("⚙  Configure Hypothetical Mix", expanded=True):
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Base values from average of the day
    base_avg = {s: float(df[s].mean()) for s in SOURCES}
    total_base = sum(base_avg.values())

    hypo_mix = {}
    scol1, scol2 = st.columns(2)

    slider_sources = [
        ("nuclear",      "⚛  Nuclear",       0,    9000),
        ("gas",          "🔥 Gas",            0,   15000),
        ("wind_offshore","💨 Offshore Wind",  0,   10000),
        ("wind_onshore", "🌬  Onshore Wind",  0,    6000),
        ("solar",        "☀  Solar",          0,    8000),
        ("biomass",      "🌿 Biomass",        0,    4000),
        ("hydro",        "💧 Hydro",          0,    3000),
    ]

    for i, (key, lbl, mn, mx) in enumerate(slider_sources):
        col = scol1 if i % 2 == 0 else scol2
        with col:
            hypo_mix[key] = st.slider(
                lbl,
                min_value=mn, max_value=mx,
                value=int(base_avg[key]),
                step=50,
                help=f"Avg predicted: {base_avg[key]:,.0f} MW",
            )

    # ── Calculated results ──
    hypo_total    = sum(hypo_mix.values())
    hypo_carbon   = carbon_from_mix(hypo_mix)
    shortfall_mw  = demand_mw - hypo_total
    storage_note  = f"{abs(shortfall_mw):,.0f} MW storage required" if shortfall_mw > 0 else f"{abs(shortfall_mw):,.0f} MW surplus (could charge storage)"

    h_label, h_color, h_badge = intensity_label(hypo_carbon)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Hypo Carbon Intensity</div>
            <div class="metric-value" style="color:{h_color};">{hypo_carbon:.0f}</div>
            <div class="metric-unit">gCO₂/kWh</div>
        </div>""", unsafe_allow_html=True)
    with rc2:
        delta_pct = ((hypo_carbon - avg_carbon) / avg_carbon * 100) if avg_carbon else 0
        arrow = "▲" if delta_pct > 0 else "▼"
        delta_cls = "metric-delta-bad" if delta_pct > 0 else "metric-delta-good"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">vs Predicted</div>
            <div class="metric-value">{abs(delta_pct):.1f}%</div>
            <div class="{delta_cls}">{arrow} {"Higher" if delta_pct > 0 else "Lower"}</div>
        </div>""", unsafe_allow_html=True)
    with rc3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Hypo Supply</div>
            <div class="metric-value">{hypo_total/1000:.1f}</div>
            <div class="metric-unit">GW</div>
        </div>""", unsafe_allow_html=True)
    with rc4:
        sf_color = "#f85149" if shortfall_mw > 0 else "#3fb950"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Storage Needed</div>
            <div class="metric-value" style="color:{sf_color};">{abs(shortfall_mw)/1000:.1f}</div>
            <div class="metric-unit">GW {"shortfall" if shortfall_mw > 0 else "surplus"}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# COMPARISON CHARTS (Predicted vs Hypothetical)
# ─────────────────────────────────────────────
# Scale hypothetical uniformly across time (flat scenario for now)
hypo_carbon_series  = pd.Series([hypo_carbon] * len(df))
hypo_supply_series  = pd.Series([hypo_total]  * len(df))

ch1, ch2 = st.columns(2)
with ch1:
    st.markdown('<div class="section-header">Carbon Intensity: Predicted vs Hypothetical</div>', unsafe_allow_html=True)
    st.plotly_chart(
        make_carbon_line(df, hypothetical=hypo_carbon_series),
        use_container_width=True, config={"displayModeBar": False}
    )
with ch2:
    st.markdown('<div class="section-header">Supply vs Demand</div>', unsafe_allow_html=True)
    st.plotly_chart(
        make_supply_demand(df, demand_mw, hypo_supply=hypo_supply_series),
        use_container_width=True, config={"displayModeBar": False}
    )


# ─────────────────────────────────────────────
# HYPOTHETICAL MIX PIE
# ─────────────────────────────────────────────
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
pc1, pc2 = st.columns(2)
with pc1:
    st.markdown('<div class="section-header">Predicted Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_pie(base_avg), use_container_width=True, config={"displayModeBar": False})
with pc2:
    st.markdown('<div class="section-header">Hypothetical Mix</div>', unsafe_allow_html=True)
    st.plotly_chart(make_mix_pie(hypo_mix), use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────
# RAW DATA TOGGLE
# ─────────────────────────────────────────────
with st.expander("📋  Raw Predicted Data"):
    display_df = df.copy()
    display_df["datetime"] = display_df["datetime"].dt.strftime("%Y-%m-%d %H:%M")
    display_df = display_df.rename(columns={s: SOURCE_LABELS[s] for s in SOURCES})
    display_df["Carbon Intensity (gCO₂/kWh)"] = display_df["carbon_intensity"].round(1)
    display_df["Total Supply (MW)"] = display_df["total_supply_mw"].round(0)
    show_cols = ["datetime"] + [SOURCE_LABELS[s] for s in SOURCES] + ["Carbon Intensity (gCO₂/kWh)", "Total Supply (MW)"]
    st.dataframe(
        display_df[show_cols].round(0),
        use_container_width=True, height=300,
        hide_index=True
    )


# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("""
<div style='border-top:1px solid #21262d;margin-top:32px;padding-top:16px;
            font-size:11px;color:#484f58;font-family:Space Mono,monospace;
            display:flex;justify-content:space-between;'>
    <span>CarbonSim · UI-only (mock data)</span>
    <span>Models: LSTM (Keras) + XGBoost (JSON) · Weather: Open-Meteo · Data: Elexon</span>
</div>
""", unsafe_allow_html=True)
