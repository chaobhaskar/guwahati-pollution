import pandas as pd
import requests
from prophet import Prophet
import matplotlib.pyplot as plt
from datetime import datetime

def fetch_guwahati_data():
    print("Fetching historical PM2.5 data for Guwahati...")
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": 26.142,
        "longitude": 91.7362,
        "hourly": "pm2_5",
        "past_days": 30,
        "timezone": "Asia/Kolkata"
    }
    response = requests.get(url, params=params)
    data = response.json()

    # The fix: Removed .dt because pd.to_datetime returns a DatetimeIndex directly
    df = pd.DataFrame({
        'ds': pd.to_datetime(data['hourly']['time']).tz_localize(None),
        'y': data['hourly']['pm2_5']
    })
    
    df = df.dropna()
    return df

def train_and_forecast(df):
    print("Training the Prophet model on particulate matter data...")
    model = Prophet(yearly_seasonality=False, weekly_seasonality=True, daily_seasonality=True)
    model.fit(df)

    print("Predicting the next 24 hours...")
    future = model.make_future_dataframe(periods=24, freq='H')
    forecast = model.predict(future)

    return model, forecast

if __name__ == "__main__":
    try:
        df = fetch_guwahati_data()
        model, forecast = train_and_forecast(df)

        now = pd.Timestamp.now()
        next_24h = forecast[forecast['ds'] > now].head(24)

        print("\n--- Next 24 Hours PM2.5 Forecast for Guwahati ---")
        output_df = next_24h[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        output_df['ds'] = output_df['ds'].dt.strftime('%Y-%m-%d %H:00')
        output_df.rename(columns={'ds': 'Time', 'yhat': 'Predicted PM2.5', 'yhat_lower': 'Min', 'yhat_upper': 'Max'}, inplace=True)
        print(output_df.to_string(index=False))

        print("\nGenerating forecast plot...")
        fig = model.plot(forecast)
        plt.title("Guwahati PM2.5 Forecast (Next 24 Hours)")
        plt.xlabel("Date & Time")
        plt.ylabel("PM2.5 (µg/m³)")
        
        plt.axvline(x=now, color='red', linestyle='--', label='Current Time')
        plt.legend()
        plt.show()
    except Exception as e:
        print(f"An error occurred: {e}")
