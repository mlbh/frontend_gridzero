import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Grid Forecast",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        background-color: #0f1117;
        color: #e8eaf0;
    }
    .stApp { background: #0f1117; }

    /* ── Header ── */
    .dash-header {
        padding: 2rem 0 1.5rem 0;
        border-bottom: 1px solid #1e2740;
        margin-bottom: 2rem;
    }
    .dash-eyebrow {
        font-family: 'DM Mono', monospace;
        font-size: 0.7rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #4b5680;
        margin-bottom: 0.35rem;
    }
    .dash-title {
        font-family: 'DM Sans', sans-serif;
        font-size: 1.9rem;
        font-weight: 600;
        color: #e8eaf0;
        letter-spacing: -0.02em;
        line-height: 1.1;
    }
    .dash-title span { color: #60a5fa; }

    /* ── KPI cards ── */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 14px;
        margin-bottom: 2rem;
    }
    .kpi-card {
        background: #161b2e;
        border: 1px solid #1e2740;
        border-radius: 10px;
        padding: 1.25rem 1.4rem 1.1rem;
        position: relative;
    }
    .kpi-card::after {
        content: '';
        position: absolute;
        bottom: 0; left: 1.4rem; right: 1.4rem;
        height: 2px;
        border-radius: 2px;
        background: var(--bar, #3b82f6);
        opacity: 0.5;
    }
    .kpi-label {
        font-family: 'DM Mono', monospace;
        font-size: 0.62rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #4b5680;
        margin-bottom: 0.6rem;
    }
    .kpi-value {
        font-size: 1.65rem;
        font-weight: 600;
        color: #e8eaf0;
        letter-spacing: -0.02em;
        line-height: 1;
    }
    .kpi-delta {
        font-family: 'DM Mono', monospace;
        font-size: 0.68rem;
        margin-top: 0.45rem;
        color: #4b5680;
    }
    .kpi-delta.green  { color: #34d399; }
    .kpi-delta.amber  { color: #fbbf24; }
    .kpi-delta.orange { color: #fb923c; }
    .kpi-delta.red    { color: #f87171; }

    /* ── Section headers ── */
    .section-wrap { margin: 0.25rem 0 0.75rem; }
    .section-eyebrow {
        font-family: 'DM Mono', monospace;
        font-size: 0.62rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #60a5fa;
        margin-bottom: 0.2rem;
    }
    .section-title {
        font-size: 1rem;
        font-weight: 600;
        color: #e8eaf0;
        letter-spacing: -0.01em;
    }

    /* ── Streamlit widget overrides ── */
    .stSelectbox > div > div {
        background: #161b2e !important;
        border: 1px solid #1e2740 !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.9rem !important;
        color: #e8eaf0 !important;
    }
    .stButton > button {
        background: #2563eb !important;
        color: #ffffff !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.6rem !important;
        transition: background 0.15s !important;
    }
    .stButton > button:hover { background: #1d4ed8 !important; }

    /* ── Misc ── */
    hr { border-color: #1e2740 !important; }
    .stAlert {
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.85rem !important;
    }
    .streamlit-expanderHeader {
        font-family: 'DM Mono', monospace !important;
        font-size: 0.72rem !important;
        letter-spacing: 0.06em !important;
        color: #4b5680 !important;
    }
    #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
GENERATION_COLS = [
    "Biomass", "Fossil Gas", "Fossil Hard coal", "Fossil Oil",
    "Hydro Pumped Storage", "Hydro Run-of-river and poundage",
    "Nuclear", "Other", "Solar", "Wind Offshore", "Wind Onshore",
]
RENEWABLES = ["Solar", "Wind Offshore", "Wind Onshore",
              "Hydro Run-of-river and poundage", "Biomass"]
FOSSIL     = ["Fossil Gas", "Fossil Hard coal", "Fossil Oil"]

CARBON_INTENSITY_FACTORS = {
    "Biomass":                             230,
    "Fossil Gas":                          490,
    "Fossil Hard coal":                    820,
    "Fossil Oil":                          650,
    "Nuclear":                              12,
    "Solar":                                45,
    "Wind Onshore":                         11,
    "Wind Offshore":                        11,
    "Hydro Run-of-river and poundage":      24,
    "Hydro Pumped Storage":                 24,
    "Other":                               300,
}

GROUPS = {
    "Renewables":    ["Solar", "Wind Offshore", "Wind Onshore",
                      "Hydro Run-of-river and poundage", "Biomass"],
    "Nuclear":       ["Nuclear"],
    "Hydro Storage": ["Hydro Pumped Storage"],
    "Fossil Fuels":  ["Fossil Gas", "Fossil Hard coal", "Fossil Oil"],
    "Other":         ["Other"],
}

GROUP_COLOURS = {
    "Renewables":    "#34d399",
    "Nuclear":       "#60a5fa",
    "Hydro Storage": "#0ea5e9",
    "Fossil Fuels":  "#f87171",
    "Other":         "#94a3b8",
}

PALETTE = [
    "#2563eb", "#0ea5e9", "#10b981", "#f59e0b",
    "#ef4444", "#8b5cf6", "#f97316", "#6ee7b7",
    "#93c5fd", "#fca5a5", "#6366f1",
]

PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#161b2e",
    font=dict(family="DM Sans, sans-serif", color="#4b5680", size=11),
    xaxis=dict(gridcolor="#1e2740", zeroline=False, showline=False, tickfont=dict(size=10)),
    yaxis=dict(gridcolor="#1e2740", zeroline=False, showline=False, tickfont=dict(size=10)),
    legend=dict(
        bgcolor="rgba(22,27,46,0.9)",
        bordercolor="#1e2740",
        borderwidth=1,
        font=dict(size=10, family="DM Sans, sans-serif"),
    ),
    margin=dict(t=30, b=40, l=50, r=30),
    hovermode="x unified",
)

def section(eyebrow, title):
    st.markdown(f"""
    <div class="section-wrap">
        <div class="section-eyebrow">{eyebrow}</div>
        <div class="section-title">{title}</div>
    </div>""", unsafe_allow_html=True)

def apply_layout(fig, **kwargs):
    fig.update_layout(**{**PLOT_LAYOUT, **kwargs})
    return fig

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="dash-header">
    <div class="dash-eyebrow">National Grid · Forecast Dashboard</div>
    <div class="dash-title">Grid <span>Generation</span> Forecast</div>
</div>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "forecast_df"   not in st.session_state: st.session_state.forecast_df   = None
if "forecast_days" not in st.session_state: st.session_state.forecast_days = None

# ── Controls ───────────────────────────────────────────────────────────────────
ctrl_a, ctrl_b, ctrl_c = st.columns([2, 1, 4])
with ctrl_a:
    days = st.selectbox(
        "Forecast horizon",
        options=list(range(1, 8)),
        format_func=lambda x: f"{x} day{'s' if x > 1 else ''}",
        index=2,
    )
with ctrl_b:
    st.write(""); st.write("")
    predict_clicked = st.button("Run Forecast", type="primary", use_container_width=True)
with ctrl_c:
    if st.session_state.forecast_days:
        st.write(""); st.write("")
        st.info(f"Showing {st.session_state.forecast_days}-day forecast. Adjust the horizon and click Run Forecast to refresh.")

# ── Fetch ──────────────────────────────────────────────────────────────────────
def fetch_forecast(days: int) -> pd.DataFrame:
    response = requests.get(
        "https://gridzero-400241154738.europe-west2.run.app/predict_lstm",
        params={"days": days},
    )
    response.raise_for_status()
    return pd.DataFrame(response.json())

if predict_clicked:
    with st.spinner("Fetching forecast..."):
        try:
            df = fetch_forecast(days)
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time")
            emissions = sum(
                df[src] * factor
                for src, factor in CARBON_INTENSITY_FACTORS.items()
                if src in df.columns
            )
            df["carbon_intensity"] = emissions / df["total_output_MW"]
            # Pre-compute grouped columns
            for group, sources in GROUPS.items():
                cols = [c for c in sources if c in df.columns]
                df[group] = df[cols].sum(axis=1)
            st.session_state.forecast_df   = df
            st.session_state.forecast_days = days
            st.success("Forecast loaded successfully.")
        except Exception as e:
            st.error(f"Failed to load forecast: {e}")

# ── Gate ───────────────────────────────────────────────────────────────────────
if st.session_state.forecast_df is None:
    st.markdown("""
    <div style="text-align:center;padding:5rem 0;color:#4b5680;font-family:'DM Mono',monospace;font-size:0.8rem">
        Select a forecast horizon above and click <strong style="color:#60a5fa">Run Forecast</strong> to load data.
    </div>""", unsafe_allow_html=True)
    st.stop()

df = st.session_state.forecast_df

# ── KPI pre-compute ────────────────────────────────────────────────────────────
latest       = df.iloc[-1]
interval_h   = (df["time"].diff().dropna().mode()[0].seconds / 3600)
total_mwh    = df["total_output_MW"].sum() * interval_h
avg_ci       = df["carbon_intensity"].mean()
latest_ci    = latest["carbon_intensity"]
renew_mwh    = df[RENEWABLES].sum().sum() * interval_h
fossil_mwh   = df[FOSSIL].sum().sum() * interval_h
total_gen    = df[GENERATION_COLS].sum().sum() * interval_h
renew_pct    = renew_mwh / total_gen * 100
fossil_pct   = fossil_mwh / total_gen * 100

def ci_info(val):
    if val < 100:  return "Very Low",  "green"
    if val < 200:  return "Low",       "green"
    if val < 350:  return "Moderate",  "amber"
    return               "High",       "red"

avg_ci_label, avg_ci_cls = ci_info(avg_ci)
lat_ci_label, lat_ci_cls = ci_info(latest_ci)

# ── KPI row ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card" style="--bar:#2563eb">
    <div class="kpi-label">Total Energy Output</div>
    <div class="kpi-value">{total_mwh:,.0f}</div>
    <div class="kpi-delta">MWh · {st.session_state.forecast_days} day(s)</div>
  </div>
  <div class="kpi-card" style="--bar:#10b981">
    <div class="kpi-label">Avg Carbon Intensity</div>
    <div class="kpi-value">{avg_ci:.0f}</div>
    <div class="kpi-delta {avg_ci_cls}">{avg_ci_label} · gCO₂/kWh</div>
  </div>
  <div class="kpi-card" style="--bar:#0ea5e9">
    <div class="kpi-label">Latest Carbon Intensity</div>
    <div class="kpi-value">{latest_ci:.0f}</div>
    <div class="kpi-delta {lat_ci_cls}">{lat_ci_label} · gCO₂/kWh</div>
  </div>
  <div class="kpi-card" style="--bar:#10b981">
    <div class="kpi-label">Renewable Share</div>
    <div class="kpi-value">{renew_pct:.1f}%</div>
    <div class="kpi-delta green">{renew_mwh:,.0f} MWh</div>
  </div>
  <div class="kpi-card" style="--bar:#ef4444">
    <div class="kpi-label">Fossil Share</div>
    <div class="kpi-value">{fossil_pct:.1f}%</div>
    <div class="kpi-delta red">{fossil_mwh:,.0f} MWh</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ROW — Current generation mix (donut)  |  Avg output per fuel (bar)
# ═══════════════════════════════════════════════════════════════════════════════
col_a, col_b = st.columns(2)

with col_a:
    section("Snapshot", "Current Generation Mix")
    latest_mix = latest[GENERATION_COLS].reset_index()
    latest_mix.columns = ["Source", "MW"]
    latest_mix = latest_mix[latest_mix["MW"] > 0].sort_values("MW", ascending=False)
    fig_donut = px.pie(
        latest_mix, names="Source", values="MW",
        hole=0.58,
        color_discrete_sequence=PALETTE,
    )
    fig_donut.update_traces(
        textposition="outside",
        textinfo="percent+label",
        textfont=dict(family="DM Sans, sans-serif", size=10, color="#4b5680"),
        marker=dict(line=dict(color="#0f1117", width=2)),
    )
    fig_donut.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(t=20, b=20, l=20, r=20),
        annotations=[dict(
            text=f"<b>{latest['total_output_MW']:,.0f}</b><br><span style='font-size:11px'>MW now</span>",
            x=0.5, y=0.5,
            font=dict(family="DM Sans, sans-serif", size=20, color="#e8eaf0"),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig_donut, use_container_width=True)

with col_b:
    section("Average", "Avg Output per Fuel Type")
    avg_output = df[GENERATION_COLS].mean().reset_index()
    avg_output.columns = ["Source", "Avg MW"]
    avg_output = avg_output.sort_values("Avg MW", ascending=True)
    fig_bar = px.bar(
        avg_output, x="Avg MW", y="Source", orientation="h",
        color="Avg MW",
        color_continuous_scale=["#1e2740", "#3b82f6", "#60a5fa"],
    )
    fig_bar.update_coloraxes(showscale=False)
    apply_layout(fig_bar, xaxis_title="Average MW", yaxis_title="")
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# CHART — Generation mix over time (all fuel types)
# ═══════════════════════════════════════════════════════════════════════════════
section("Generation", "Mix Over Time")
fig_area = px.area(df, x="time", y=GENERATION_COLS, color_discrete_sequence=PALETTE)
fig_area.update_traces(line=dict(width=0.8))
apply_layout(fig_area,
    yaxis_title="MW",
    legend=dict(**PLOT_LAYOUT["legend"], orientation="h", y=-0.22),
)
st.plotly_chart(fig_area, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# CHART — Grouped mix & carbon intensity
# ═══════════════════════════════════════════════════════════════════════════════
section("Generation", "Grouped Mix & Carbon Intensity Over Time")

fig_mix = go.Figure()
for group in GROUPS.keys():
    fig_mix.add_trace(go.Scatter(
        x=df["time"], y=df[group],
        name=group, yaxis="y1",
        stackgroup="one",
        fillcolor=GROUP_COLOURS[group],
        line=dict(color=GROUP_COLOURS[group], width=0.5),
        hovertemplate=f"<b>{group}</b>: %{{y:,.0f}} MW<extra></extra>",
    ))
fig_mix.add_trace(go.Scatter(
    x=df["time"], y=df["carbon_intensity"],
    name="Carbon Intensity (gCO₂/kWh)", yaxis="y2",
    line=dict(color="#fbbf24", width=2, dash="dot"),
    hovertemplate="<b>Carbon Intensity</b>: %{y:.0f} gCO₂/kWh<extra></extra>",
))
apply_layout(fig_mix,
    yaxis=dict(**PLOT_LAYOUT["yaxis"], title="MW"),
    yaxis2=dict(
        title=dict(text="gCO₂/kWh", font=dict(color="#fbbf24")),
        overlaying="y", side="right",
        gridcolor="rgba(0,0,0,0)", zeroline=False,
        tickfont=dict(size=10, color="#fbbf24"),
    ),
    legend=dict(**PLOT_LAYOUT["legend"], orientation="h", y=-0.18),
)
st.plotly_chart(fig_mix, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ROW — Average daily profile  |  CO₂ contribution per fuel
# ═══════════════════════════════════════════════════════════════════════════════
col_c, col_d = st.columns(2)

with col_c:
    section("Daily Patterns", "Average Generation Profile by Hour of Day")
    hourly_avg = (
        df.assign(hour=df["time"].dt.hour)
        .groupby("hour")["total_output_MW"]
        .mean()
        .reset_index()
    )
    fig_profile = go.Figure()
    fig_profile.add_trace(go.Scatter(
        x=hourly_avg["hour"], y=hourly_avg["total_output_MW"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(37,99,235,0.07)",
        line=dict(color="#2563eb", width=2),
        name="Avg Total Output",
        hovertemplate="<b>%{x:02d}:00</b> — %{y:,.0f} MW<extra></extra>",
    ))
    apply_layout(fig_profile,
        xaxis=dict(
            **PLOT_LAYOUT["xaxis"],
            title="Hour of Day",
            tickmode="linear",
            tick0=0, dtick=1,
            tickvals=list(range(24)),
            ticktext=[f"{h:02d}:00" for h in range(24)],
        ),
        yaxis=dict(**PLOT_LAYOUT["yaxis"], title="Average MW"),
        showlegend=False,
    )
    st.plotly_chart(fig_profile, use_container_width=True)

with col_d:
    section("Emissions", "CO₂ Contribution per Fuel Type")
    co2_contrib = {
        src: (df[src] * factor).mean()
        for src, factor in CARBON_INTENSITY_FACTORS.items()
        if src in df.columns
    }
    co2_df = pd.DataFrame(
        sorted(co2_contrib.items(), key=lambda x: x[1], reverse=True),
        columns=["Source", "Avg gCO₂ contribution"],
    )
    fig_co2 = px.bar(
        co2_df, x="Avg gCO₂ contribution", y="Source", orientation="h",
        color="Avg gCO₂ contribution",
        color_continuous_scale=["#10b981", "#f59e0b", "#ef4444"],
    )
    fig_co2.update_coloraxes(showscale=False)
    apply_layout(fig_co2, xaxis_title="Avg gCO₂/kWh contribution", yaxis_title="")
    st.plotly_chart(fig_co2, use_container_width=True)


st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# ROW — Solar patterns
# ═══════════════════════════════════════════════════════════════════════════════
section("Solar", "Solar Energy Patterns")

col_s1, col_s2 = st.columns(2)

with col_s1:
    # Solar output vs shortwave radiation — dual axis line
    section("", "Output vs Shortwave Radiation")
    fig_solar_rad = go.Figure()
    fig_solar_rad.add_trace(go.Scatter(
        x=df["time"], y=df["Solar"],
        name="Solar (MW)", yaxis="y1",
        fill="tozeroy", fillcolor="rgba(251,191,36,0.07)",
        line=dict(color="#fbbf24", width=2),
        hovertemplate="<b>Solar</b>: %{y:,.0f} MW<extra></extra>",
    ))
    fig_solar_rad.add_trace(go.Scatter(
        x=df["time"], y=df["shortwave_radiation"],
        name="Shortwave Radiation (W/m²)", yaxis="y2",
        line=dict(color="#fb923c", width=1.5, dash="dot"),
        hovertemplate="<b>Radiation</b>: %{y:,.0f} W/m²<extra></extra>",
    ))
    apply_layout(fig_solar_rad,
        yaxis=dict(**PLOT_LAYOUT["yaxis"], title="MW"),
        yaxis2=dict(
            title=dict(text="W/m²", font=dict(color="#fb923c")),
            overlaying="y", side="right",
            gridcolor="rgba(0,0,0,0)", zeroline=False,
            tickfont=dict(size=10, color="#fb923c"),
        ),
        legend=dict(**PLOT_LAYOUT["legend"], orientation="h", y=-0.2),
    )
    st.plotly_chart(fig_solar_rad, use_container_width=True)

with col_s2:
    # Solar average daily profile
    section("", "Average Solar Output by Hour of Day")
    solar_hourly = (
        df.assign(hour=df["time"].dt.hour)
        .groupby("hour")["Solar"]
        .mean()
        .reset_index()
    )
    fig_solar_profile = go.Figure()
    fig_solar_profile.add_trace(go.Scatter(
        x=solar_hourly["hour"], y=solar_hourly["Solar"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(251,191,36,0.07)",
        line=dict(color="#fbbf24", width=2),
        hovertemplate="<b>%{x:02d}:00</b> — %{y:,.0f} MW<extra></extra>",
    ))
    apply_layout(fig_solar_profile,
        xaxis=dict(
            **PLOT_LAYOUT["xaxis"],
            title="Hour of Day",
            tickmode="linear",
            tick0=0, dtick=1,
            tickvals=list(range(24)),
            ticktext=[f"{h:02d}:00" for h in range(24)],
        ),
        yaxis=dict(**PLOT_LAYOUT["yaxis"], title="Average MW"),
        showlegend=False,
    )
    st.plotly_chart(fig_solar_profile, use_container_width=True)


# ── Raw data ───────────────────────────────────────────────────────────────────
st.divider()
with st.expander("View raw data"):
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False),
        file_name=f"grid_forecast_{st.session_state.forecast_days}d.csv",
        mime="text/csv",
    )
