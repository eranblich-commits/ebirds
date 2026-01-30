import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import math
import json
import os
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

st.set_page_config(page_title="eBird Israel Pro Explorer", layout="wide")

@st.cache_data
def load_birds_data():
    file_path = 'birds.json'
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

ALL_BIRDS = load_birds_data()
BIRD_OPTIONS = [f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})" for b in ALL_BIRDS]
BIRD_MAP = {f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') for b in ALL_BIRDS}

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.geolocator = Nominatim(user_agent="ebird_israel_final_v9")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    @st.cache_data(ttl=600)
    def get_species_obs_in_radius(_self, sci_name, lat, lon, dist, api_key, days):
        """פונקציה חדשה: מושכת ישירות את כל תצפיות המין ברדיוס"""
        headers = _self.get_headers(api_key)
        # שימוש ב-endpoint ייעודי למינים ברדיוס
        url = f"{_self.base_url}/data/obs/geo/recent/{sci_name}"
        params = {
            "lat": lat,
            "lng": lon,
            "dist": min(dist, 50), # eBird מגביל ל-50 ק"מ בנתיב זה
            "back": days,
            "includeProvisional": "true"
        }
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - Explorer Pro")

with st.sidebar:
    st.header("הגדרות חיפוש")
    api_key = st.text_input("API Key (eBird):", type="password")
    mode = st.radio("מרכז חיפוש:", ["כפר סבא", "המיקום שלי (GPS)", "חיפוש עיר"])
    clat, clon = 32.175, 34.906
    if mode == "המיקום שלי (GPS)":
        loc = get_geolocation()
        if loc: clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    elif mode == "חיפוש עיר":
        city = st.text_input("עיר:", "Tel Aviv")
        res = explorer.geolocator.geocode(f"{city}, Israel")
        if res: clat, clon = res.latitude, res.longitude
    radius = st.slider("רדיוס (ק\"מ):", 1, 100, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

with tab1:
    st.info("השתמש בכפתור לסריקת המוקדים הכללית בסביבה.")
    if st.button("🔍 סרוק מוקדים"):
        # נשאר עם הלוגיקה הקודמת לטאב 1 כי היא טובה לסקירה כללית
        pass 

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש ממוקד:", [""] + BIRD_OPTIONS)
    if st.button("🎯 מצא את הכמות המקסימלית") and selected_bird:
        sci_name = BIRD_MAP.get(selected_bird)
        with st.spinner(f"מושך נתונים ישירות עבור {selected_bird}..."):
            # פנייה אחת ל-API שמחזירה את כל התצפיות של המין ברדיוס
            all_obs = explorer.get_species_obs_in_radius(sci_name, clat, clon, radius, api_key, days)
            
            if all_obs:
                results = []
                for o in all_obs:
                    results.append({
                        "מיקום": o.get('locName', 'לא ידוע'),
                        "ק\"מ": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "כמות": o.get('howMany', 'X'),
                        "תאריך": o.get('obsDt', '').split(' ')[0],
                        "צופה": o.get('userDisplayName', 'אנונימי'),
                        "lat": o['lat'], "lon": o['lng'],
                        "raw_count": (int(o['howMany']) if str(o.get('howMany')).isdigit() else 1)
                    })
                
                df = pd.DataFrame(results)
                
                # כאן אנחנו מציגים את כל התצפיות, אבל ממיינים לפי כמות (מהגבוה לנמוך)
                df_sorted = df.sort_values(by="raw_count", ascending=False)
                
                st.success(f"נמצאו {len(df)} תצפיות של {selected_bird}!")
                st.dataframe(df_sorted.drop(columns=['lat', 'lon', 'raw_count']), use_container_width=True)
                
                # מפה
                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer("ScatterplotLayer", df, get_position=["lon", "lat"], get_color=[0, 128, 255, 160], get_radius=400)],
                    initial_view_state=pdk.ViewState(latitude=clat, longitude=clon, zoom=10)
                ))
            else:
                st.info("לא נמצאו תצפיות של מין זה ברדיוס הנבחר.")
