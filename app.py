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
        self.geolocator = Nominatim(user_agent="ebird_israel_ultra_v8")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    @st.cache_data(ttl=3600)
    def get_nearby_hotspots(_self, lat, lon, dist, api_key):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/ref/hotspot/geo"
        params = {"lat": lat, "lng": lon, "dist": min(dist, 50), "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        all_hs = res.json() if res.status_code == 200 else []
        for hs in all_hs:
            hs['calculated_dist'] = _self.calculate_distance(lat, lon, hs['lat'], hs['lng'])
        return sorted(all_hs, key=lambda x: x['calculated_dist'])

    @st.cache_data(ttl=600)
    def get_full_history(_self, loc_id, api_key, days):
        """פונקציה חדשה: מושכת את כל התצפיות ההיסטוריות ולא רק את האחרונה"""
        headers = _self.get_headers(api_key)
        # שימוש ב-endpoint של data/obs/loc/recent שכולל את כל התצפיות
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
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
    if st.button("🔍 סרוק אזור"):
        with st.spinner("סורק מוקדים..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            results = []
            for hs in hotspots[:40]:
                obs = explorer.get_full_history(hs['locId'], api_key, days)
                if obs:
                    results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs['calculated_dist'], 1),
                        "מינים": len(set(o.get('sciName','') for o in obs)),
                        "עדכון": obs[0].get('obsDt', '').split(' ')[0]
                    })
            if results:
                st.dataframe(pd.DataFrame(results).sort_values("ק\"מ"), use_container_width=True)

with tab2:
    selected_bird = st.selectbox("בחר ציפור:", [""] + BIRD_OPTIONS)
    if st.button("🎯 חפש תצפיות") and selected_bird:
        sci_name = BIRD_MAP.get(selected_bird)
        with st.spinner(f"סורק את כל התצפיות של {selected_bird}..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            s_results = []
            
            for hs in hotspots[:50]:
                # אנחנו מושכים את כל ההיסטוריה של המוקד לימים אלו
                obs_list = explorer.get_full_history(hs['locId'], api_key, days)
                
                # סינון כל התצפיות של המין הספציפי מתוך כל הרשימה
                matches = [o for o in obs_list if sci_name.lower() in o.get('sciName','').lower()]
                
                if matches:
                    def get_val(o):
                        v = o.get('howMany')
                        if v is None or str(v).upper() == 'X': return 1
                        try: return int(v)
                        except: return 1

                    # כאן קורה הקסם: הוא עובר על *כל* התצפיות שנמצאו ובוחר את זו עם הכמות הגבוהה ביותר
                    best_obs = max(matches, key=get_val)
                    
                    s_results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs['calculated_dist'], 1),
                        "כמות מקסימלית": best_obs.get('howMany', '1'),
                        "צופה": best_obs.get('userDisplayName', 'אנונימי'),
                        "תאריך": best_obs.get('obsDt', '').split(' ')[0]
                    })
            
            if s_results:
                st.dataframe(pd.DataFrame(s_results).sort_values("ק\"מ"), use_container_width=True)
            else:
                st.info("לא נמצאו תצפיות.")
