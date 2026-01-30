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

# פונקציה לטעינת רשימת הציפורים מקובץ JSON בצורה בטוחה
@st.cache_data
def load_birds_data():
    file_path = 'birds.json'
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            st.error(f"❌ שגיאה במבנה קובץ birds.json בשורה {e.lineno}, עמודה {e.colno}. ודא שאין פסיק מיותר בסוף הרשימה.")
            return []
        except Exception as e:
            st.error(f"❌ שגיאה לא צפויה בטעינת הקובץ: {e}")
            return []
    return []

# טעינת הנתונים
ALL_BIRDS = load_birds_data()
BIRD_OPTIONS = [f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})" for b in ALL_BIRDS]
BIRD_MAP = {f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') for b in ALL_BIRDS}

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.geolocator = Nominatim(user_agent="ebird_israel_pro_v6")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """חישוב מרחק אווירי מדויק בק"מ"""
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
        try:
            res = requests.get(url, headers=headers, params=params)
            all_hs = res.json() if res.status_code == 200 else []
            for hs in all_hs:
                hs['calculated_dist'] = _self.calculate_distance(lat, lon, hs['lat'], hs['lng'])
            return all_hs
        except:
            return []

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        try:
            res = requests.get(url, headers=headers, params=params)
            return res.json() if res.status_code == 200 else []
        except:
            return []

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 צפרות ישראל - Explorer Pro")

with st.sidebar:
    st.header("הגדרות חיפוש")
    api_key = st.text_input("API Key (eBird):", type="password")
    
    mode = st.radio("מרכז חיפוש:", ["כפר סבא", "המיקום שלי (GPS)", "חיפוש עיר"])
    
    clat, clon = 32.175, 34.906 # ברירת מחדל
    
    if mode == "המיקום שלי (GPS)":
        loc = get_geolocation()
        if loc:
            clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
            st.success("📍 המיקום זוהה")
    elif mode == "חיפוש עיר":
        city = st.text_input("שם עיר באנגלית:", "Jerusalem")
        res = explorer.geolocator.geocode(f"{city}, Israel")
        if res: clat, clon = res.latitude, res.longitude

    radius = st.slider("רדיוס חיפוש (ק\"מ):", 1, 100, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין ספציפי"])

with tab1:
    if st.button("🔍 סרוק מוקדים בסביבה"):
        with st.spinner("סורק נתונים..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            results = []
            for hs in hotspots[:60]:
                obs = explorer.get_observations(hs['locId'], api_key, days)
                if obs:
                    results.append({
                        "מיקום": hs.get('locName', 'Unknown'),
                        "ק\"מ": round(hs.get('calculated_dist', 0), 1),
                        "מינים": len(set(o.get('sciName','') for o in obs)),
                        "תאריך": obs[0].get('obsDt', 'N/A').split(' ')[0],
                        "lat": hs.get('lat'), "lon": hs.get('lng')
                    })
            
            if results:
                df = pd.DataFrame(results).sort_values(by="ק\"מ")
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer("ScatterplotLayer", df, get_position=["lon", "lat"], get_color=[200, 30, 0, 160], get_radius=300)],
                    initial_view_state=pdk.ViewState(latitude=clat, longitude=clon, zoom=10)
                ))

with tab2:
    st.subheader("חיפוש מין (עברית / אנגלית)")
    if not BIRD_OPTIONS:
        st.error("לא נטענו ציפורים. בדוק את קובץ birds.json")
    else:
        selected_bird = st.selectbox("בחר ציפור לחיפוש:", [""] + BIRD_OPTIONS)

        if st.button("🎯 חפש תצפיות") and selected_bird:
            sci_name = BIRD_MAP.get(selected_bird)
            with st.spinner(f"מחפש את {selected_bird}..."):
                hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
                s_results = []
                for hs in hotspots[:80]:
                    obs = explorer.get_observations(hs['locId'], api_key, days)
                    # חיפוש בטוח ללא קריסה אם שמות חסרים
                    matches = [o for o in obs if sci_name.lower() in o.get('sciName','').lower()]
                    if matches:
                        best = max(matches, key=lambda x: x.get('howMany', 1) if isinstance(x.get('howMany'), int) else 1)
                        s_results.append({
                            "מיקום": hs.get('locName', 'Unknown'),
                            "ק\"מ": round(hs.get('calculated_dist', 0), 1),
                            "כמות": best.get('howMany', 1),
                            "צופה": best.get('userDisplayName', 'אנונימי'),
                            "תאריך": best.get('obsDt', 'N/A').split(' ')[0],
                            "lat": hs.get('lat'), "lon": hs.get('lng')
                        })
                
                if s_results:
                    sdf = pd.DataFrame(s_results).sort_values(by="ק\"מ")
                    st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True)
                    st.pydeck_chart(pdk.Deck(
                        layers=[pdk.Layer("ScatterplotLayer", sdf, get_position=["lon", "lat"], get_color=[0, 128, 255, 160], get_radius=400)],
                        initial_view_state=pdk.ViewState(latitude=clat, longitude=clon, zoom=10)
                    ))
                else:
                    st.info("לא נמצאו תצפיות למין זה בטווח הנבחר.")
