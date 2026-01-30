import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import math
import json
import os
from concurrent.futures import ThreadPoolExecutor # להרצה מהירה
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
        self.geolocator = Nominatim(user_agent="ebird_israel_final_v10")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def fetch_obs_for_hotspot(self, hs, api_key, days):
        """פונקציה לסריקת מוקד בודד (תרוץ במקביל)"""
        url = f"{self.base_url}/data/obs/{hs['locId']}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=self.get_headers(api_key), params=params)
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

# --- לוגיקה משותפת לסריקת מוקדים ---
def get_all_nearby_data(clat, clon, radius, api_key, days):
    url = f"https://api.ebird.org/v2/ref/hotspot/geo"
    params = {"lat": clat, "lng": clon, "dist": min(radius, 50), "fmt": "json"}
    res = requests.get(url, headers=explorer.get_headers(api_key), params=params)
    hotspots = res.json() if res.status_code == 200 else []
    
    for hs in hotspots:
        hs['dist'] = explorer.calculate_distance(clat, clon, hs['lat'], hs['lng'])
    
    hotspots = sorted(hotspots, key=lambda x: x['dist'])[:50] # 50 הקרובים ביותר
    
    # הרצה במקביל (Multi-threading) - כאן המהירות!
    all_data = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(explorer.fetch_obs_for_hotspot, hs, api_key, days): hs for hs in hotspots}
        for future in futures:
            hs_info = futures[future]
            obs = future.result()
            if obs:
                all_data.append({"hs": hs_info, "obs": obs})
    return all_data

with tab1:
    if st.button("🔍 סרוק את כל האזור"):
        with st.spinner("סורק מוקדים במקביל (מהיר)..."):
            data = get_all_nearby_data(clat, clon, radius, api_key, days)
            results = []
            for item in data:
                results.append({
                    "מיקום": item['hs']['locName'],
                    "ק\"מ": round(item['hs']['dist'], 1),
                    "מינים": len(set(o.get('sciName','') for o in item['obs'])),
                    "תאריך": item['obs'][0].get('obsDt', '').split(' ')[0]
                })
            if results:
                st.dataframe(pd.DataFrame(results).sort_values("ק\"מ"), use_container_width=True)

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש מקסימום:", [""] + BIRD_OPTIONS)
    if st.button("🎯 מצא את הריכוז הכי גבוה") and selected_bird:
        sci_name = BIRD_MAP.get(selected_bird)
        with st.spinner(f"סורק את כל הדיווחים של {selected_bird}..."):
            data = get_all_nearby_data(clat, clon, radius, api_key, days)
            s_results = []
            
            for item in data:
                # מחפש את המין בכל התצפיות של המוקד הזה
                matches = [o for o in item['obs'] if sci_name.lower() in o.get('sciName','').lower()]
                if matches:
                    # מציאת המקסימום בתוך המוקד
                    def get_count(o):
                        v = o.get('howMany')
                        return int(v) if str(v).isdigit() else 1
                    
                    best_obs = max(matches, key=get_count)
                    s_results.append({
                        "מיקום": item['hs']['locName'],
                        "ק\"מ": round(item['hs']['dist'], 1),
                        "כמות מקסימלית": best_obs.get('howMany', 'X'),
                        "צופה": best_obs.get('userDisplayName', 'אנונימי'),
                        "תאריך": best_obs.get('obsDt', '').split(' ')[0],
                        "raw_count": get_count(best_obs)
                    })
            
            if s_results:
                # מיון לפי כמות מהגבוה לנמוך!
                sdf = pd.DataFrame(s_results).sort_values(by="raw_count", ascending=False)
                st.success(f"נמצאו תצפיות ב-{len(sdf)} מוקדים!")
                st.dataframe(sdf.drop(columns=['raw_count']), use_container_width=True)
            else:
                st.info("לא נמצאו תצפיות. נסה להגדיל רדיוס או ימים.")
