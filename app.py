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
            "אילת (Eilat)": {"lat": 29.558, "lon": 34.948}
        }
        self.geolocator = Nominatim(user_agent="ebird_explorer_israel_v3")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    @st.cache_data(ttl=86400) # שמירה ליום שלם - רשימת המינים לא משתנה בתכיפות
    def get_israel_species(_self, api_key):
        """טעינת רשימת כל המינים בישראל לצורך השלמה אוטומטית"""
        headers = _self.get_headers(api_key)
        # נבקש את רשימת המינים עבור ישראל (IL)
        url = f"{_self.base_url}/ref/taxonomy/ebird"
        params = {"fmt": "json", "loc": "IL"}
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            # מחזיר רשימה של שמות נפוצים באנגלית
            return sorted([f"{item['comName']} ({item['sciName']})" for item in data])
        return []

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
        return all_hs

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

# אתחול
explorer = eBirdRadiusExplorer()
st.title("🇮🇱 eBird Israel Pro Explorer")

with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("API Key:", type="password")
    mode = st.radio("מרכז חיפוש:", ["עיר מרכזית", "המיקום שלי", "חיפוש חופשי"])
    
    clat, clon = 32.175, 34.906
    if mode == "עיר מרכזית":
        city = st.selectbox("עיר:", list(explorer.city_coordinates.keys()))
        clat, clon = explorer.city_coordinates[city]["lat"], explorer.city_coordinates[city]["lon"]
    elif mode == "המיקום שלי":
        loc = get_geolocation()
        if loc: clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    
    radius = st.slider("רדיוס (ק\"מ):", 1, 100, 20)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("הכנס API Key להמשך")
    st.stop()

# טעינת המינים להשלמה אוטומטית
all_bird_species = explorer.get_israel_species(api_key)

tab1, tab2 = st.tabs(["📊 תצפיות בסביבה", "🎯 חיפוש מין (עם השלמה)"])

with tab1:
    if st.button("🔍 חפש הכל באזור"):
        # לוגיקה קודמת... (זהה למה שעבד לך)
        st.write("מבצע חיפוש...")
        # (כאן תבוא הלוגיקה של טאב 1 מהקוד הקודם)

with tab2:
    st.subheader("חיפוש מין ספציפי")
    st.markdown("ניתן להתחיל להקליד שם באנגלית, המערכת תשלים אותך אוטומטית.")
    
    # השלמה אוטומטית מהרשימה שמשכנו מ-eBird
    selected_bird = st.selectbox("בחר מין מהרשימה:", [""] + all_bird_species)
    
    # תמיכה בעברית - תיבת טקסט חופשית למקרה של שם בעברית
    hebrew_name = st.text_input("או הקלד שם חופשי (עברית/אנגלית):")

    if st.button("🎯 חפש תצפיות של המין"):
        search_query = ""
        if selected_bird:
            # חילוץ השם המדעי מהסוגריים כי הוא הכי מדויק לחיפוש
            search_query = selected_bird.split('(')[1].replace(')', '')
        elif hebrew_name:
            search_query = hebrew_name

        if search_query:
            with st.spinner(f"מחפש את {search_query}..."):
                hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
                s_results = []
                for hs in hotspots[:60]:
                    obs = explorer.get_observations(hs['locId'], api_key, days)
                    # חישוב התאמה (תומך גם בשם המדעי וגם בשם הנפוץ)
                    matches = [o for o in obs if search_query.lower() in o.get('comName','').lower() 
                               or search_query.lower() in o.get('sciName','').lower()]
                    
                    if matches:
                        best = max(matches, key=lambda x: x.get('howMany', 0))
                        s_results.append({
                            "מיקום": hs['locName'],
                            "ק\"מ": round(hs['calculated_dist'], 1),
                            "כמות": best.get('howMany', 0),
                            "תאריך": best.get('obsDt', ''),
                            "lat": hs['lat'], "lon": hs['lng']
                        })
                
                if s_results:
                    sdf = pd.DataFrame(s_results).sort_values(by="כמות", ascending=False)
                    st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True,
                                 column_config={"מיקום": st.column_config.TextColumn(pinned=True)})
                else:
                    st.info("לא נמצאו תצפיות למין זה בטווח הזמן והרדיוס שנבחרו.")
