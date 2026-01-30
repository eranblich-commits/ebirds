import streamlit as st
import requests
import pandas as pd
import math
import random
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

st.set_page_config(page_title="eBird Israel Ultimate Pro", layout="wide")

class eBirdEngine:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {"X-eBirdApiToken": api_key}
        self.base_url = "https://api.ebird.org/v2"

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def fetch_comprehensive_data(self, lat, lon, dist, days):
        """שואב נתונים מכמה מקורות במקביל כדי להגיע למקסימום תצפיות"""
        params = {"lat": lat, "lng": lon, "dist": dist, "back": days, "fmt": "json", "includeProvisional": "true"}
        
        # 1. תצפיות אחרונות כלליות
        r_recent = requests.get(f"{self.base_url}/data/obs/geo/recent", headers=self.headers, params=params)
        # 2. תצפיות 'ראויות לציון' (כאן נמצאים הדיווחים הגדולים והנדירים יותר)
        r_notable = requests.get(f"{self.base_url}/data/obs/geo/recent/notable", headers=self.headers, params=params)
        
        data = []
        if r_recent.status_code == 200: data.extend(r_recent.json())
        if r_notable.status_code == 200: data.extend(r_notable.json())
        
        # הסרת כפילויות לפי מזהה תצפית (obsId) אם קיים
        df = pd.DataFrame(data)
        if not df.empty and 'subId' in df.columns:
            df = df.drop_duplicates(subset=['subId', 'sciName', 'howMany'])
        return df

st.title("🇮🇱 צפרות ישראל - גרסת המקסימום האמיתי")

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

if st.button("🚀 סרוק את כל הרדיוס (סריקה עמוקה)"):
    with st.spinner("שואב וממזג נתונים מכל המקורות..."):
        df = engine.fetch_comprehensive_data(clat, clon, radius, days)
        if not df.empty:
            # חישוב מרחק לכל שורה בנפרד
            df['distance'] = df.apply(lambda x: engine.calculate_distance(clat, clon, x['lat'], x['lng']), axis=1)
            st.session_state['master_df'] = df
            st.success(f"נטענו {len(df)} תצפיות ייחודיות.")
        else:
            st.error("לא התקבלו נתונים מה-API.")

if 'master_df' in st.session_state:
    df = st.session_state['master_df']
    tab1, tab2 = st.tabs(["📊 10 מוקדים עשירים", "🎯 10 תצפיות שיא למין"])

    with tab1:
        # כאן אנחנו סופרים כמה מינים יש באמת בכל מוקד
        summary = []
        for loc_id, group in df.groupby('locId'):
            summary.append({
                "מיקום": group.iloc[0]['locName'],
                "מרחק (ק\"מ)": round(group.iloc[0]['distance'], 1),
                "מספר מינים": group['sciName'].nunique(),
                "עדכון": group['obsDt'].max()
            })
        top_10_locs = pd.DataFrame(summary).sort_values("מספר מינים", ascending=False).head(10)
        st.write("### המוקדים עם מגוון המינים הגדול ביותר ברדיוס")
        st.table(top_10_locs)

    with tab2:
        from birds_data import ALL_BIRDS # בהנחה שזה המבנה שלך, או השתמש ב-load_birds_data
        bird_map = {f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') for b in load_birds_data()}
        selected_bird = st.selectbox("בחר ציפור לניתוח כמויות:", [""] + list(bird_map.keys()))
        
        if selected_bird:
            target_sci = bird_map.get(selected_bird)
            # סינון המין המבוקש - חיפוש גמיש בשם המדעי
            matches = df[df['sciName'].str.contains(target_sci, case=False, na=False)].copy()
            
            if not matches.empty:
                # טיפול בכמויות (X הופך ל-1 לצורכי מיון)
                matches['sort_qty'] = pd.to_numeric(matches['howMany'], errors='coerce').fillna(1).astype(int)
                
                # הצגת 10 התצפיות הגדולות ביותר (ללא איחוד מוקדים - כל דיווח בנפרד!)
                top_10_obs = matches.sort_values("sort_qty", ascending=False).head(10)
                
                display_df = top_10_obs[['locName', 'howMany', 'distance', 'obsDt', 'userDisplayName']].copy()
                display_df.columns = ['מיקום', 'כמות', 'מרחק (ק\"מ)', 'תאריך', 'צופה']
                display_df['מרחק (ק\"מ)'] = display_df['מרחק (ק\"מ)'].round(1)
                
                st.write(f"### 10 התצפיות הגדולות ביותר של {selected_bird}")
                st.table(display_df)
            else:
                st.info("לא נמצאו תצפיות למין זה במאגר שנסרק.")
