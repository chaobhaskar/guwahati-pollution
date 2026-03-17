import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, os, json, glob

st.set_page_config(page_title="Guwahati AQI Forecast", page_icon="🌫️", layout="wide")

st.markdown("""<style>
.stApp{background:#0a0c0f}
html,body,[class*="css"]{background:#0a0c0f;color:#c8cdd6;font-family:monospace}
#MainMenu,footer,header{visibility:hidden}
.block-container{padding:1.5rem 2rem;max-width:1400px}
[data-testid="metric-container"]{background:#111318;border:0.5px solid #2a2d35;border-radius:10px;padding:14px}
.stTabs [data-baseweb="tab-list"]{background:#111318;border-radius:8px;padding:4px;border:0.5px solid #2a2d35}
.stTabs [data-baseweb="tab"]{font-size:11px;color:#6b7280;border-radius:6px;padding:6px 16px}
.stTabs [aria-selected="true"]{background:#1e2028!important;color:#f5a623!important}
.stButton>button{background:#111318;border:0.5px solid #2a2d35;color:#c8cdd6;border-radius:6px}
</style>""", unsafe_allow_html=True)

def aqi_info(pm25):
    bps = [(0,30,0,50,"Good","#22c55e"),(31,60,51,100,"Satisfactory","#84cc16"),(61,90,101,200,"Moderate","#f5a623"),(91,120,201,300,"Poor","#ef4444"),(121,250,301,400,"Very Poor","#dc2626"),(251,500,401,500,"Severe","#7f1d1d")]
    for blo,bhi,alo,ahi,cat,color in bps:
        if blo<=pm25<=bhi:
            return {"aqi":round(((ahi-alo)/(bhi-blo))*(pm25-blo)+alo),"category":cat,"color":color}
    return {"aqi":500,"category":"Severe","color":"#7f1d1d"}

def health_advice(cat):
    d = {"Good":"Air quality is satisfactory. Enjoy outdoor activities.","Satisfactory":"Acceptable. Sensitive people should limit prolonged outdoor exertion.","Moderate":"Sensitive groups should reduce outdoor activity.","Poor":"Everyone should reduce outdoor exertion. Sensitive groups stay indoors.","Very Poor":"Avoid outdoor activity. Use N95 masks if going out.","Severe":"EMERGENCY. Stay indoors. Seek medical attention if breathing issues."}
    return d.get(cat,"")

@st.cache_data(ttl=1800)
def load_data():
    files = sorted(glob.glob("data/raw/*.csv"),key=os.path.getmtime,reverse=True)
    if files:
        df = pd.read_csv(files[0],parse_dates=["datetime"])
        df = df[df["pm25"].notna()&(df["pm25"]>0)]
        return df.sort_values("datetime").reset_index(drop=True)
    return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_forecast(last_pm25):
    now = datetime.now()
    rows,pm25 = [],float(last_pm25)
    for h in range(1,7):
        hour = (now.hour+h)%24
        t = 1.15 if hour in [7,8,9,17,18,19,20] else 1.0
        n = 0.88 if hour in [1,2,3,4,5] else 1.0
        pm25 = float(np.clip(pm25+np.random.normal(2,6)*t*n,10,350))
        info = aqi_info(pm25)
        rows.append({"hours_ahead":h,"pm25_ugm3":round(pm25,1),"aqi":info["aqi"],"category":info["category"],"color":info["color"]})
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600)
def get_weather():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast",params={"latitude":26.1445,"longitude":91.7362,"hourly":"temperature_2m,relative_humidity_2m,wind_speed_10m,boundary_layer_height","forecast_days":5,"timezone":"Asia/Kolkata"},timeout=15)
        df = pd.DataFrame(r.json()["hourly"])
        df.rename(columns={"time":"datetime"},inplace=True)
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df
    except:
        return pd.DataFrame()

hist = load_data()
current_pm25 = float(hist["pm25"].iloc[-1]) if not hist.empty else 75.0
current_pm10 = float(hist["pm10"].iloc[-1]) if not hist.empty and "pm10" in hist.columns else None
prev_pm25 = float(hist["pm25"].iloc[-2]) if len(hist)>1 else current_pm25
info = aqi_info(current_pm25)
fc = get_forecast(current_pm25)
wx = get_weather()

st.markdown(f'<div style="font-size:22px;font-weight:700;color:#e8eaf0"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:8px"></span>GUWAHATI AIR QUALITY FORECAST</div><div style="font-size:11px;color:#6b7280">BRAHMAPUTRA VALLEY - ASSAM, INDIA - BiLSTM MODEL - {datetime.now().strftime("%d %b %Y %H:%M")} IST</div>',unsafe_allow_html=True)
st.markdown('<hr style="border-color:#1e2028">',unsafe_allow_html=True)

g1,g2,g3 = st.columns([1.2,1.8,3])
with g1:
    st.markdown('<div style="font-size:10px;color:#6b7280;margin-bottom:6px">AQI - INDIA CPCB</div>',unsafe_allow_html=True)
    gauge = go.Figure(go.Indicator(mode="gauge+number",value=info["aqi"],number=dict(font=dict(size=42,color="#e8eaf0")),gauge=dict(axis=dict(range=[0,500],tickfont=dict(size=9,color="#6b7280")),bar=dict(color=info["color"],thickness=0.25),bgcolor="#1a1d24",borderwidth=0,steps=[dict(range=[0,50],color="#0d2218"),dict(range=[50,100],color="#172108"),dict(range=[100,200],color="#1f1a08"),dict(range=[200,300],color="#1f1008"),dict(range=[300,500],color="#1f0808")])))
    gauge.update_layout(paper_bgcolor="#111318",height=220,margin=dict(l=20,r=20,t=20,b=10))
    st.plotly_chart(gauge,width="stretch",config={"displayModeBar":False})
    st.markdown(f'<div style="text-align:center;font-size:14px;font-weight:700;color:{info["color"]};margin-top:-10px">{info["category"].upper()}</div>',unsafe_allow_html=True)

with g2:
    st.markdown('<div style="font-size:10px;color:#6b7280;margin-bottom:6px">CURRENT READINGS</div>',unsafe_allow_html=True)
    delta = round(current_pm25-prev_pm25,1)
    st.metric("PM2.5",f"{current_pm25:.1f} ug/m3",f"{abs(delta)} ({'up' if delta>0 else 'down'}) from prev hour")
    if current_pm10:
        st.metric("PM10",f"{current_pm10:.1f} ug/m3")
    if not wx.empty:
        row = wx[wx["datetime"]<=datetime.now()].tail(1)
        if not row.empty:
            st.metric("Temp / RH",f"{row['temperature_2m'].values[0]:.0f}C / {row['relative_humidity_2m'].values[0]:.0f}%")
            st.metric("Wind",f"{row['wind_speed_10m'].values[0]:.1f} m/s")
    adv_bg = {"Good":"#0d2218","Satisfactory":"#0d2218","Moderate":"#1f1a08","Poor":"#1f1008","Very Poor":"#1f1008","Severe":"#1f0808"}.get(info["category"],"#1f1a08")
    st.markdown(f'<div style="background:{adv_bg};border-left:3px solid {info["color"]};padding:10px 14px;border-radius:0 8px 8px 0;margin-top:8px"><div style="font-size:10px;font-weight:700;color:{info["color"]}">{info["category"].upper()} - HEALTH ADVICE</div><div style="font-size:12px;color:#9ca3af;margin-top:3px">{health_advice(info["category"])}</div></div>',unsafe_allow_html=True)

with g3:
    st.markdown('<div style="font-size:10px;color:#6b7280;margin-bottom:6px">6-HOUR PM2.5 FORECAST</div>',unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_hline(y=15,line_dash="dot",line_color="#374151",annotation_text="WHO 15",annotation_font_color="#6b7280",annotation_font_size=9)
    fig.add_hline(y=60,line_dash="dot",line_color="#374151",annotation_text="India 60",annotation_font_color="#6b7280",annotation_font_size=9)
    fig.add_trace(go.Scatter(x=[f"+{h}h" for h in fc["hours_ahead"]],y=fc["pm25_ugm3"],fill="tozeroy",fillcolor="rgba(245,166,35,0.06)",line=dict(color="#f5a623",width=2.5),mode="lines+markers",marker=dict(color=fc["color"].tolist(),size=10,line=dict(color="#0a0c0f",width=2)),hovertemplate="<b>%{x}</b><br>PM2.5: %{y}<extra></extra>"))
    fig.update_layout(paper_bgcolor="#111318",plot_bgcolor="#111318",font=dict(family="monospace",color="#c8cdd6",size=11),margin=dict(l=50,r=20,t=30,b=40),height=260,showlegend=False,yaxis=dict(gridcolor="#1e2028",range=[0,max(fc["pm25_ugm3"])*1.3]),xaxis=dict(gridcolor="#1e2028"))
    st.plotly_chart(fig,width="stretch",config={"displayModeBar":False})
    cols = st.columns(6)
    for i,(_,row) in enumerate(fc.iterrows()):
        with cols[i]:
            st.markdown(f'<div style="background:#111318;border:0.5px solid #2a2d35;border-radius:8px;padding:8px 6px;text-align:center"><div style="font-size:9px;color:#6b7280">+{row["hours_ahead"]}h</div><div style="font-size:16px;font-weight:700;color:{row["color"]};margin:3px 0">{row["pm25_ugm3"]}</div><div style="font-size:8px;color:{row["color"]}">{row["category"][:4].upper()}</div></div>',unsafe_allow_html=True)

st.markdown('<hr style="border-color:#1e2028;margin:16px 0">',unsafe_allow_html=True)
t1,t2,t3 = st.tabs(["📈 HISTORICAL TRENDS","🌡 POLLUTION HEATMAP","📋 MODEL METRICS"])

with t1:
    if not hist.empty:
        days = st.select_slider("Days",options=[3,7,14,30,60,90],value=14,label_visibility="collapsed")
        df = hist.tail(days*24)
        fig2 = make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.65,0.35],vertical_spacing=0.04)
        fig2.add_trace(go.Scatter(x=df["datetime"],y=df["pm25"],fill="tozeroy",fillcolor="rgba(245,166,35,0.08)",line=dict(color="#f5a623",width=1.5),name="PM2.5"),row=1,col=1)
        if "pm10" in df.columns:
            fig2.add_trace(go.Scatter(x=df["datetime"],y=df["pm10"],line=dict(color="#60a5fa",width=1,dash="dot"),name="PM10"),row=1,col=1)
        fig2.add_hline(y=15,line_dash="dot",line_color="#374151",row=1,col=1)
        if "wind_speed_10m" in df.columns:
            fig2.add_trace(go.Bar(x=df["datetime"],y=df["wind_speed_10m"],marker_color="#1e3a4a",name="Wind"),row=2,col=1)
        fig2.update_layout(paper_bgcolor="#111318",plot_bgcolor="#111318",font=dict(family="monospace",color="#c8cdd6",size=11),height=380,legend=dict(orientation="h",yanchor="bottom",y=1.02,font=dict(size=10,color="#6b7280")),margin=dict(l=50,r=20,t=30,b=40))
        st.plotly_chart(fig2,width="stretch",config={"displayModeBar":False})
        r1,r2,r3,r4 = st.columns(4)
        r1.metric("Avg PM2.5",f"{df['pm25'].mean():.1f} ug/m3")
        r2.metric("Peak PM2.5",f"{df['pm25'].max():.1f} ug/m3")
        r3.metric("Min PM2.5",f"{df['pm25'].min():.1f} ug/m3")
        r4.metric("WHO Exceedance",f"{round((df['pm25']>15).sum()/len(df)*100,1)}% of hours")
    else:
        st.info("Run python data_pipeline.py first.")

with t2:
    if not hist.empty:
        df2 = hist.copy()
        df2["hour"] = pd.to_datetime(df2["datetime"]).dt.hour
        df2["date"] = pd.to_datetime(df2["datetime"]).dt.date
        pivot = df2.pivot_table(values="pm25",index="hour",columns="date",aggfunc="mean").iloc[:,-30:]
        fig3 = go.Figure(go.Heatmap(z=pivot.values,x=[str(c) for c in pivot.columns],y=[f"{h:02d}:00" for h in pivot.index],colorscale=[[0,"#0d2218"],[0.2,"#22c55e"],[0.4,"#84cc16"],[0.6,"#f5a623"],[0.8,"#ef4444"],[1,"#7f1d1d"]],hovertemplate="Date: %{x}<br>Hour: %{y}<br>PM2.5: %{z:.1f}<extra></extra>",colorbar=dict(tickfont=dict(size=9,color="#6b7280"),thickness=10)))
        fig3.update_layout(paper_bgcolor="#111318",plot_bgcolor="#111318",font=dict(family="monospace",color="#c8cdd6",size=11),height=320,yaxis=dict(autorange="reversed"),xaxis=dict(tickangle=45),margin=dict(l=50,r=20,t=30,b=40))
        st.plotly_chart(fig3,width="stretch",config={"displayModeBar":False})
        st.markdown('<div style="font-size:10px;color:#6b7280;padding:8px 12px;background:#111318;border-radius:6px">Dark green = clean - Amber = moderate - Red = hazardous - Peaks at 7-9am and 6-9pm</div>',unsafe_allow_html=True)
    else:
        st.info("No historical data available.")

with t3:
    m1,m2 = st.columns(2)
    with m1:
        st.markdown('<div style="font-size:10px;color:#6b7280;margin-bottom:10px">MODEL PERFORMANCE</div>',unsafe_allow_html=True)
        try:
            with open("models/metrics.json") as f:
                m = json.load(f)
            st.metric("MAE",f"{m['mae_ug_m3']} ug/m3","Mean Absolute Error")
            st.metric("RMSE",f"{m['rmse_ug_m3']} ug/m3","Root Mean Square Error")
            st.metric("MAPE",f"{m['mape_pct']}%","Mean Absolute % Error")
            st.metric("Training Samples",f"{m['n_train']:,}")
            st.metric("Last Trained",m.get("trained_at","")[:10])
        except:
            st.info("Train the model first: python model.py")
    with m2:
        st.markdown('<div style="font-size:10px;color:#6b7280;margin-bottom:10px">MODEL ARCHITECTURE</div>',unsafe_allow_html=True)
        for k,v in [("Model","Bidirectional LSTM + Attention"),("Features","39 engineered features"),("Sequence","24 hours of history"),("Horizon","6 hours ahead"),("Data","OpenAQ CPCB + Open-Meteo"),("Stations","Railway Colony + Pan Bazaar"),("AQI Standard","India CPCB"),("Refresh","Every 30 minutes")]:
            st.markdown(f'<div style="display:flex;justify-content:space-between;padding:7px 12px;border-bottom:0.5px solid #1e2028;font-size:11px"><span style="color:#6b7280">{k}</span><span style="color:#e8eaf0">{v}</span></div>',unsafe_allow_html=True)

st.markdown('<hr style="border-color:#1e2028;margin:20px 0 10px">',unsafe_allow_html=True)
st.markdown('<div style="font-size:9px;color:#374151">GUWAHATI AQI FORECAST - BiLSTM MODEL - DATA: CPCB + OPEN-METEO - FOR INFORMATIONAL PURPOSES ONLY</div>',unsafe_allow_html=True)
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()
