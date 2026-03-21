import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, os, json, glob
import time

# --- INITIAL SETUP ---
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()
if time.time() - st.session_state.last_refresh > 1800:
    st.session_state.last_refresh = time.time()
    st.cache_data.clear()
    st.rerun()

st.set_page_config(
    page_title="Guwahati AQI",
    page_icon="🌫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLING ---
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{background:#0a0c0f;color:#c8cdd6;font-family:'IBM Plex Sans',sans-serif}
.stApp{background:#0a0c0f}
.section-divider{height:1px;background:linear-gradient(90deg,transparent,#2a2d35,transparent);margin:32px 0}
.section-label{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7280;letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}
</style>""", unsafe_allow_html=True)

# --- DATA FUNCTIONS ---
def aqi_info(pm25):
    bps = [(0,30,0,50,"Good","#22c55e"),(31,60,51,100,"Satisfactory","#84cc16"),(61,90,101,200,"High","#f5a623"),(91,120,201,300,"Poor","#ef4444"),(121,250,301,400,"Very Poor","#dc2626"),(251,500,401,500,"Severe","#7f1d1d")]
    for blo,bhi,alo,ahi,cat,color in bps:
        if blo<=pm25<=bhi:
            return {"aqi":round(((ahi-alo)/(bhi-blo))*(pm25-blo)+alo),"category":cat,"color":color}
    return {"aqi":500,"category":"Severe","color":"#7f1d1d"}

@st.cache_data(ttl=600)
def load_data():
    files = sorted(glob.glob("data/raw/*.csv"), key=os.path.getmtime, reverse=True)
    if files:
        df = pd.read_csv(files[0], parse_dates=["datetime"])
        return df.sort_values("datetime").reset_index(drop=True)
    return pd.DataFrame()

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:14px;font-weight:700;color:#e8eaf0">GUWAHATI AQI</div>', unsafe_allow_html=True)
    
    if "page" not in st.session_state:
        st.session_state.page = "Home"

    # Use a radio or selectbox for stable navigation
    page = st.radio("Navigation", ["Home", "Science of Air", "Creator", "Data Transparency"], label_visibility="collapsed")
    st.session_state.page = page

    if st.button("↻ Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# --- PAGE LOGIC ---
hist = load_data()

if st.session_state.page == "Home":
    st.title("🌫️ Live Air Quality Forecast")
    
    if not hist.empty:
        # Corrected Slider Logic
        st.markdown('<div class="section-label">History Range (Days)</div>', unsafe_allow_html=True)
        days = st.select_slider("Range", options=[7, 14, 30, 60, 90], value=14)
        
        df_display = hist.tail(days * 24)
        st.line_chart(df_display.set_index("datetime")["pm25"])
    else:
        st.warning("No historical data found. Please run your data pipeline.")

elif st.session_state.page == "Science of Air":
    st.title("🔬 The Science of Air")
    st.markdown("---")
    
    t1, t2, t3 = st.tabs(["Thermal Inversion", "Stokes Law", "Hygroscopic Growth"])
    
    with t1:
        st.subheader("🏔️ The Valley Trap")
        st.write("Guwahati's hills trap cold air near the ground, creating a 'lid'.")
        st.latex(r"\frac{dT}{dz} > 0")
        st.info("This explains why AQI stays high even when traffic is low at night.")
        

    with t2:
        st.subheader("⏳ Particle Residence Time")
        st.write("Small particles stay in the air for days because of their low settling velocity.")
        st.latex(r"V_s = \frac{2r^2(\rho_p - \rho_f)g}{9\eta}")
        

    with t3:
        st.subheader("💧 Hygroscopic Growth")
        st.write("In humid Assam, particles absorb water and swell, increasing their mass.")
        st.latex(r"D(RH) = D_{dry}(1-RH)^{-\gamma}")
        

elif st.session_state.page == "Creator":
    st.title("👨‍🔬 About the Creator")
    st.write("Developed by Chao Bhaskar Gogoi, Physics Postgraduate.")

elif st.session_state.page == "Data Transparency":
    st.title("◈ Data Pipeline & Transparency")
    st.write("Data sourced from CPCB CAAQMS via OpenAQ.")
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests,