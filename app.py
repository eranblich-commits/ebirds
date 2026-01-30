import streamlit as st
import requests
import pandas as pd
import math
import json
import os
import random
import urllib.parse
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
        self.ua = f"ebird_pro_final_fix_{random.randint(1000, 9999)}"
        self.geolocator = Nominatim(user_agent=self.ua)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def get_headers(self, key):
        return {"X-eBirdApiToken": key}

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - Pro Explorer")

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
    
    # הגבלת רדיוס ל-50 ק"מ (מקסימום API)
    radius = st.slider("רדיוס לחיפוש (ק\"מ):", 1, 50, 50)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 10 המוקדים העשירים", "🎯 10 התצפיות הגדולות למין"])

with tab1:
    if st.button("🔍 סרוק מוקדים עשירים"):
        with st.spinner("סורק את כל המוקדים ברדיוס..."):
            # שימוש בכתובת שמבטיחה לקבל את כל המוקדים ברדיוס
            hs_url = f"{explorer.base_url}/ref/hotspot/geo"
            hs_params = {"lat": clat, "lng": clon, "dist": radius, "fmt": "json"}
            hs_res = requests.get(hs_url, headers=explorer.get_headers(api_key), params=hs_params)
            hotspots = hs_res.json() if hs_res.status_code == 200 else []
            
            if hotspots:
                for hs in hotspots:
                    hs['dist'] = explorer.calculate_distance(clat, clon, hs['lat'], hs['lng'])
                
                # סריקה רחבה יותר של עד 60 מוקדים כדי לא לפספס אזורים רחוקים
                sorted_hs = sorted(hotspots, key=lambda x: x['dist'])[:60]

                def fetch_species_count(h):
                    obs_url = f"{explorer.base_url}/data/obs/{h['locId']}/recent"
                    obs_params = {"back": days, "fmt": "json"}
                    r = requests.get(obs_url, headers=explorer.get_headers(api_key), params=obs_params)
                    obs = r.json() if r.status_code == 200 else []
                    return {
                        "מיקום": h['locName'],
                        "ק\"מ": round(h['dist'], 1),
                        "מספר מינים": len(set(o['sciName'] for o in obs)),
                        "תאריך": obs[0]['obsDt'].split(' ')[0] if obs else "N/A"
                    }

                with ThreadPoolExecutor(max_workers=15) as executor:
                    summary = list(executor.map(fetch_species_count, sorted_hs))
                
                top_10 = pd.DataFrame(summary).sort_values("מספר מינים", ascending=False).head(10)
                st.table(top_10)
            else:
                st.warning("לא נמצאו מוקדים. נסה לוודא שה-API Key תקין.")

with tab2:
    selected_bird = st.selectbox("בחר ציפור לחיפוש עומק:", [""] + BIRD_OPTIONS)
    if st.button("🎯 מצא את כל התצפיות למין") and selected_bird:
        sci_name = BIRD_MAP.get(selected_bird)
        # קידוד השם המדעי לפורמט URL (קריטי למציאת המין)
        encoded_sci = urllib.parse.quote(sci_name)
        
        with st.spinner(f"סורק את כל הדיווחים של {selected_bird}..."):
            url = f"{explorer.base_url}/data/obs/geo/recent/{encoded_sci}"
            params = {
                "lat": clat, "lng": clon, "dist": radius, 
                "back": days, "includeProvisional": "true", "fmt": "json"
            }
            res = requests.get(url, headers=explorer.get_headers(api_key), params=params)
            obs_list = res.json() if res.status_code == 200 else []
            
            if obs_list:
                results = []
                for o in obs_list:
                    how_many = o.get('howMany')
                    # המרת X או ערך ריק ל-1 לצורכי מיון
                    if how_many is None or str(how_many).upper() == 'X':
                        sort_val = 1
                        display_val = "X"
                    else:
                        try:
                            sort_val = int(how_many)
                            display_val = str(how_many)
                        except:
                            sort_val = 1
                            display_val = "X"

                    results.append({
                        "מיקום": o['locName'],
                        "כמות": display_val,
                        "sort_num": sort_val,
                        "מרחק": round(explorer.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "תאריך": o['obsDt'],
                        "צופה": o.get('userDisplayName', 'אנונימי')
                    })
                
                # מיון לפי הכמות הגבוהה ביותר והצגת 10 הראשונים
                final_df = pd.DataFrame(results).sort_values("sort_num", ascending=False).head(10)
                st.success(f"נמצאו {len(results)} דיווחים ברדיוס של {radius} ק\"מ.")
                st.table(final_df.drop(columns=['sort_num']))
            else:
                st.info(f"לא נמצאו דיווחים עבור {selected_bird}. ודא שהשם המדעי ב-JSON תקין.")
