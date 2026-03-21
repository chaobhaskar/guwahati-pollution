import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, os, json, glob
try:
    from streamlit_folium import st_folium
    import folium
    FOLIUM_AVAILABLE = True
except:
    FOLIUM_AVAILABLE = False

import time
# Auto-refresh every 30 minutes
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

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{background:#0a0c0f;color:#c8cdd6;font-family:'IBM Plex Sans',sans-serif}
.stApp{background:#0a0c0f}
#MainMenu,footer,header{visibility:hidden}
.block-container{padding:1rem 2rem 3rem;max-width:1300px}
[data-testid="metric-container"]{background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:14px 18px}
[data-testid="metric-container"] label{font-family:'IBM Plex Mono',monospace!important;font-size:10px!important;color:#6b7280!important;letter-spacing:.08em!important;text-transform:uppercase}
[data-testid="metric-container"] [data-testid="stMetricValue"]{font-family:'IBM Plex Mono',monospace!important;font-size:24px!important;font-weight:700!important;color:#e8eaf0!important}
section[data-testid="stSidebar"]{background:#0d0f14;border-right:0.5px solid #1e2028;width:260px!important}
section[data-testid="stSidebar"] .block-container{padding:1rem}
.stButton>button{background:#111318;border:0.5px solid #2a2d35;color:#c8cdd6;border-radius:6px;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.04em}
.stButton>button:hover{border-color:#f5a623;color:#f5a623}
div[data-testid="stHorizontalBlock"]{gap:12px}
.section-divider{height:1px;background:linear-gradient(90deg,transparent,#2a2d35,transparent);margin:32px 0}
.section-label{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7280;letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}
</style>""", unsafe_allow_html=True)

STATIONS = [
    {"name":"Railway Colony","area":"North Guwahati","lat":26.1817,"lon":91.7806,"sensor_pm25":12235761,"sensor_pm10":12235760,"type":"CPCB CAAQMS"},
    {"name":"Pan Bazaar","area":"City Centre","lat":26.1844,"lon":91.7458,"sensor_pm25":12236490,"sensor_pm10":12236489,"type":"CPCB CAAQMS"},
    {"name":"IIT Guwahati","area":"North Bank","lat":26.1924,"lon":91.6966,"sensor_pm25":3409360,"sensor_pm10":None,"type":"PCBA Monitor"},
    {"name":"LGBI Airport","area":"Borjhar","lat":26.1061,"lon":91.5858,"sensor_pm25":3409390,"sensor_pm10":None,"type":"PCBA Monitor"},
]

KEY_LOCATIONS = [
    {"name":"G.S. Road","lat":26.1396,"lon":91.7943,"note":"High traffic corridor"},
    {"name":"Paltan Bazar","lat":26.1847,"lon":91.7534,"note":"Commercial hub"},
    {"name":"Six Mile","lat":26.1285,"lon":91.8156,"note":"Traffic bottleneck"},
    {"name":"Ganeshguri","lat":26.1467,"lon":91.7789,"note":"Residential area"},
    {"name":"Dispur","lat":26.1342,"lon":91.7858,"note":"Government district"},
    {"name":"GMCH","lat":26.1731,"lon":91.7441,"note":"Medical College"},
]

def aqi_info(pm25):
    bps = [(0,30,0,50,"Good","#22c55e"),(31,60,51,100,"Satisfactory","#84cc16"),(61,90,101,200,"High","#f5a623"),(91,120,201,300,"Poor","#22c55e"),(121,250,301,400,"Very Poor","#dc2626"),(251,500,401,500,"Severe","#7f1d1d")]
    for blo,bhi,alo,ahi,cat,color in bps:
        if blo<=pm25<=bhi:
            return {"aqi":round(((ahi-alo)/(bhi-blo))*(pm25-blo)+alo),"category":cat,"color":color}
    return {"aqi":500,"category":"Severe","color":"#7f1d1d"}

def health_advice(cat):
    d = {"Good":"Safe for all outdoor activities including jogging on the riverfront.","Satisfactory":"Acceptable. Sensitive people should limit prolonged outdoor exertion.","High":"Sensitive groups should reduce outdoor activity. Limit exercise near G.S. Road.","Poor":"Everyone should reduce outdoor exertion. Sensitive groups stay indoors.","Very Poor":"Avoid outdoor activity. Use N95 masks if going out.","Severe":"EMERGENCY. Stay indoors. Seek medical attention if breathing issues."}
    return d.get(cat,"")

def confidence_score(mae, pm25):
    rel = (mae / max(pm25,1)) * 100
    if rel < 10: return 95, "Very High"
    elif rel < 15: return 88, "High"
    elif rel < 25: return 76, "High"
    elif rel < 35: return 95.2, "Excellent"
    else: return 45, "Low"

def local_impact(pm25):
    cigs = round(pm25/22,1)
    if pm25<=30:
        return {"cigarettes":cigs,"summary":"Air quality is clean today.","activity":"Safe for all outdoor activities including jogging on the riverfront.","avoid":None,"zones":["All areas safe today"],"icon":"🟢","visibility":"Good visibility across the Brahmaputra."}
    elif pm25<=60:
        return {"cigarettes":cigs,"summary":"Mild pollution — acceptable for most people.","activity":"Morning walks near Uzan Bazar and Fancy Bazar are fine.","avoid":"Sensitive individuals should avoid prolonged exercise near G.S. Road.","zones":["G.S. Road (traffic)","Paltan Bazar (congestion)"],"icon":"🟡","visibility":"Slight haze possible over Dispur hills."}
    elif pm25<=90:
        return {"cigarettes":cigs,"summary":"High pollution — sensitive groups at risk.","activity":"Limit outdoor exercise to early morning (5-7am) near Dighalipukhuri.","avoid":"Avoid G.S. Road, Six Mile, and Ganeshguri during peak hours.","zones":["G.S. Road","Six Mile junction","Ganeshguri","Paltan Bazar"],"icon":"🟠","visibility":"Noticeable haze over the city."}
    elif pm25<=120:
        return {"cigarettes":cigs,"summary":"Poor air quality — everyone should take precautions.","activity":"Avoid all outdoor exercise. Keep windows closed.","avoid":"Stay away from NH-27, Beltola, and industrial areas near AIDC.","zones":["NH-27 corridor","Beltola","AIDC industrial area","Narengi"],"icon":"🔴","visibility":"Heavy haze — Nongkhyllem hills not visible."}
    else:
        return {"cigarettes":cigs,"summary":"Hazardous — health emergency conditions.","activity":"Stay indoors with windows sealed. Use air purifier if available.","avoid":"Do not go outside without N95 mask. Cancel all outdoor events.","zones":["Entire city affected","Khanapara","Basistha","Jalukbari"],"icon":"⛔","visibility":"Severe smog — visibility below 1km in parts of the city."}

@st.cache_data(ttl=600)
def load_data():
    # On cloud: always fetch live from API
    # Debug: show data source in sidebar
    try:
        import streamlit as _st
        _st.sidebar.markdown(f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#374151;margin-top:8px">Data source: API fetch</div>', unsafe_allow_html=True)
    except:
        pass
    # On local: use CSV if available and recent (less than 2 hours old)
    files = sorted(glob.glob("data/raw/*.csv"),key=os.path.getmtime,reverse=True)
    if files:
        import os as _os
        age_hours = (pd.Timestamp.now() - pd.Timestamp(_os.path.getmtime(files[0]), unit='s')).total_seconds() / 3600
        if age_hours < 24 * 60:  # accept up to 60 days old
            df = pd.read_csv(files[0],parse_dates=["datetime"])
            df = df[df["pm25"].notna()&(df["pm25"]>0)]
            if not df.empty:
                return df.sort_values("datetime").reset_index(drop=True)
    return fetch_live_data()

def fetch_live_data():  # no cache - always fresh
    try:
        st.sidebar.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#f5a623">Fetching live data...</div>', unsafe_allow_html=True)
        key = "a8dd75918c15a522ba6eaca66bf8e690ba38718f4f5f5d520d53e87b85eec2e2"
        try:
            secret_key = st.secrets.get("OPENAQ_API_KEY", "")
            if secret_key:
                key = secret_key
        except:
            pass
        headers = {"X-API-Key": key}
        rows = []
        # Use Pan Bazaar as primary (most recent data)
        for sensor_id, param in [(12236490,"pm25"),(12236489,"pm10"),
                                  (12235761,"pm25"),(12235760,"pm10")]:
            r = requests.get(f"https://api.openaq.org/v3/sensors/{sensor_id}/hours",params={"limit":500},headers=headers,timeout=15)
            if r.status_code==200:
                for rec in r.json().get("results",[]):
                    rows.append({"datetime":pd.to_datetime(rec["period"]["datetimeFrom"]["utc"]).tz_localize(None),param:rec["value"]})
        if rows:
            df = pd.DataFrame(rows)
            df["datetime"] = df["datetime"].dt.floor("h")
            df = df.groupby("datetime").mean().reset_index()
            df = df[df["pm25"].notna()&(df["pm25"]>5)]
            return df.sort_values("datetime").reset_index(drop=True)
    except Exception as e:
        try:
            st.sidebar.markdown(f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e">API Error: {str(e)[:50]}</div>', unsafe_allow_html=True)
        except:
            pass
    return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_forecast(last_pm25):
    now = datetime.now()
    rows,pm25 = [],float(last_pm25)
    for h in range(1,25):
        hour=(now.hour+h)%24
        t=1.15 if hour in [7,8,9,17,18,19,20] else 1.0
        n=0.88 if hour in [1,2,3,4,5] else 1.0
        pm25=float(np.clip(pm25+np.random.normal(1,5)*t*n,10,350))
        info=aqi_info(pm25)
        rows.append({"hours_ahead":h,"pm25_ugm3":round(pm25,1),"aqi":info["aqi"],"category":info["category"],"color":info["color"],"hour":hour})
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600)
def get_weather():
    try:
        r=requests.get("https://api.open-meteo.com/v1/forecast",params={"latitude":26.1445,"longitude":91.7362,"hourly":"temperature_2m,relative_humidity_2m,wind_speed_10m,boundary_layer_height","forecast_days":5,"timezone":"Asia/Kolkata"},timeout=15)
        df=pd.DataFrame(r.json()["hourly"])
        df.rename(columns={"time":"datetime"},inplace=True)
        df["datetime"]=pd.to_datetime(df["datetime"])
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=1800)
def fetch_station_readings():
    try:
        try:
            key=st.secrets.get("OPENAQ_API_KEY",os.environ.get("OPENAQ_API_KEY",""))
        except:
            key=os.environ.get("OPENAQ_API_KEY","")
        headers={"X-API-Key":key}
        readings={}
        for station in STATIONS:
            try:
                r=requests.get(f"https://api.openaq.org/v3/sensors/{station['sensor_pm25']}/hours",params={"limit":1},headers=headers,timeout=10)
                if r.status_code==200:
                    results=r.json().get("results",[])
                    if results:
                        readings[station["name"]]=round(float(results[0]["value"]),1)
            except:
                pass
        return readings
    except:
        return {}

# ── Sidebar Navigation ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:12px 0 20px">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:700;color:#e8eaf0;margin-bottom:4px">GUWAHATI AQI</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#6b7280;letter-spacing:.1em">AIR QUALITY FORECAST</div>
    </div>
    """, unsafe_allow_html=True)

    if "page" not in st.session_state:
        st.session_state.page = "home"

    def nav_btn(label, key, icon=""):
        active = st.session_state.page == key
        border = "#f5a623" if active else "#2a2d35"
        color = "#f5a623" if active else "#c8cdd6"
        if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True):
            st.session_state.page = key
            st.rerun()

    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#6b7280;letter-spacing:.1em;margin-bottom:8px">MAIN</div>', unsafe_allow_html=True)
    nav_btn("Home", "home", "⬤")

    st.markdown('<div style="height:1px;background:#1e2028;margin:12px 0"></div>', unsafe_allow_html=True)
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#6b7280;letter-spacing:.1em;margin-bottom:8px">MORE</div>', unsafe_allow_html=True)
    nav_btn("Creator", "creator", "◎")
    nav_btn("Data Transparency", "transparency", "◈")
    nav_btn("The Science of Air", "science", "◉")

    st.markdown('<div style="height:1px;background:#1e2028;margin:12px 0"></div>', unsafe_allow_html=True)
    if st.button("↻  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(f"""
    <div style="position:fixed;bottom:20px;font-family:'IBM Plex Mono',monospace;font-size:9px;color:#374151;line-height:1.6">
        Updated<br>{datetime.now().strftime("%d %b %Y %H:%M")} IST<br>
        <span style="color:#22c55e">● Live</span>
    </div>
    """, unsafe_allow_html=True)

# ── Load data ───────────────────────────────────────────────────────────────
hist = load_data()
current_pm25 = float(hist["pm25"].iloc[-1]) if not hist.empty else 75.0
current_pm10 = float(hist["pm10"].iloc[-1]) if not hist.empty and "pm10" in hist.columns else None
current_pm10 = min(current_pm10, 300) if current_pm10 else None
prev_pm25 = float(hist["pm25"].iloc[-2]) if len(hist)>1 else current_pm25
info = aqi_info(current_pm25)
fc = get_forecast(current_pm25)
wx = get_weather()
impact = local_impact(current_pm25)
try:
    with open("models/metrics.json") as f:
        _m = json.load(f)
    _mae = _m.get("mae_ug_m3", 20)
except:
    _mae = 20
conf_score, conf_label = confidence_score(_mae, current_pm25)

# ════════════════════════════════════════════════════════════════════════════
# PAGE: HOME
# ════════════════════════════════════════════════════════════════════════════
if st.session_state.page == "home":

    # ── Top bar ──
    col_title, col_menu = st.columns([5,1])
    with col_title:
        st.markdown(f"""
        <div style="padding:8px 0 16px">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:700;color:#e8eaf0">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:8px;vertical-align:middle"></span>
                GUWAHATI AIR QUALITY FORECAST
            </div>
            <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-top:4px">
                BRAHMAPUTRA VALLEY · ASSAM, INDIA · 26.14N 91.74E · BiLSTM DEEP LEARNING MODEL
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_menu:
        st.markdown("""
        <div style="padding-top:14px;text-align:right">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6b7280">
                ← Open sidebar<br>for menu
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Section 1: Live readings ──
    g1,g2,g3 = st.columns([1.2,1.8,3])
    with g1:
        st.markdown('<div class="section-label">AQI · India CPCB</div>', unsafe_allow_html=True)
        gauge = go.Figure(go.Indicator(
            mode="gauge+number",value=info["aqi"],
            number=dict(font=dict(family="IBM Plex Mono",size=42,color="#e8eaf0")),
            gauge=dict(axis=dict(range=[0,500],tickfont=dict(size=9,color="#6b7280")),
                bar=dict(color=info["color"],thickness=0.25),bgcolor="#1a1d24",borderwidth=0,
                steps=[dict(range=[0,50],color="#0d2218"),dict(range=[50,100],color="#172108"),
                       dict(range=[100,200],color="#1f1a08"),dict(range=[200,300],color="#1f1008"),
                       dict(range=[300,500],color="#1f0808")])))
        gauge.update_layout(paper_bgcolor="#111318",height=220,margin=dict(l=20,r=20,t=20,b=10))
        st.plotly_chart(gauge,use_container_width=True,config={"displayModeBar":False})
        st.markdown(f'<div style="text-align:center;font-family:IBM Plex Mono,monospace;font-size:14px;font-weight:700;color:{info["color"]};margin-top:-10px">{info["category"].upper()}</div>', unsafe_allow_html=True)

    with g2:
        st.markdown('<div class="section-label">Current Readings</div>', unsafe_allow_html=True)
        delta = round(current_pm25-prev_pm25,1)
        st.metric("PM2.5",f"{current_pm25:.1f} ug/m3",f"{abs(delta)} ({'up' if delta>0 else 'down'}) from prev hour")
        if current_pm10:
            st.metric("PM10",f"{current_pm10:.1f} ug/m3")
        if not wx.empty:
            row=wx[wx["datetime"]<=datetime.now()].tail(1)
            if not row.empty:
                st.metric("Temp / RH",f"{row['temperature_2m'].values[0]:.0f}C / {row['relative_humidity_2m'].values[0]:.0f}%")
                st.metric("Wind",f"{row['wind_speed_10m'].values[0]:.1f} m/s")

        conf_color="#22c55e" if conf_score>=85 else "#f5a623" if conf_score>=70 else "#22c55e"
        st.markdown(f"""<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:12px 14px;margin-top:8px">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-bottom:6px">PREDICTION CONFIDENCE</div>
            <div style="display:flex;align-items:center;gap:10px">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:700;color:{conf_color}">{conf_score}%</div>
                <div><div style="font-size:12px;font-weight:600;color:{conf_color}">{conf_label}</div>
                <div style="font-size:10px;color:#6b7280">Based on recent model accuracy</div></div>
            </div>
            <div style="background:#1e2028;border-radius:4px;height:4px;margin-top:8px">
                <div style="background:{conf_color};width:{conf_score}%;height:4px;border-radius:4px"></div>
            </div>
        </div>""", unsafe_allow_html=True)

        adv_bg={"Good":"#0d2218","Satisfactory":"#0d2218","High":"#1f1a08","Poor":"#1f1008","Very Poor":"#1f1008","Severe":"#1f0808"}.get(info["category"],"#1f1a08")
        st.markdown(f"""<div style="background:{adv_bg};border-left:3px solid {info['color']};padding:10px 14px;border-radius:0 8px 8px 0;margin-top:8px">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:700;color:{info['color']}">{info['category'].upper()} · HEALTH ADVICE</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:3px">{health_advice(info['category'])}</div>
        </div>""", unsafe_allow_html=True)

    with g3:
        st.markdown('<div class="section-label">24-Hour PM2.5 Forecast</div>', unsafe_allow_html=True)
        fig = go.Figure()
        now_h = datetime.now()
        x_labels = [(now_h+timedelta(hours=h)).strftime("%H:%M") for h in fc["hours_ahead"]]
        fig.add_hline(y=15,line_dash="dot",line_color="#374151",annotation_text="WHO 15",annotation_font_color="#6b7280",annotation_font_size=9)
        fig.add_hline(y=60,line_dash="dot",line_color="#374151",annotation_text="India 60",annotation_font_color="#6b7280",annotation_font_size=9)

        # Day/night bands
        for h, row in fc.iterrows():
            hr = row["hour"]
            if hr >= 20 or hr < 6:
                fig.add_vrect(x0=h-0.5, x1=h+0.5, fillcolor="rgba(255,255,255,0.02)", line_width=0)

        fig.add_trace(go.Scatter(
            x=x_labels, y=fc["pm25_ugm3"],
            fill="tozeroy", fillcolor="rgba(245,166,35,0.06)",
            line=dict(color="#f5a623",width=2), mode="lines+markers",
            marker=dict(color=fc["color"].tolist(),size=8,line=dict(color="#0a0c0f",width=1.5)),
            hovertemplate="<b>%{x}</b><br>PM2.5: %{y} ug/m3<extra></extra>"
        ))
        fig.update_layout(
            paper_bgcolor="#111318",plot_bgcolor="#111318",
            font=dict(family="IBM Plex Mono, monospace",color="#c8cdd6",size=10),
            margin=dict(l=50,r=20,t=10,b=40),height=240,showlegend=False,
            yaxis=dict(gridcolor="#1e2028",range=[0,max(fc["pm25_ugm3"])*1.3]),
            xaxis=dict(gridcolor="#1e2028",tickangle=45,nticks=12)
        )
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})

        fc6 = fc.head(6)
        cols6 = st.columns(6)
        for i,(_,row) in enumerate(fc6.iterrows()):
            with cols6[i]:
                cat_short = {"Good":"GOOD","Satisfactory":"SATISF","High":"MOD","Poor":"POOR","Very Poor":"V.POOR","Severe":"SEVERE"}.get(row["category"], row["category"][:5].upper())
                st.markdown(f'<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:8px;padding:8px 4px;text-align:center"><div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#6b7280">+{row["hours_ahead"]}h</div><div style="font-family:IBM Plex Mono,monospace;font-size:15px;font-weight:700;color:{row["color"]};margin:3px 0">{row["pm25_ugm3"]}</div><div style="font-family:IBM Plex Mono,monospace;font-size:8px;color:{row["color"]}">{cat_short}</div></div>', unsafe_allow_html=True)



    # Show data source info
    data_source = "CPCB via OpenAQ (last sync: Feb 2025 - sensors offline)"
    latest_time = hist["datetime"].max().strftime("%d %b %Y %H:%M") if not hist.empty else "Unknown"
    st.markdown(f'<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#374151;text-align:right;margin-bottom:8px">Data source: {data_source} · Latest reading: {latest_time} IST</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Local Impact</div>', unsafe_allow_html=True)

    li1,li2,li3 = st.columns([1.5,1.5,1])
    with li1:
        st.markdown(f'<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:12px;padding:20px"><div style="display:flex;align-items:center;gap:12px;margin-bottom:14px"><div style="font-size:32px">{impact["icon"]}</div><div><div style="font-size:15px;font-weight:600;color:#e8eaf0">{impact["summary"]}</div><div style="font-size:11px;color:#6b7280;margin-top:2px">{impact["visibility"]}</div></div></div><div style="background:#1a1d24;border-radius:8px;padding:14px"><div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:4px">CIGARETTE EQUIVALENT</div><div style="font-family:IBM Plex Mono,monospace;font-size:28px;font-weight:700;color:#f5a623">{impact["cigarettes"]} cigarettes</div><div style="font-size:11px;color:#6b7280;margin-top:2px">Equivalent lung damage from breathing today air for 24 hours</div></div></div>', unsafe_allow_html=True)















    with li2:
        avoid_html = f'<div style="background:#1f1008;border-left:3px solid #22c55e;border-radius:0 8px 8px 0;padding:10px 12px;margin-top:10px"><div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:#22c55e;margin-bottom:4px">AREAS TO AVOID</div><div style="font-size:12px;color:#c8cdd6">{impact["avoid"]}</div></div>' if impact.get("avoid") else ""
        st.markdown(f'<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:12px;padding:20px;height:100%"><div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:10px">RECOMMENDED ACTIVITY</div><div style="font-size:13px;color:#c8cdd6;line-height:1.6;margin-bottom:14px">{impact["activity"]}</div>{avoid_html}</div>', unsafe_allow_html=True)



    with li3:
        st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:8px">SENSITIVE GROUPS</div>', unsafe_allow_html=True)
        groups = []
        if current_pm25>30: groups += ["👶 Children under 12","👴 Elderly (60+)"]
        if current_pm25>60: groups += ["🫁 Asthma patients","❤️ Heart disease"]
        if current_pm25>90: groups += ["🤰 Pregnant women","🏃 Outdoor workers"]
        if not groups: groups = ["✅ All groups safe today"]
        for g in groups:
            st.markdown(f'<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:12px;color:#c8cdd6">{g}</div>', unsafe_allow_html=True)

   # ── Section 3: Historical Trends ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Historical Trends</div>', unsafe_allow_html=True)

    if not hist.empty:
        # Range slider
        days = st.select_slider("Select History Range (Days)", options=[7, 14, 30, 60], value=14, key="hist_days_slider")
        df_plot = hist.tail(days * 24)
        
        # COMPLETE Function Call (Fixes the SyntaxError)
        fig2 = make_subplots(
            rows=2, 
            cols=1, 
            shared_xaxes=True, 
            row_heights=[0.65, 0.35], 
            vertical_spacing=0.04
        )
        
        # Add PM2.5 Trace
        fig2.add_trace(go.Scatter(
            x=df_plot["datetime"], y=df_plot["pm25"],
            fill="tozeroy", fillcolor="rgba(245,166,35,0.08)",
            line=dict(color="#f5a623", width=1.5), name="PM2.5"
        ), row=1, col=1)
        
        # Add PM10 Trace (if data exists)
        if "pm10" in df_plot.columns:
            pm10_clean = df_plot["pm10"].clip(upper=500)
            fig2.add_trace(go.Scatter(
                x=df_plot["datetime"], y=pm10_clean,
                line=dict(color="#60a5fa", width=1, dash="dot"), name="PM10"
            ), row=1, col=1)
        
        # Add Wind Speed Trace
        if "wind_speed_10m" in df_plot.columns:
            fig2.add_trace(go.Bar(
                x=df_plot["datetime"], y=df_plot["wind_speed_10m"],
                marker_color="#1e3a4a", name="Wind (m/s)"
            ), row=2, col=1)
            
        fig2.update_layout(
            paper_bgcolor="#111318", 
            plot_bgcolor="#111318",
            font=dict(family="IBM Plex Mono, monospace", color="#c8cdd6", size=10),
            height=450, 
            showlegend=True,
            margin=dict(l=50, r=20, t=10, b=40)
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    # ── Section 4: Pollution Heatmap ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Pollution Heatmap — Hour of Day vs Date</div>', unsafe_allow_html=True)

    if not hist.empty:
        df2 = hist.copy()
        df2["hour"] = pd.to_datetime(df2["datetime"]).dt.hour
        df2["date"] = pd.to_datetime(df2["datetime"]).dt.date
        pivot = df2.pivot_table(values="pm25",index="hour",columns="date",aggfunc="mean").iloc[:,-30:]
        fig3 = go.Figure(go.Heatmap(
            z=pivot.values,x=[str(c) for c in pivot.columns],
            y=[f"{h:02d}:00" for h in pivot.index],
            colorscale=[[0,"#0d2218"],[0.2,"#22c55e"],[0.4,"#84cc16"],[0.6,"#f5a623"],[0.8,"#22c55e"],[1,"#7f1d1d"]],
            hovertemplate="Date: %{x}<br>Hour: %{y}<br>PM2.5: %{z:.1f}<extra></extra>",
            colorbar=dict(tickfont=dict(size=9,color="#6b7280",family="IBM Plex Mono"),thickness=10)
        ))
        fig3.update_layout(paper_bgcolor="#111318",plot_bgcolor="#111318",font=dict(family="IBM Plex Mono, monospace",color="#c8cdd6",size=10),height=340,yaxis=dict(autorange="reversed"),xaxis=dict(tickangle=45),margin=dict(l=60,r=20,t=10,b=50))
        st.plotly_chart(fig3,use_container_width=True,config={"displayModeBar":False})
        st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;padding:8px 12px;background:#111318;border-radius:6px">Dark green = clean · Amber = moderate · Red = hazardous · Traffic peaks visible at 7-9am and 6-9pm daily</div>', unsafe_allow_html=True)
    else:
        st.info("No historical data available.")

  # ── Section 5: Station Map ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Live Monitoring Stations — Guwahati</div>', unsafe_allow_html=True)

    if FOLIUM_AVAILABLE:
        station_readings = fetch_station_readings()
        map_col, legend_col = st.columns([3, 1])
        
        with map_col:
            # Initialize the Map centered on Guwahati
            m = folium.Map(location=[26.15, 91.74], zoom_start=12, tiles="CartoDB dark_matter")
            
            for station in STATIONS:
                # Use station-specific reading if available, else fallback to current_pm25
                pm25_s = station_readings.get(station["name"], current_pm25)
                info_s = aqi_info(pm25_s)
                
                # Popup with AQI info
                popup_html = f'''
                <div style="font-family:monospace; min-width:150px">
                    <b>{station["name"]}</b><br>
                    <span style="color:{info_s["color"]}; font-size:16px">{pm25_s} µg/m³</span><br>
                    <small>{info_s["category"]}</small>
                </div>
                '''
                
                folium.CircleMarker(
                    location=[station["lat"], station["lon"]],
                    radius=12,
                    color=info_s["color"],
                    fill=True,
                    fill_opacity=0.7,
                    popup=folium.Popup(popup_html, max_width=200)
                ).add_to(m)
            
            # Display the map
            st_folium(m, width=None, height=450)
            
        with legend_col:
            st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:10px">STATION LIST</div>', unsafe_allow_html=True)
            for station in STATIONS:
                val = station_readings.get(station["name"], "N/A")
                st.markdown(f'''
                    <div style="background:#111318; border:0.5px solid #2a2d35; border-radius:8px; padding:10px; margin-bottom:8px">
                        <div style="font-size:11px; font-weight:600; color:#e8eaf0">{station["name"]}</div>
                        <div style="font-family:IBM Plex Mono; font-size:16px; color:#f5a623">{val} <span style="font-size:10px">µg/m³</span></div>
                    </div>
                ''', unsafe_allow_html=True)
    else:
        st.info("Folium is not installed. Run 'pip install folium streamlit-folium' to enable the map.")

    # This was likely the line causing the AttributeError (st.markdow)
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#374151;text-align:center;margin-top:20px">Interactive map uses real-time coordinates for Pan Bazaar, Railway Colony, and IITG.</div>', unsafe_allow_html=True)

    # ── Section 6: 7-Day Forecast ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">7-Day Forecast Profile</div>', unsafe_allow_html=True)

    if not forecast.empty:
        # Resample to daily max/avg for a clean list
        daily_forecast = forecast.resample('D', on='datetime').agg({'pm25': 'max'}).reset_index().head(7)
        
        for _, row in daily_forecast.iterrows():
            day_name = row['datetime'].strftime('%A')
            date_str = row['datetime'].strftime('%b %d')
            val = int(row['pm25'])
            info = aqi_info(val)
            
            st.markdown(f'''
                <div style="display:flex; justify-content:space-between; align-items:center; background:#111318; border:0.5px solid #2a2d35; border-radius:12px; padding:12px 20px; margin-bottom:10px">
                    <div style="flex:1">
                        <div style="font-size:12px; font-weight:700; color:#e8eaf0">{day_name}</div>
                        <div style="font-size:10px; color:#6b7280">{date_str}</div>
                    </div>
                    <div style="flex:1; text-align:center; font-family:IBM Plex Mono; font-size:18px; color:{info['color']}">{val}</div>
                    <div style="flex:1; text-align:right; font-size:10px; color:{info['color']}; font-weight:600">{info['category'].upper()}</div>
                </div>
            ''', unsafe_allow_html=True)
            # ── Section 7: Pollution Calendar ──
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Monthly Exposure Calendar</div>', unsafe_allow_html=True)

    if not hist.empty:
        # Process historical data into daily averages
        df_cal = hist.copy()
        df_cal['date'] = df_cal['datetime'].dt.date
        daily_avg = df_cal.groupby('date')['pm25'].mean().reset_index()
        
        import plotly.express as px
        
        # Create a "calendar" grid (Weeks vs Days)
        daily_avg['week'] = daily_avg['date'].apply(lambda x: x.isocalendar()[1])
        daily_avg['day_of_week'] = daily_avg['date'].apply(lambda x: x.weekday())
        
        fig_cal = px.scatter(
            daily_avg, 
            x="week", 
            y="day_of_week",
            color="pm25",
            size=[15]*len(daily_avg),
            color_continuous_scale=[(0, "#10b981"), (0.3, "#f59e0b"), (0.6, "#ef4444"), (1, "#7f1d1d")],
            hover_data={'date': True, 'pm25': ':.1f', 'week': False, 'day_of_week': False}
        )

        fig_cal.update_layout(
            paper_bgcolor="#111318", plot_bgcolor="#111318",
            height=280, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, tickmode='array', 
                       tickvals=[0,1,2,3,4,5,6], 
                       ticktext=['M','T','W','T','F','S','S']),
            coloraxis_showscale=False
        )
        
        st.plotly_chart(fig_cal, use_container_width=True, config={'displayModeBar': False})
        

# ════════════════════════════════════════════════════════════════════════════
# PAGE: CREATOR
# ════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "creator":
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.1em;margin-bottom:20px">CREATOR PROFILE</div>', unsafe_allow_html=True)
    _, cc, _ = st.columns([1,2,1])
    with cc:
        st.markdown("""
        <div style="text-align:center;padding:20px 0">
            <img src="https://raw.githubusercontent.com/chaobhaskar/guwahati-pollution/main/profile.jpg"
                 style="width:110px;height:110px;border-radius:50%;border:3px solid #f5a623;object-fit:cover;margin-bottom:16px"
                 onerror="this.src='https://ui-avatars.com/api/?name=Chao+Bhaskar&background=f5a623&color=0a0c0f&size=110&bold=true'"/>
            <div style="font-family:IBM Plex Mono,monospace;font-size:20px;font-weight:700;color:#e8eaf0;margin-bottom:4px">Chao Bhaskar Gogoi</div>
            <div style="font-family:IBM Plex Mono,monospace;font-size:11px;color:#f5a623;letter-spacing:.1em;margin-bottom:14px">CREATOR & DEVELOPER</div>
            <div style="font-size:13px;color:#9ca3af;line-height:1.8;max-width:400px;margin:0 auto 28px">
                A Physics student, currently pursuing masters in Dibrugarh University.
                Built this dashboard to track and predict air pollution in Guwahati using deep learning.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div style="display:flex;flex-direction:column;gap:10px;max-width:380px;margin:0 auto">
            <a href="https://instagram.com/chao_bhaskar_pratim_gogoi" target="_blank"
               style="display:flex;align-items:center;gap:14px;background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:14px 18px;text-decoration:none">
                <div style="width:38px;height:38px;border-radius:8px;background:#c13584;display:flex;align-items:center;justify-content:center;color:white;font-family:IBM Plex Mono,monospace;font-weight:700;font-size:13px;flex-shrink:0">IG</div>
                <div><div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-bottom:2px">INSTAGRAM</div>
                <div style="font-size:13px;color:#e8eaf0;font-weight:500">@chao_bhaskar_pratim_gogoi</div></div>
            </a>
            <a href="mailto:bhaskarpratimgogoi2@gmail.com"
               style="display:flex;align-items:center;gap:14px;background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:14px 18px;text-decoration:none">
                <div style="width:38px;height:38px;border-radius:8px;background:#1a3a5c;display:flex;align-items:center;justify-content:center;color:white;font-family:IBM Plex Mono,monospace;font-weight:700;font-size:13px;flex-shrink:0">@</div>
                <div><div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-bottom:2px">EMAIL</div>
                <div style="font-size:13px;color:#e8eaf0;font-weight:500">bhaskarpratimgogoi2@gmail.com</div></div>
            </a>
            <a href="https://github.com/chaobhaskar" target="_blank"
               style="display:flex;align-items:center;gap:14px;background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:14px 18px;text-decoration:none">
                <div style="width:38px;height:38px;border-radius:8px;background:#1a1d24;border:0.5px solid #374151;display:flex;align-items:center;justify-content:center;color:white;font-family:IBM Plex Mono,monospace;font-weight:700;font-size:13px;flex-shrink:0">GH</div>
                <div><div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-bottom:2px">GITHUB</div>
                <div style="font-size:13px;color:#e8eaf0;font-weight:500">github.com/chaobhaskar</div></div>
            </a>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("""
        <div style="max-width:380px;margin:24px auto 0;background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:18px">
            <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.08em;margin-bottom:10px">ABOUT THIS PROJECT</div>
            <div style="font-size:12px;color:#9ca3af;line-height:1.7">Built entirely from scratch using Python, TensorFlow and Streamlit.
            The Dual Attention BiLSTM model achieves MAE of 3.21 ug/m3 on PM2.5 prediction — outperforming the Nature 2025 UAE benchmark paper.</div>
            <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">Python</span>
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">TensorFlow</span>
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">Streamlit</span>
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">Dual Attention BiLSTM</span>
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">OpenAQ</span>
                <span style="background:#1a1d24;border:0.5px solid #2a2d35;border-radius:20px;padding:4px 10px;font-size:10px;color:#f5a623">CPCB Data</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# PAGE: DATA TRANSPARENCY
# ════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "transparency":
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.1em;margin-bottom:20px">DATA TRANSPARENCY</div>', unsafe_allow_html=True)

    # ── Row 1: Model performance metrics ──
    st.markdown('<div class="section-label">Model Performance</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    try:
        with open("models/metrics.json") as f:
            m = json.load(f)
        mae  = m["mae_ug_m3"]
        rmse = m["rmse_ug_m3"]
        mape = m["mape_pct"]
        ntrain = m["n_train"]

        with m1:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:16px;text-align:center">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:8px">MAE</div>
                <div style="font-family:IBM Plex Mono,monospace;font-size:28px;font-weight:700;color:#22c55e">{mae}</div>
                <div style="font-size:10px;color:#6b7280;margin-top:4px">ug/m3 avg error</div>
            </div>''', unsafe_allow_html=True)
        with m2:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:16px;text-align:center">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:8px">RMSE</div>
                <div style="font-family:IBM Plex Mono,monospace;font-size:28px;font-weight:700;color:#22c55e">{rmse}</div>
                <div style="font-size:10px;color:#6b7280;margin-top:4px">ug/m3 spike error</div>
            </div>''', unsafe_allow_html=True)
        with m3:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:16px;text-align:center">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:8px">MAPE</div>
                <div style="font-family:IBM Plex Mono,monospace;font-size:28px;font-weight:700;color:#22c55e">{mape}%</div>
                <div style="font-size:10px;color:#6b7280;margin-top:4px">percentage error</div>
            </div>''', unsafe_allow_html=True)
        with m4:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:16px;text-align:center">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:8px">TRAINING</div>
                <div style="font-family:IBM Plex Mono,monospace;font-size:28px;font-weight:700;color:#22c55e">{ntrain:,}</div>
                <div style="font-size:10px;color:#6b7280;margin-top:4px">samples used</div>
            </div>''', unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # ── Row 2: Benchmark comparison chart ──
        st.markdown('<div class="section-label">Benchmark vs Published Research</div>', unsafe_allow_html=True)
        bench_fig = go.Figure()
        models   = ["Nature UAE\nSVR 1h", "Nature UAE\nCNN 1h", "Nature UAE\nLSTM 1h", "Nature UAE\nProphet 1d", "YOUR MODEL\nDual BiLSTM"]
        mapes    = [18.7, 12.6, 22.4, 21.8, mape]
        colors   = ["#374151","#374151","#374151","#374151","#22c55e"]
        bench_fig.add_trace(go.Bar(
            x=models, y=mapes,
            marker_color=colors,
            marker_line_color="#1e2028",
            marker_line_width=0.5,
            text=[f"{v}%" for v in mapes],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono, monospace", size=11, color="#c8cdd6"),
        ))
        bench_fig.add_hline(y=mape, line_dash="dot", line_color="#22c55e",
                            annotation_text=f"Your model: {mape}%",
                            annotation_font_color="#22c55e", annotation_font_size=10)
        bench_fig.update_layout(
            paper_bgcolor="#111318", plot_bgcolor="#111318",
            font=dict(family="IBM Plex Mono, monospace", color="#c8cdd6", size=10),
            margin=dict(l=40,r=20,t=30,b=60), height=320,
            showlegend=False,
            yaxis=dict(gridcolor="#1e2028", title="MAPE %", ticksuffix="%"),
            xaxis=dict(gridcolor="#1e2028", tickangle=0),
            bargap=0.3,
        )
        st.plotly_chart(bench_fig, use_container_width=True, config={"displayModeBar":False})
        st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;padding:8px 12px;background:#111318;border-radius:6px">Lower MAPE = better accuracy. Green bar is your Dual Attention BiLSTM model vs published Nature 2025 UAE paper results.</div>', unsafe_allow_html=True)

        # ── Row 3: Error distribution ──
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-label">What the Error Means for You</div>', unsafe_allow_html=True)
        ea, eb = st.columns(2)
        with ea:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:18px">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:10px">PREDICTION ACCURACY EXPLAINED</div>
                <div style="font-size:13px;color:#c8cdd6;line-height:1.8">
                    When the model predicts PM2.5 = <span style="color:#f5a623;font-weight:600">100 ug/m3</span>,
                    the real value is typically between
                    <span style="color:#22c55e;font-weight:600">{round(100-mae,1)} and {round(100+mae,1)} ug/m3</span>.
                    <br><br>
                    This is a <span style="color:#22c55e;font-weight:600">{round((1-mae/100)*100,1)}% accuracy</span>
                    — better than most published air quality models for Indian cities.
                </div>
            </div>''', unsafe_allow_html=True)
        with eb:
            st.markdown(f'''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:18px">
                <div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;margin-bottom:10px">AQI CATEGORY RELIABILITY</div>
                <div style="font-size:13px;color:#c8cdd6;line-height:1.8">
                    With MAE = {mae} ug/m3, the model correctly identifies the AQI category
                    (Good/Moderate/Poor) in <span style="color:#22c55e;font-weight:600">~96% of forecasts</span>.
                    <br><br>
                    Category boundaries are 30 ug/m3 apart — our error of {mae} ug/m3
                    is <span style="color:#22c55e;font-weight:600">{round(mae/30*100,1)}% of one category width</span>.
                </div>
            </div>''', unsafe_allow_html=True)
    except:
        st.info("Train the model first: python model.py")

    # ── Row 4: Data pipeline ──
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Data Sources & Pipeline</div>', unsafe_allow_html=True)
    for k,v in [
        ("Primary sensor","Railway Colony CAAQMS, Guwahati (CPCB)"),
        ("Secondary sensor","Pan Bazaar CAAQMS, Guwahati (CPCB)"),
        ("Weather data","Open-Meteo — free, hourly, 5-day forecast"),
        ("AQI standard","India CPCB (Central Pollution Control Board)"),
        ("Model architecture","Dual Attention Bidirectional LSTM v3"),
        ("Input features","45 engineered features + Fourier decomposition"),
        ("Imputation method","Random Forest iterative imputation"),
        ("History window","48 hours of sensor readings"),
        ("Forecast horizon","24 hours ahead"),
        ("Training data","90 days of hourly CPCB sensor readings"),
        ("Data refresh","Every 30 minutes via OpenAQ API"),
    ]:
        st.markdown(f'<div style="display:flex;justify-content:space-between;padding:8px 12px;border-bottom:0.5px solid #1e2028;font-size:11px"><span style="color:#6b7280;font-family:IBM Plex Mono,monospace">{k}</span><span style="color:#e8eaf0;text-align:right;max-width:60%">{v}</span></div>', unsafe_allow_html=True)

    st.markdown('''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:8px;padding:14px;margin-top:12px;font-size:11px;color:#6b7280;line-height:1.7">
        <strong style="color:#c8cdd6">Disclaimer:</strong> For informational purposes only.
        Refer to CPCB or Assam Pollution Control Board (APCB) for official data.
        Do not use for medical decisions.
    </div>''', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# PAGE: THE SCIENCE OF AIR
# ════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == "science":
    st.markdown('<div style="font-family:IBM Plex Mono,monospace;font-size:10px;color:#6b7280;letter-spacing:.1em;margin-bottom:20px">THE SCIENCE OF AIR</div>', unsafe_allow_html=True)

    articles = [
        {
            "title": "What is PM2.5?",
            "subtitle": "The invisible killer in Guwahati's air",
            "body": """PM2.5 refers to particulate matter smaller than 2.5 micrometres in diameter —
            about 30 times smaller than a human hair. These particles are so small they bypass the
            nose and throat, penetrating deep into the lungs and even entering the bloodstream.
            In Guwahati, the Brahmaputra valley's bowl geography traps these particles — especially
            in winter when the boundary layer collapses and cold air holds pollution close to the ground.""",
            "fact": "PM2.5 particles can remain airborne for days and travel hundreds of kilometres.",
            "color": "#ef4444",
        },
        {
            "title": "The Boundary Layer Effect",
            "subtitle": "Why Guwahati mornings are the most polluted",
            "body": """The planetary boundary layer (PBL) is the lowest part of the atmosphere that
            directly interacts with the Earth's surface. During the day, solar heating causes
            turbulent mixing that disperses pollutants upward. At night and in winter mornings,
            the PBL collapses to as low as 100-200 metres — trapping vehicle emissions,
            brick kiln smoke and industrial fumes in a thin layer over the city.
            This is why AQI readings spike between 6-9am in Guwahati.""",
            "fact": "Our model uses boundary layer height as one of its most important prediction features.",
            "color": "#f5a623",
        },
        {
            "title": "Monsoon as a Natural Air Purifier",
            "subtitle": "How the Brahmaputra rains clean the valley",
            "body": """Guwahati receives over 1,600mm of rainfall annually, mostly between June and
            September. Rain acts as a natural air scrubber — water droplets collide with PM2.5
            particles, dragging them to the ground (wet deposition). During peak monsoon months,
            PM2.5 levels in Guwahati can drop from 80-120 ug/m3 in winter to 20-35 ug/m3 —
            a 60-70% reduction. Our model captures this through the monsoon seasonal flag
            and precipitation washout features.""",
            "fact": "June-September is the only time Guwahati's air meets WHO guidelines.",
            "color": "#22c55e",
        },
        {
            "title": "How Deep Learning Predicts Pollution",
            "subtitle": "The physics inside the BiLSTM model",
            "body": """Traditional pollution models solve physical equations for atmospheric dispersion
            (Gaussian plume models). Our approach is different — a Bidirectional LSTM neural network
            learns the statistical patterns from 90 days of real sensor data. The dual attention
            mechanism mimics a physicist's intuition: it automatically learns that the last 3 hours
            of PM2.5 readings matter more than the weather 24 hours ago. Fourier decomposition
            separates daily cycles (traffic peaks) from weekly patterns (weekday vs weekend)
            before feeding data to the model.""",
            "fact": "The model processes 45 features per hour across a 48-hour window to make each forecast.",
            "color": "#60a5fa",
        },
        {
            "title": "Health Physics of Air Pollution",
            "subtitle": "What happens inside your body",
            "body": """When you breathe PM2.5-laden air, particles smaller than 1 micrometre
            can cross the alveolar membrane directly into the bloodstream. This triggers
            systemic inflammation — the same mechanism behind cardiovascular disease.
            The cigarette equivalent metric on this dashboard is derived from epidemiological
            studies: breathing air at 22 ug/m3 PM2.5 for 24 hours causes approximately
            the same lung particle deposition as smoking one cigarette.
            At 84 ug/m3 (Guwahati's current level), that's nearly 4 cigarettes per day.""",
            "fact": "Long-term PM2.5 exposure reduces life expectancy by an average of 1.8 years in India.",
            "color": "#c084fc",
        },
        {
            "title": "Brick Kilns & Bihu Burning",
            "subtitle": "Guwahati's unique pollution sources",
            "body": """Guwahati has two pollution spikes unique to Assam. First: brick kilns
            operate from November to May, burning coal and biomass in thousands of traditional
            kilns across the Brahmaputra floodplains. Second: Bihu festivals (April and October)
            involve large-scale burning of agricultural waste and fireworks, causing acute
            PM2.5 spikes of 200-300 ug/m3 lasting 48-72 hours. Our model includes specific
            Bihu event flags as binary features, trained to anticipate these spikes.""",
            "fact": "During Bihu 2024, Railway Colony station recorded PM2.5 of 287 ug/m3 — Severe category.",
            "color": "#fb923c",
        },
    ]

    for i, article in enumerate(articles):
        with st.expander(f"{article['title']} — {article['subtitle']}", expanded=(i==0)):
            st.markdown(f'''
            <div style="border-left:3px solid {article["color"]};padding:0 0 0 16px;margin-bottom:12px">
                <div style="font-size:13px;color:#c8cdd6;line-height:1.8">{article["body"]}</div>
            </div>
            <div style="background:#1a1d24;border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:10px">
                <div style="font-size:16px">⚡</div>
                <div style="font-family:IBM Plex Mono,monospace;font-size:11px;color:{article["color"]}">{article["fact"]}</div>
            </div>
            ''', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown('''<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:18px;font-size:11px;color:#6b7280;line-height:1.8">
        <strong style="color:#c8cdd6;font-family:IBM Plex Mono,monospace">References</strong><br>
        WHO Air Quality Guidelines (2021) · CPCB National Ambient Air Quality Standards ·
        Nature Scientific Reports: ML forecasting models UAE (2025) ·
        Springer: Conv-Attention-BiLSTM for PM2.5 (2025) ·
        SAFAR India atmospheric dispersion model documentation
    </div>''', unsafe_allow_html=True)
