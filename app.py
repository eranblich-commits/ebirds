import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import math
import json
import os
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# הגדרות דף
st.set_page_config(page_title="eBird Israel Pro Explorer", layout="wide")

# פונקציה לטעינת רשימת הציפורים מקובץ JSON
@st.cache_data
def load_birds_data():
    file_path = 'birds.json'
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"שגיאה בטעינת קובץ הציפורים: {e}")
            return []
    return []

# טעינת הנתונים ועיבודם לרשימת בחירה
ALL_BIRDS = load_birds_data()
BIRD_OPTIONS = [f"{b['heb']} ({b['eng']})" for b in ALL_BIRDS]
BIRD_MAP = {f"{b['heb']} ({b['eng']})": b['sci'] for b in ALL_BIRDS}

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.geolocator = Nominatim(user_agent="ebird_israel_vfinal")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """חישוב מרחק אווירי מדויק בק"מ (נוסחת הברסין)"""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    @st.cache_data(ttl=3600)
    def get_nearby_hotspots(_self, lat, lon, dist, api_key):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/ref/hotspot/geo"
        # API של eBird מוגבל ל-50 ק"מ. לכן נבקש 50 ונבצע סינון ידני אם נדרש פחות.
        params = {"lat": lat, "lng": lon, "dist": min(dist, 50), "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        all_hs = res.json() if res.status_code == 200 else []
        
        # הוספת המרחק המחושב לכל מוקד
        for hs in all_hs:
            hs['calculated_dist'] = _self.calculate_distance(lat, lon, hs['lat'], hs['lng'])
        return all_hs

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - Explorer Pro")

with st.sidebar:
    st.header("הגדרות מיקום")
    api_key = st.text_input("API Key (eBird):", type="password")
    
    mode = st.radio("נקודת מרכז:", ["כפר סבא", "חיפוש עיר (ידני)", "המיקום שלי (GPS)"])
    
    clat, clon = 32.175, 34.906 # ברירת מחדל
    
    if mode == "חיפוש עיר (ידני)":
        city_input = st.text_input("הכנס שם עיר (אנגלית):", "Haifa")
        location = explorer.geolocator.geocode(f"{city_input}, Israel")
        if location:
            clat, clon = location.latitude, location.longitude
            st.success(f"נמצא: {location.address[:30]}...")
    
    elif mode == "המיקום שלי (GPS)":
        loc = get_geolocation()
        if loc:
            clat = loc['coords']['latitude']
            clon = loc['coords']['longitude']
            st.success("המיקום זוהה בהצלחה")
        else:
            st.info("אנא אשר גישת מיקום בדפדפן...")

    radius = st.slider("רדיוס חיפוש (ק\"מ):", 1, 100, 25)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.warning("יש להזין API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

with tab1:
    if st.button("🔍 סרוק מוקדים בסביבה"):
        with st.spinner("מושך נתונים..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            results = []
            progress_bar = st.progress(0)
            
            for i, hs in enumerate(hotspots[:60]): # הגבלה ל-60 מוקדים לביצועים
                obs = explorer.get_observations(hs['locId'], api_key, days)
                if obs:
                    results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs['calculated_dist'], 1),
                        "מינים": len(set(o['sciName'] for o in obs)),
                        "תאריך": obs[0]['obsDt'].split(' ')[0],
                        "lat": hs['lat'], "lon": hs['lng']
                    })
                progress_bar.progress
