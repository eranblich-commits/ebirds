import streamlit as st
import requests
import pandas as pd
import math
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
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
        self.ua = f"ebird_pro_il_{random.randint(1000, 9999)}"
        self.geolocator = Nominatim(user_agent=self.ua)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def get_hotspots_in_radius(self, lat, lon, dist, key):
        url = f"{self.base_url}/ref/hotspot/geo"
        params = {"lat": lat, "lng": lon, "dist": dist, "fmt": "json"}
        res = requests.get(url, headers={"X-eBirdApiToken": key}, params=params)
        return res.json() if res.status_code == 200 else []

    def get_all_obs_for_hotspot(self, loc_id, days, key):
        url = f"{self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers={"X-eBirdApiToken": key}, params=params)
        return res.json() if res.status_code == 200 else []

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - סריקה עמוקה")

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
    
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 10)
    days = st.slider("ימים אחורה:", 1, 14, 3)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 10 המוקדים העשירים", "🎯 10 התצפיות הגדולות למין"])

# פונקציה להרצה מקבילה של שליפת נתונים ממוקדים (שיפור ביצועים)
def scan_area(clat, clon, radius, days, api_key):
    hotspots = explorer.get_hotspots_in_radius(clat, clon, radius, api_key)
    # נגביל ל-30 מוקדים קרובים כדי לא לחסום את ה-API
    for hs in hotspots:
        hs['d'] = explorer.calculate_distance(clat, clon, hs['lat'], hs['lng'])
    hotspots = sorted(hotspots, key=lambda x: x['d'])[:30]
    
    all_results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(explorer.get_all_obs_for_hotspot, h['locId'], days, api_key): h for h in hotspots}
        for future in futures:
            hs = futures[future]
            obs = future.result()
            if obs:
                all_results.append({"hotspot": hs, "observations": obs})
    return all_results

with tab1:
    if st.button("🔍 בצע סריקה עמוקה"):
        with st.spinner("סורק מוקד-מוקד לדיוק מקסימלי..."):
            data = scan_area(clat, clon, radius, days, api_key)
            if data:
                summary = []
                for entry in data:
                    obs = entry['observations']
                    summary.append({
                        "מיקום": entry['hotspot']['locName'],
                        "ק\"מ": round(entry['hotspot']['d'], 1),
                        "מספר מינים": len(set(o['sciName'] for o in obs)),
                        "תאריך": obs[0]['obsDt'].split(' ')[0]
                    })
                top_10 = pd.DataFrame(summary).sort_values("מספר מינים", ascending=False).head(10)
                st.table(top_10)
            else:
                st.warning("לא נמצאו נתונים.")

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש כמות מקסימלית:", [""] + BIRD_OPTIONS)
    if st.button("🎯 חפש תצפיות שיא") and selected_bird:
        target_sci = BIRD_MAP.get(selected_bird)
        with st.spinner(f"סורק את כל הדיווחים הגולמיים במוקדים עבור {selected_bird}..."):
            data = scan_area(clat, clon, radius, days, api_key)
            bird_obs = []
            for entry in data:
                for o in entry['observations']:
                    if target_sci.lower() in o.get('sciName', '').lower():
                        c_str = o.get('howMany', '1')
                        count = int(c_str) if str(c_str).isdigit() else 1
                        bird_obs.append({
                            "מיקום": entry['hotspot']['locName'],
                            "כמות": c_str,
                            "מספר": count,
                            "ק\"מ": round(entry['hotspot']['d'], 1),
                            "תאריך": o['obsDt'],
                            "צופה": o.get('userDisplayName', 'אנונימי')
                        })
            
            if bird_obs:
                final_df = pd.DataFrame(bird_obs).sort_values("מספר", ascending=False).head(10)
                st.success(f"נמצאו תצפיות! הנה ה-10 הגדולות ביותר:")
                st.table(final_df.drop(columns=['מספר']))
            else:
                st.info("לא נמצאו תצפיות למין זה בסריקה העמוקה.")
