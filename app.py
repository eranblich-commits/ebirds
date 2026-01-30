import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import math
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# הגדרות דף
st.set_page_config(page_title="eBird Israel Pro Explorer", layout="wide")

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.city_coordinates = {
            "כפר סבא (Kfar Saba)": {"lat": 32.175, "lon": 34.906},
            "חיפה (Haifa)": {"lat": 32.794, "lon": 34.989},
            "תל אביב (Tel Aviv)": {"lat": 32.085, "lon": 34.781},
            "ירושלים (Jerusalem)": {"lat": 31.768, "lon": 35.213},
            "באר שבע (Beersheba)": {"lat": 31.253, "lon": 34.791},
            "אילת (Eilat)": {"lat": 29.558, "lon": 34.948},
            "נחשולים / מעגן מיכאל": {"lat": 32.561, "lon": 34.923}
        }
        self.geolocator = Nominatim(user_agent="ebird_explorer_israel_v2")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        # חישוב מרחק אווירי פשוט בקילומטרים
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    @st.cache_data(ttl=3600)
    def get_nearby_hotspots(_self, lat, lon, dist, api_key):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/ref/hotspot/geo"
        
        # אם המשתמש ביקש מעל 50 ק"מ, נבצע פיצול בקשות בסיסי
        all_hs = []
        params = {"lat": lat, "lng": lon, "dist": min(dist, 50), "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            all_hs.extend(res.json())
        
        # אם נדרש רדיוס גדול יותר, נשלים נתונים (לוגיקת השלמה בסיסית)
        if dist > 50:
            offset = 0.4 # כ-45 ק"מ
            for d_lat, d_lon in [(offset, 0), (-offset, 0), (0, offset), (0, -offset)]:
                params = {"lat": lat + d_lat, "lng": lon + d_lon, "dist": 30, "fmt": "json"}
                res = requests.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    all_hs.extend(res.json())
        
        # ניקוי כפילויות וחישוב מרחק סופי
        unique_hs = {hs['locId']: hs for hs in all_hs}.values()
        for hs in unique_hs:
            hs['calculated_dist'] = _self.calculate_distance(lat, lon, hs['lat'], hs['lng'])
            
        return [hs for hs in unique_hs if hs['calculated_dist'] <= dist]

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

def display_map(df, lat, lon):
    view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=10)
    st.pydeck_chart(pdk.Deck(
        layers=[
            pdk.Layer("ScatterplotLayer", df, get_position=["lon", "lat"], get_color=[200, 30, 0, 160], get_radius=400, pickable=True),
            pdk.Layer("TextLayer", df, get_position=["lon", "lat"], get_text="מיקום", get_size=14, get_color=[255,255,255], get_pixel_offset=[0, -10])
        ],
        initial_view_state=view_state,
        tooltip={"text": "{מיקום}"}
    ))

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 eBird Israel Pro Explorer")

with st.sidebar:
    st.header("הגדרות מיקום")
    api_key = st.text_input("API Key:", type="password")
    mode = st.radio("נקודת מרכז:", ["עיר מרכזית", "חיפוש עיר חופשי", "המיקום שלי"])
    
    clat, clon = 32.175, 34.906 # כפ"ס
    location_name = "כפר סבא"

    if mode == "עיר מרכזית":
        city = st.selectbox("בחר עיר:", list(explorer.city_coordinates.keys()))
        clat, clon = explorer.city_coordinates[city]["lat"], explorer.city_coordinates[city]["lon"]
        location_name = city
    elif mode == "חיפוש עיר חופשי":
        free_city = st.text_input("שם עיר באנגלית:", "Kfar Saba")
        loc = explorer.geolocator.geocode(f"{free_city}, Israel")
        if loc:
            clat, clon = loc.latitude, loc.longitude
            location_name = free_city
            st.success(f"נמצא: {loc.address[:30]}...")
    elif mode == "המיקום שלי":
        loc = get_geolocation()
        if loc:
            clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
            location_name = "המיקום שלך"
            st.success("מיקום זוהה!")

    radius = st.slider("רדיוס (ק\"מ):", 1, 100, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הכנס API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות בסביבה", "🎯 חיפוש מין"])

with tab1:
    if st.button(f"🔍 חפש הכל סביב {location_name}"):
        with st.spinner("סורק מוקדים..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            results = []
            progress = st.progress(0)
            for i, hs in enumerate(hotspots[:80]):
                obs = explorer.get_observations(hs['locId'], api_key, days)
                if obs:
                    results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs['calculated_dist'], 1),
                        "מינים": len(set(o['sciName'] for o in obs)),
                        "פרטים": sum(o.get('howMany', 0) for o in obs),
                        "תאריך": obs[0]['obsDt'].split(' ')[0],
                        "lat": hs['lat'], "lon": hs['lng']
                    })
                progress.progress((i+1)/len(hotspots[:80]))
            
            if results:
                df = pd.DataFrame(results).sort_values(by="מינים", ascending=False)
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True,
                             column_config={"מיקום": st.column_config.TextColumn(pinned=True)})
                display_map(df, clat, clon)

with tab2:
    st.subheader("חפש מין ספציפי ברדיוס")
    sp_input = st.text_input("שם ציפור (אנגלית/מדעי):", placeholder="למשל: Common Crane")
    if st.button("🎯 חפש מין") and sp_input:
        with st.spinner(f"מחפש {sp_input}..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            s_results = []
            for hs in hotspots[:80]:
                obs = explorer.get_observations(hs['locId'], api_key, days)
                matches = [o for o in obs if sp_input.lower() in o.get('comName','').lower() or sp_input.lower() in o.get('sciName','').lower()]
                if matches:
                    best = max(matches, key=lambda x: x.get('howMany', 0))
                    s_results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs['calculated_dist'], 1),
                        "כמות": best.get('howMany', 0),
                        "תאריך": best.get('obsDt', '').split(' ')[0],
                        "lat": hs['lat'], "lon": hs['lng']
                    })
            if s_results:
                sdf = pd.DataFrame(s_results).sort_values(by="כמות", ascending=False)
                st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True,
                             column_config={"מיקום": st.column_config.TextColumn(pinned=True)})
                display_map(sdf, clat, clon)
            else:
                st.info("לא נמצאו תצפיות למין זה בטווח הנבחר.")
