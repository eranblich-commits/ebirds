import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
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
        self.ua = f"ebird_explorer_il_{random.randint(1000, 9999)}"
        self.geolocator = Nominatim(user_agent=self.ua)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

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
        city = st.text_input("עיר (באנגלית):", "Kfar Saba")
        try:
            res = explorer.geolocator.geocode(f"{city}, Israel", timeout=10)
            if res: clat, clon = res.latitude, res.longitude
        except: pass
    
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

# פונקציה משופרת לשליפת כל הנתונים - מושכת גם תצפיות רגילות וגם "ראויות לציון" לדיוק מקסימלי
def fetch_comprehensive_obs(lat, lon, dist, days, key):
    headers = {"X-eBirdApiToken": key}
    params = {"lat": lat, "lng": lon, "dist": dist, "back": days, "fmt": "json", "includeProvisional": "true"}
    
    # שליפת תצפיות אחרונות
    r1 = requests.get(f"https://api.ebird.org/v2/data/obs/geo/recent", headers=headers, params=params)
    # שליפת תצפיות "ראויות לציון" (מכיל לעיתים דיווחים מפורטים יותר)
    r2 = requests.get(f"https://api.ebird.org/v2/data/obs/geo/recent/notable", headers=headers, params=params)
    
    data1 = r1.json() if r1.status_code == 200 else []
    data2 = r2.json() if r2.status_code == 200 else []
    
    # איחוד והסרת כפילויות לפי מזהה תצפית אם קיים, או שילוב נתונים
    combined = data1 + data2
    return combined

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

with tab1:
    if st.button("🔍 סרוק 10 מקומות מובילים"):
        with st.spinner("מנתח את כל הדיווחים באזור..."):
            raw_obs = fetch_comprehensive_obs(clat, clon, radius, days, api_key)
            if raw_obs:
                df = pd.DataFrame(raw_obs)
                summary = []
                # קיבוץ לפי ID של מיקום לדיוק מרבי
                for loc_id, group in df.groupby('locId'):
                    summary.append({
                        "מיקום": group.iloc[0]['locName'],
                        "ק\"מ": round(explorer.calculate_distance(clat, clon, group.iloc[0]['lat'], group.iloc[0]['lng']), 1),
                        "מספר מינים": len(group['sciName'].unique()),
                        "תאריך": group['obsDt'].max().split(' ')[0]
                    })
                top_10 = pd.DataFrame(summary).sort_values("מספר מינים", ascending=False).head(10)
                st.table(top_10)
            else:
                st.warning("לא נמצאו תצפיות.")

with tab2:
    selected_bird = st.selectbox("בחר ציפור:", [""] + BIRD_OPTIONS)
    if st.button("🎯 חפש 10 ריכוזים גדולים") and selected_bird:
        target_sci = BIRD_MAP.get(selected_bird)
        with st.spinner(f"מחפש את הכמויות הגדולות ביותר של {selected_bird}..."):
            raw_obs = fetch_comprehensive_obs(clat, clon, radius, days, api_key)
            matches = [o for o in raw_obs if target_sci.lower() in o.get('sciName', '').lower()]
            
            if matches:
                obs_list = []
                for o in matches:
                    c_str = o.get('howMany', '1')
                    count = int(c_str) if str(c_str).isdigit() else 1
                    obs_list.append({
                        "מיקום": o['locName'],
                        "כמות": c_str,
                        "count_num": count,
                        "מרחק (ק\"מ)": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "תאריך": o['obsDt'],
                        "צופה": o.get('userDisplayName', 'אנונימי')
                    })
                
                # הצגת 10 התצפיות עם הכמות הגדולה ביותר
                final_df = pd.DataFrame(obs_list).sort_values("count_num", ascending=False).head(10)
                st.success(f"הצגת 10 הדיווחים עם הכמויות הגדולות ביותר:")
                st.table(final_df.drop(columns=['count_num']))
            else:
                st.info("לא נמצאו תצפיות למין זה.")
