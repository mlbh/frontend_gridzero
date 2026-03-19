# ─────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Fuel Generation Forecast", layout="wide")
st.title("⚡ Fuel Generation Forecast")

# ── Initialise session state ───────────────────────────────────────────────────
if "forecast_df" not in st.session_state:
    st.session_state.forecast_df = None
if "forecast_days" not in st.session_state:
    st.session_state.forecast_days = None

# ── Controls row ───────────────────────────────────────────────────────────────
col_select, col_button, col_info = st.columns([2, 1, 3])

with col_select:
    days = st.selectbox(
        "Forecast horizon",
        options=list(range(1, 8)),
        format_func=lambda x: f"{x} day{'s' if x > 1 else ''}",
        index=2,
    )

with col_button:
    st.write("")  # vertical alignment nudge
    st.write("")
    predict_clicked = st.button("🔮 Predict", type="primary", use_container_width=True)

with col_info:
    if st.session_state.forecast_days is not None:
        st.info(f"Showing forecast for **{st.session_state.forecast_days} day(s)**. "
                "Change the horizon and click Predict to refresh.")

# ── Fetch only on button click ─────────────────────────────────────────────────
def fetch_forecast(days: int) -> pd.DataFrame:
    response = requests.get(
        "https://gridzero-400241154738.europe-west2.run.app/predict_lstm",
        params={"days": days}
    )
    response.raise_for_status()
    return pd.DataFrame(response.json())

if predict_clicked:
    with st.spinner(f"Fetching {days}-day forecast..."):
        try:
            df = fetch_forecast(days)
            st.session_state.forecast_df = df        # store in session state
            st.session_state.forecast_days = days    # remember which days were fetched
            st.success("Forecast loaded!")
        except Exception as e:
            st.error(f"Failed to load data: {e}")

# ── Only render charts if data exists in session state ─────────────────────────
if st.session_state.forecast_df is None:
    st.info("👆 Select a forecast horizon and click **Predict** to load data.")
    st.stop()

df = st.session_state.forecast_df  # use stored data for everything below


# ── Carbon intensity calculation ───────────────────────────────────────────────
CARBON_INTENSITY = {
    "Biomass":                              230,
    "Fossil Gas":                           490,
    "Fossil Hard coal":                     820,
    "Fossil Oil":                           650,  # added — commonly ~650
    "Nuclear":                               12,
    "Solar":                                 45,
    "Wind Onshore":                          11,
    "Wind Offshore":                         11,
    "Hydro Run-of-river and poundage":       24,
    "Hydro Pumped Storage":                  24,  # similar to run-of-river
    "Other":                                300,  # conservative catch-all
}

def calculate_carbon_intensity(df: pd.DataFrame) -> pd.DataFrame:
    emissions = sum(
        df[source] * factor
        for source, factor in CARBON_INTENSITY.items()
        if source in df.columns
    )
    df["carbon_intensity"] = emissions / df["total_output_MW"]  # gCO₂/kWh
    return df

df = calculate_carbon_intensity(df)


# ── Pre-process ────────────────────────────────────────────────────────────────
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time")

GENERATION_COLS = [
    "Biomass", "Fossil Gas", "Fossil Hard coal", "Fossil Oil",
    "Hydro Pumped Storage", "Hydro Run-of-river and poundage",
    "Nuclear", "Other", "Solar", "Wind Offshore", "Wind Onshore",
]

RENEWABLES = ["Solar", "Wind Offshore", "Wind Onshore",
              "Hydro Run-of-river and poundage", "Biomass"]
FOSSIL     = ["Fossil Gas", "Fossil Hard coal", "Fossil Oil"]

# ── KPI row ────────────────────────────────────────────────────────────────────
# ── KPI row ────────────────────────────────────────────────────────────────────
latest = df.iloc[-1]  # still used for carbon intensity, temperature, etc.

total_output_all = df["total_output_MW"].sum()  # sum across all timestamps
renew  = latest[RENEWABLES].sum()
fossil = latest[FOSSIL].sum()
ci     = latest["carbon_intensity"]

# colour-coded delta label
if ci < 100:
    ci_label, ci_delta = "🟢 Very low", "Very low carbon"
elif ci < 200:
    ci_label, ci_delta = "🟡 Low", "Low carbon"
elif ci < 350:
    ci_label, ci_delta = "🟠 Moderate", "Moderate carbon"
else:
    ci_label, ci_delta = "🔴 High", "High carbon"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Output (MW)", f"{total_output_all:,.0f}")
k2.metric("Carbon Intensity (gCO₂/kWh)",       f"{ci:.0f}", ci_label)
k3.metric("Renewables (MW)",        f"{renew:,.0f}",  f"{renew/total_output_all*100:.1f}%")
k4.metric("Fossil Fuels (MW)",      f"{fossil:,.0f}", f"{fossil/total_output_all*100:.1f}%")
k5.metric("Temperature (°C)",       f"{latest['temperature_2m']:.1f}")



# ── Charts (unchanged from before) ────────────────────────────────────────────
st.subheader("Generation Mix Over Time")
fig_area = px.area(
    df, x="time", y=GENERATION_COLS,
    labels={"value": "MW", "variable": "Source"},
    color_discrete_sequence=px.colors.qualitative.Safe,
)
fig_area.update_layout(hovermode="x unified", legend_title="Fuel type")
st.plotly_chart(fig_area, use_container_width=True)

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Total Output vs Temperature")
    fig_dual = go.Figure()
    fig_dual.add_trace(go.Scatter(
        x=df["time"], y=df["total_output_MW"],
        name="Total Output (MW)", yaxis="y1",
        line=dict(color="#636EFA", width=2),
    ))
    fig_dual.add_trace(go.Scatter(
        x=df["time"], y=df["temperature_2m"],
        name="Temperature (°C)", yaxis="y2",
        line=dict(color="#EF553B", width=2, dash="dot"),
    ))
    fig_dual.update_layout(
        yaxis=dict(title="MW"),
        yaxis2=dict(title="°C", overlaying="y", side="right"),
        hovermode="x unified", legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_dual, use_container_width=True)

with col_right:
    st.subheader("Solar Output vs Radiation")
    fig_solar = go.Figure()
    fig_solar.add_trace(go.Scatter(
        x=df["time"], y=df["Solar"],
        name="Solar (MW)", yaxis="y1",
        line=dict(color="#FFA15A"),
    ))
    fig_solar.add_trace(go.Scatter(
        x=df["time"], y=df["shortwave_radiation"],
        name="Shortwave Radiation", yaxis="y2",
        line=dict(color="#FECB52", dash="dot"),
    ))
    fig_solar.update_layout(
        yaxis=dict(title="MW"),
        yaxis2=dict(title="W/m²", overlaying="y", side="right"),
        hovermode="x unified", legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_solar, use_container_width=True)

col3, col4 = st.columns(2)

with col3:
    st.subheader("Wind Generation vs Wind Speed")
    df["Wind Total"] = df["Wind Offshore"] + df["Wind Onshore"]
    fig_wind = go.Figure()
    fig_wind.add_trace(go.Scatter(
        x=df["time"], y=df["Wind Total"],
        name="Wind Total (MW)", yaxis="y1",
        line=dict(color="#00CC96"),
    ))
    fig_wind.add_trace(go.Scatter(
        x=df["time"], y=df["wind_speed_100m"],
        name="Wind Speed 100m (m/s)", yaxis="y2",
        line=dict(color="#19D3F3", dash="dot"),
    ))
    fig_wind.update_layout(
        yaxis=dict(title="MW"),
        yaxis2=dict(title="m/s", overlaying="y", side="right"),
        hovermode="x unified", legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_wind, use_container_width=True)

with col4:
    st.subheader("Generation Mix at Latest Timestamp")
    latest_mix = latest[GENERATION_COLS].reset_index()
    latest_mix.columns = ["Source", "MW"]
    latest_mix = latest_mix[latest_mix["MW"] > 0]
    fig_pie = px.pie(
        latest_mix, names="Source", values="MW",
        color_discrete_sequence=px.colors.qualitative.Safe,
        hole=0.4,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pie, use_container_width=True)

with st.expander("View raw data"):
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV", df.to_csv(index=False),
        file_name=f"forecast_{st.session_state.forecast_days}d.csv",
        mime="text/csv",
    )
