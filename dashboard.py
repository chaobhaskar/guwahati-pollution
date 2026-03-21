import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, os, json, glob, time

# --- INITIAL SETUP ---
st.set_page_config(
    page_title="Guwahati AQI",
    page_icon="🌫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{background:#0a0c0f;color:#c8cdd6;font-family:'IBM Plex Sans',sans-serif}
.stApp{background:#0a0c0f}
.section-label{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7280;letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}
</style>""", unsafe_allow_html=True)

# --- DATA LOADING ---
@st.cache_data(ttl=600)
def load_data():
    files = sorted(glob.glob("data/raw/*.csv"), key=os.path.getmtime, reverse=True)
    if files:
        df = pd.read_csv(files[0], parse_dates=["datetime"])
        return df.sort_values("datetime").reset_index(drop=True)
    return pd.DataFrame()

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:14px;font-weight:700;color:#e8eaf0;margin-bottom:20px">GUWAHATI AQI</div>', unsafe_allow_html=True)
    
    # Stable Navigation using radio
    page = st.radio("MENU", ["Home", "Science of Air", "Creator", "Data Transparency"])
    
    st.markdown("---")
    if st.button("↻ Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# --- PAGE LOGIC ---
hist = load_data()

if page == "Home":
    st.title("🌫️ Air Quality Dashboard")
    st.markdown('<div class="section-label">Live Brahmaputra Valley Monitoring</div>', unsafe_allow_html=True)
    
    if not hist.empty:
        # Fixed Slider (Numeric options to avoid the '14' error)
        days = st.select_slider("Select History Range (Days)", options=[7, 14, 30, 60], value=14)
        
        df_display = hist.tail(days * 24)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_display["datetime"], y=df_display["pm25"], line=dict(color="#f5a623", width=2), fill="tozeroy"))
        fig.update_layout(paper_bgcolor="#111318", plot_bgcolor="#111318", font=dict(color="#c8cdd6"), height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data found. Please ensure your data pipeline is running.")

elif page == "Science of Air":
    st.title("🔬 The Science of Air")
    st.write("Atmospheric physics of the Guwahati 'Bowl'.")
    st.markdown("---")
    
    t1, t2, t3 = st.tabs(["Thermal Inversion", "Stokes Law", "Hygroscopic Growth"])
    
    with t1:
        st.subheader("🏔️ The Valley Trap")
        st.write("Guwahati's hills trap cold air near the ground, creating a 'lid' known as a temperature inversion.")
        st.latex(r"\frac{dT}{dz} > 0")
        st.info("Normally, air cools with height. In an inversion, it warms up, trapping PM2.5 at breathing level.")
        

    with t2:
        st.subheader("⏳ Particle Residence Time")
        st.write("PM2.5 particles stay in the air for days because their settling velocity is so low.")
        st.latex(r"V_s = \frac{2r^2(\rho_p - \rho_f)g}{9\eta}")
        st.write("This physics justifies our model's 48-hour history window.")
        

    with t3:
        st.subheader("💧 Hygroscopic Growth")
        st.write("Assam's humidity causes particles to absorb water and swell (deliquescence).")
        st.latex(r"D(RH) = D_{dry}(1-RH)^{-\gamma}")
        

elif page == "Creator":
    st.title("👨‍🔬 About the Creator")
    st.write("Project developed by Chao Bhaskar Gogoi, Physics Postgraduate.")

elif page == "Data Transparency":
    st.title("◈ Data & Transparency")
    st.write("Data sourced from CPCB CAAQMS via OpenAQ.")