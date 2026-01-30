import streamlit as st
import requests
import pandas as pd
import math
import json
import os
import random
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
        self.ua = f"ebird_pro_fixed_{random.randint(1000, 9999)}"
        self.geolocator = Nominatim(user_agent=self.ua)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def fetch_all_recent_obs(self, lat, lon, dist, days, key):
        # שימוש ב-Endpoint גאוגרפי ישיר שמחזיר את כל הדיווחים הגולמיים ברדיוס
        url = f"{self.base_url}/data/obs/geo/recent"
        params = {
            "lat": lat,
            "lng": lon,
            "dist": dist, # הרדיוס נשלח ישירות ל-eBird
            "back": days,
            "includeProvisional": "true",
            "fmt": "json"
        }
        res = requests.get(url, headers={"X-eBirdApiToken": key}, params=params)
        return res.json() if res.status_code == 200 else []

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - Explorer Pro (גרסה מתוקנת)")

with st.sidebar:
    st.header("הגדרות חיפוש")
    api_key = st.text_input("API Key (eBird):", type="password")
    mode = st.radio("מרכז חיפוש:", ["כפר סבא", "המיקום שלי (GPS)", "חיפוש עיר"])
    
    clat, clon = 32.175, 34.906
    if mode == "המיקום שלי (GPS)":
        loc = get_geolocation()
        if loc: clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    elif mode == "חיפוש עיר":
        city = st.text_input("עיר (באנגלית):", "Kfar Saba")
        try:
            res = explorer.geolocator.geocode(f"{city}, Israel", timeout=10)
            if res: clat, clon = res.latitude, res.longitude
        except: pass
    
    radius = st.slider("רדיוס לחיפוש (ק\"מ):", 1, 50, 50)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 10 המוקדים העשירים", "🎯 10 התצפיות הגדולות למין"])

# שליפת נתונים גולמיים לשימוש בשני הטאבים
if 'raw_data' not in st.session_state:
    st.session_state.raw_data = None

if st.button("🚀 רענן נתונים וסרוק רדיוס"):
    with st.spinner(f"מושך את כל הדיווחים בטווח {radius} ק\"מ..."):
        st.session_state.raw_data = explorer.fetch_all_recent_obs(clat, clon, radius, days, api_key)

if st.session_state.raw_data:
    raw_obs = st.session_state.raw_data
    
    with tab1:
        summary = []
        df_raw = pd.DataFrame(raw_obs)
        if not df_raw.empty:
            for loc_id, group in df_raw.groupby('locId'):
                dist = explorer.calculate_distance(clat, clon, group.iloc[0]['lat'], group.iloc[0]['lng'])
                summary.append({
                    "מיקום": group.iloc[0]['locName'],
                    "ק\"מ": round(dist, 1),
                    "מספר מינים": len(group['sciName'].unique()),
                    "תאריך": group['obsDt'].max().split(' ')[0]
                })
            top_10 = pd.DataFrame(summary).sort_values("מספר מינים", ascending=False).head(10)
            st.write(f"נמצאו {len(summary)} מוקדים ברדיוס. הנה ה-10 העשירים ביותר:")
            st.table(top_10)

    with tab2:
        selected_bird = st.selectbox("בחר ציפור:", [""] + BIRD_OPTIONS)
        if selected_bird:
            target_sci = BIRD_MAP.get(selected_bird)
            # סינון המין המבוקש מתוך כל המידע שנסרק ברדיוס
            matches = [o for o in raw_obs if target_sci.lower() in o.get('sciName', '').lower()]
            
            if matches:
                bird_list = []
                for o in matches:
                    c_str = o.get('howMany', '1')
                    count = int(c_str) if str(c_str).isdigit() else 1
                    bird_list.append({
                        "מיקום": o['locName'],
                        "כמות": c_str,
                        "מספר": count,
                        "מרחק": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "תאריך": o['obsDt'],
                        "צופה": o.get('userDisplayName', 'אנונימי')
                    })
                
                final_df = pd.DataFrame(bird_list).sort_values("מספר", ascending=False).head(10)
                st.success(f"נמצאו {len(bird_list)} דיווחים ברדיוס של {radius} ק\"מ.")
                st.table(final_df.drop(columns=['מספר']))
            else:
                st.info(f"לא נמצאו דיווחים של {selected_bird} בטווח שנבחר.")
else:
    st.warning("לחץ על הכפתור 'רענן נתונים' כדי להתחיל בסריקה.")
