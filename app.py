import streamlit as st
import requests
import pandas as pd
import math
import json
import os
import random
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

st.set_page_config(page_title="eBird Israel Ultimate", layout="wide")

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

class eBirdEngine:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.ebird.org/v2"

    def get_raw_data(self, lat, lon, dist, days):
        """שואב את כל זרם התצפיות הגולמי ללא סינון שרת"""
        url = f"{self.base_url}/data/obs/geo/recent"
        params = {
            "lat": lat, "lng": lon, "dist": dist,
            "back": days, "includeProvisional": "true", "fmt": "json"
        }
        headers = {"X-eBirdApiToken": self.api_key}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

st.title("🇮🇱 צפרות ישראל - גרסת הנתונים המלאים")

with st.sidebar:
    api_key = st.text_input("API Key:", type="password")
    mode = st.radio("מרכז:", ["כפר סבא", "GPS", "עיר"])
    clat, clon = 32.175, 34.906
    if mode == "GPS":
        loc = get_geolocation()
        if loc: clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    elif mode == "עיר":
        city = st.text_input("שם עיר:", "Kfar Saba")
        geo = Nominatim(user_agent=f"ua_{random.randint(1,999)}").geocode(f"{city}, Israel")
        if geo: clat, clon = geo.latitude, geo.longitude
    
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 50)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.warning("הזן API Key להפעלה.")
    st.stop()

engine = eBirdEngine(api_key)

# כפתור מרכזי לשאיבת המאגר הגולמי
if st.button("🔄 טען נתוני שטח מלאים (Raw Scan)"):
    with st.spinner("שואב את כל התצפיות ברדיוס..."):
        # שאיבה אחת גדולה של הכל
        raw_data = engine.get_raw_data(clat, clon, radius, days)
        st.session_state['master_data'] = raw_data
        st.success(f"נטענו {len(raw_data)} תצפיות גולמיות.")

if 'master_data' in st.session_state:
    data = st.session_state['master_data']
    tab1, tab2 = st.tabs(["📊 מוקדים עשירים", "🎯 חיפוש מין (דיוק מקסימלי)"])

    with tab1:
        # עיבוד המוקדים מהנתונים הגולמיים
        df = pd.DataFrame(data)
        if not df.empty:
            summary = []
            for loc_id, group in df.groupby('locId'):
                d = engine.calculate_distance(clat, clon, group.iloc[0]['lat'], group.iloc[0]['lng'])
                summary.append({
                    "מיקום": group.iloc[0]['locName'],
                    "מרחק": round(d, 1),
                    "מינים": len(group['sciName'].unique()),
                    "תאריך": group['obsDt'].max()
                })
            res_df = pd.DataFrame(summary).sort_values("מינים", ascending=False).head(10)
            st.write("### 10 המקומות עם מגוון המינים הגדול ביותר")
            st.table(res_df)

    with tab2:
        selected_bird = st.selectbox("בחר ציפור לניתוח כמויות:", [""] + BIRD_OPTIONS)
        if selected_bird:
            target_sci = BIRD_MAP.get(selected_bird)
            # סינון ידני בתוך הקוד - כאן אנחנו לא מפספסים כלום
            matches = [o for o in data if target_sci.lower() in o.get('sciName', '').lower()]
            
            if matches:
                processed = []
                for o in matches:
                    how_many = o.get('howMany')
                    # לוגיקת X: נחשב כ-1 למיון, מוצג כ-X
                    sort_val = int(how_many) if (how_many and str(how_many).isdigit()) else 1
                    
                    processed.append({
                        "מיקום": o['locName'],
                        "כמות": how_many if how_many else "X",
                        "sort_val": sort_val,
                        "מרחק": round(engine.calculate_distance(clat, clon, o['lat'], o['lng']), 1),
                        "תאריך": o['obsDt'],
                        "צופה": o.get('userDisplayName', 'אנונימי')
                    })
                
                # מיון לפי הכמות הגבוהה ביותר
                final_df = pd.DataFrame(processed).sort_values("sort_val", ascending=False).head(10)
                st.write(f"### 10 התצפיות הגדולות ביותר של {selected_bird}")
                st.table(final_df.drop(columns=['sort_val']))
            else:
                st.info("המין לא נמצא במאגר הגולמי שנטען.")
