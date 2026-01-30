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
# מיפוי שם עברי/אנגלי לשם מדעי
BIRD_MAP = {f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') for b in ALL_BIRDS}

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.geolocator = Nominatim(user_agent="ebird_israel_v12_final")

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
    
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

# פונקציה מרכזית לשליפת כל הנתונים ברדיוס
def get_raw_obs(lat, lon, dist, days, api_key):
    url = f"https://api.ebird.org/v2/data/obs/geo/recent"
    params = {"lat": lat, "lng": lon, "dist": dist, "back": days, "fmt": "json", "includeProvisional": "true"}
    headers = {"X-eBirdApiToken": api_key}
    res = requests.get(url, headers=headers, params=params)
    return res.json() if res.status_code == 200 else []

with tab1:
    if st.button("🔍 סרוק תצפיות בסביבה"):
        with st.spinner("טוען נתונים..."):
            all_data = get_raw_obs(clat, clon, radius, days, api_key)
            if all_data:
                df = pd.DataFrame(all_data)
                summary = []
                for loc_name, group in df.groupby('locName'):
                    d = explorer.calculate_distance(clat, clon, group.iloc[0]['lat'], group.iloc[0]['lng'])
                    summary.append({
                        "מיקום": loc_name,
                        "ק\"מ": round(d, 1),
                        "מינים": len(group['sciName'].unique()),
                        "עדכון": group['obsDt'].max()
                    })
                st.dataframe(pd.DataFrame(summary).sort_values("ק\"מ"), use_container_width=True)
            else:
                st.info("אין תצפיות ברדיוס זה.")

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש כמות מקסימלית:", [""] + BIRD_OPTIONS)
    if st.button("🎯 חפש תצפיות") and selected_bird:
        target_sci = BIRD_MAP.get(selected_bird)
        with st.spinner(f"סורק את כל הדיווחים של {selected_bird}..."):
            # אנחנו מושכים את כל הנתונים הגולמיים ברדיוס ומסננים אצלנו בקוד
            raw_data = get_raw_obs(clat, clon, radius, days, api_key)
            
            # סינון המין הספציפי (חיפוש גמיש בשם המדעי)
            matches = [o for o in raw_data if target_sci.lower() in o.get('sciName', '').lower()]
            
            if matches:
                results = []
                # יצירת מילון כדי למצוא את המקסימום לכל מיקום
                loc_max = {}
                
                for o in matches:
                    loc = o.get('locName')
                    count_val = o.get('howMany')
                    # המרה למספר לצורך השוואה
                    current_count = int(count_val) if str(count_val).isdigit() else 1
                    
                    # אם המיקום לא קיים או שמצאנו כמות גדולה יותר, נעדכן
                    if loc not in loc_max or current_count > loc_max[loc]['raw_count']:
                        loc_max[loc] = {
                            "מיקום": loc,
                            "ק\"מ": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                            "כמות": count_val if count_val else "X",
                            "צופה": o.get('userDisplayName', 'אנונימי'),
                            "תאריך": o.get('obsDt'),
                            "raw_count": current_count
                        }
                
                # המרה לרשימה ומיון לפי כמות (מהגבוה לנמוך)
                final_df = pd.DataFrame(list(loc_max.values())).sort_values(by="raw_count", ascending=False)
                
                st.success(f"נמצאו תצפיות של {selected_bird} ב-{len(final_df)} מוקדים!")
                st.dataframe(final_df.drop(columns=['raw_count']), use_container_width=True)
            else:
                st.info(f"לא נמצאו תצפיות עבור {selected_bird} ברדיוס שנבחר.")
