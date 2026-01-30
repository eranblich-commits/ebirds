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
        self.geolocator = Nominatim(user_agent="ebird_israel_final_v11")

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
        city = st.text_input("עיר:", "Tel Aviv")
        res = explorer.geolocator.geocode(f"{city}, Israel")
        if res: clat, clon = res.latitude, res.longitude
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 20) # eBird API מוגבל ל-50 בחיפוש גאוגרפי
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

with tab1:
    if st.button("🔍 סרוק תצפיות בסביבה"):
        with st.spinner("מושך את כל התצפיות האחרונות..."):
            # שליפת כל התצפיות ברדיוס (זה מחזיר רשימה ארוכה של הכל)
            url = f"{explorer.base_url}/data/obs/geo/recent"
            params = {"lat": clat, "lng": clon, "dist": radius, "back": days, "fmt": "json"}
            res = requests.get(url, headers={"X-eBirdApiToken": api_key}, params=params)
            all_obs = res.json() if res.status_code == 200 else []
            
            if all_obs:
                # קיבוץ לפי מוקד
                df = pd.DataFrame(all_obs)
                summary = []
                for loc_name, group in df.groupby('locName'):
                    first = group.iloc[0]
                    dist = explorer.calculate_distance(clat, clon, first['lat'], first['lng'])
                    summary.append({
                        "מיקום": loc_name,
                        "ק\"מ": round(dist, 1),
                        "מינים": len(group['sciName'].unique()),
                        "עדכון": group['obsDt'].max().split(' ')[0]
                    })
                st.dataframe(pd.DataFrame(summary).sort_values("ק\"מ"), use_container_width=True)
            else:
                st.info("לא נמצאו תצפיות.")

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש מקסימום:", [""] + BIRD_OPTIONS)
    if st.button("🎯 מצא את הריכוז הכי גבוה") and selected_bird:
        sci_name = BIRD_MAP.get(selected_bird)
        with st.spinner(f"מחפש בכל הדיווחים הגולמיים של {selected_bird}..."):
            # פה הפתרון: אנחנו מבקשים את כל הדיווחים של המין הספציפי ברדיוס
            # eBird מחזיר כאן את הדיווחים האחרונים של כל צופה/מיקום
            url = f"{explorer.base_url}/data/obs/geo/recent/{sci_name}"
            params = {"lat": clat, "lng": clon, "dist": radius, "back": days, "fmt": "json"}
            res = requests.get(url, headers={"X-eBirdApiToken": api_key}, params=params)
            obs_list = res.json() if res.status_code == 200 else []
            
            if obs_list:
                results = []
                for o in obs_list:
                    count_val = o.get('howMany')
                    # המרה למספר לצורך מיון, אבל שמירה על X אם קיים
                    num_count = int(count_val) if str(count_val).isdigit() else 1
                    
                    results.append({
                        "מיקום": o.get('locName'),
                        "ק\"מ": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "כמות": count_val if count_val else 1,
                        "צופה": o.get('userDisplayName', 'אנונימי'),
                        "תאריך": o.get('obsDt'),
                        "raw_count": num_count
                    })
                
                # מיון לפי כמות מהגבוה לנמוך
                sdf = pd.DataFrame(results).sort_values(by="raw_count", ascending=False)
                st.success(f"נמצאו {len(sdf)} דיווחים שונים!")
                st.dataframe(sdf.drop(columns=['raw_count']), use_container_width=True)
            else:
                st.info("לא נמצאו תצפיות למין זה. נסה להגדיל רדיוס.")
