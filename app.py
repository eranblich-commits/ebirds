import streamlit as st
import requests
import pandas as pd
import math
import random
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim
from datetime import datetime
import time
import json
import os

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

    def get_hotspots_in_region(self, lat, lon, dist):
        """שליפת כל ה-hotspots באזור"""
        try:
            params = {"lat": lat, "lng": lon, "dist": dist, "fmt": "json"}
            response = requests.get(
                f"{self.base_url}/ref/hotspot/geo",
                headers=self.headers,
                params=params,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            st.warning(f"שגיאה בשליפת hotspots: {e}")
        return []

    def get_species_list_for_location(self, loc_id, days):
        """שליפת רשימת כל המינים במוקד מסוים"""
        try:
            params = {"back": days}
            response = requests.get(
                f"{self.base_url}/data/obs/{loc_id}/recent",
                headers=self.headers,
                params=params,
                timeout=15
            )
            if response.status_code == 200:
                return response.json()
            time.sleep(0.05)  # מניעת חסימה
        except Exception as e:
            pass
        return []

    def fetch_comprehensive_data_with_hotspots(self, lat, lon, dist, days, progress_bar=None):
        """גישה חדשה: שליפה לפי hotspots למדויקות מלאה"""
        
        # שלב 1: שליפת כל ה-hotspots
        if progress_bar:
            progress_bar.progress(0.1, "שולף רשימת מוקדים...")
        
        hotspots = self.get_hotspots_in_region(lat, lon, dist)
        
        if not hotspots:
            st.warning("לא נמצאו hotspots באזור - מנסה שיטה חלופית...")
            return self.fetch_basic_data(lat, lon, dist, days, progress_bar)
        
        st.info(f"נמצאו {len(hotspots)} מוקדים - שואב נתונים מכל אחד...")
        
        # שלב 2: שליפת נתונים מכל hotspot
        all_observations = []
        hotspot_species_count = {}
        
        for idx, hotspot in enumerate(hotspots[:150]):  # מגבלה של 150 מוקדים
            if idx % 10 == 0 and progress_bar:
                progress = 0.1 + (idx / len(hotspots[:150])) * 0.8
                progress_bar.progress(progress, f"עיבוד מוקד {idx + 1}/{len(hotspots[:150])}...")
            
            loc_id = hotspot['locId']
            observations = self.get_species_list_for_location(loc_id, days)
            
            if observations:
                # שמירת כמות המינים הייחודיים במוקד
                unique_species = set(obs['sciName'] for obs in observations if 'sciName' in obs)
                hotspot_species_count[loc_id] = {
                    'count': len(unique_species),
                    'name': hotspot['locName'],
                    'lat': hotspot['lat'],
                    'lng': hotspot['lng']
                }
                
                # הוספת המידע על המיקום לכל תצפית
                for obs in observations:
                    obs['locName'] = hotspot['locName']
                    obs['lat'] = hotspot['lat']
                    obs['lng'] = hotspot['lng']
                
                all_observations.extend(observations)
        
        if progress_bar:
            progress_bar.progress(0.95, "ממזג נתונים...")
        
        # המרה ל-DataFrame
        df = pd.DataFrame(all_observations) if all_observations else pd.DataFrame()
        
        if not df.empty:
            df = df.drop_duplicates(subset=['subId', 'sciName', 'howMany'], keep='first')
        
        return df, hotspot_species_count

    def fetch_basic_data(self, lat, lon, dist, days, progress_bar=None):
        """שיטה בסיסית כגיבוי"""
        all_data = []
        
        base_params = {
            "lat": lat, "lng": lon, "dist": dist, "back": days,
            "fmt": "json", "includeProvisional": "true", "maxResults": 10000
        }
        
        endpoints = [
            f"{self.base_url}/data/obs/geo/recent",
            f"{self.base_url}/data/obs/geo/recent/notable",
        ]
        
        for idx, url in enumerate(endpoints):
            try:
                if progress_bar:
                    progress_bar.progress((idx + 1) / 3, f"שולף נתונים {idx + 1}/2...")
                response = requests.get(url, headers=self.headers, params=base_params, timeout=30)
                if response.status_code == 200:
                    all_data.extend(response.json())
            except Exception as e:
                st.warning(f"שגיאה: {e}")
        
        df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df.empty:
            df = df.drop_duplicates(subset=['subId', 'sciName'], keep='first')
        
        # חישוב בסיסי של מינים לכל מוקד
        hotspot_species_count = {}
        if not df.empty:
            for loc_id, group in df.groupby('locId'):
                hotspot_species_count[loc_id] = {
                    'count': group['sciName'].nunique(),
                    'name': group.iloc[0]['locName'],
                    'lat': group.iloc[0]['lat'],
                    'lng': group.iloc[0]['lng']
                }
        
        return df, hotspot_species_count

def load_birds_data():
    """טוען את רשימת הציפורות מקובץ birds.json"""
    
    # רשימת נתיבים אפשריים
    possible_paths = [
        "/mnt/user-data/uploads/birds.json",
        "./birds.json",
        "birds.json",
        "/home/claude/birds.json"
    ]
    
    # ניסיון לטעון מכל נתיב
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    birds_data = json.load(f)
                    st.sidebar.success(f"✅ קובץ ציפורים נטען מ: {os.path.basename(path)}")
                    return birds_data
            except Exception as e:
                st.sidebar.warning(f"שגיאה בקריאת {path}: {e}")
    
    # חיפוש כלי של JSON באזור uploads
    upload_dir = "/mnt/user-data/uploads"
    if os.path.exists(upload_dir):
        all_files = os.listdir(upload_dir)
        json_files = [f for f in all_files if f.endswith('.json')]
        
        if json_files:
            try:
                json_path = os.path.join(upload_dir, json_files[0])
                with open(json_path, 'r', encoding='utf-8') as f:
                    birds_data = json.load(f)
                    st.sidebar.success(f"✅ נטען: {json_files[0]}")
                    return birds_data
            except Exception as e:
                st.sidebar.error(f"שגיאה בקריאת JSON: {e}")
    
    # רשימה בסיסית כברירת מחדל
    st.sidebar.error("❌ לא נמצא קובץ birds.json")
    st.sidebar.info("💡 שים את birds.json באותה תיקייה או העלה אותו")
    
    return [
        {"heb": "דרור הבית", "eng": "House Sparrow", "sci": "Passer domesticus"},
        {"heb": "בולבול", "eng": "Common Bulbul", "sci": "Pycnonotus barbatus"},
        {"heb": "עורב מצוי", "eng": "Hooded Crow", "sci": "Corvus cornix"},
    ]

# ===================== UI =====================

st.title("🇮🇱 צפרות ישראל - גרסת Hotspots המדויקת")

with st.sidebar:
    st.header("⚙️ הגדרות")
    api_key = st.text_input("🔑 eBird API Key:", type="password")
    
    st.subheader("📍 מיקום")
    mode = st.radio("מרכז החיפוש:", ["כפר סבא", "GPS", "עיר"])
    clat, clon = 32.175, 34.906
    
    if mode == "GPS":
        loc = get_geolocation()
        if loc: 
            clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
            st.success(f"📍 {clat:.4f}, {clon:.4f}")
    elif mode == "עיר":
        city = st.text_input("שם עיר:", "Kfar Saba")
        try:
            geo = Nominatim(user_agent=f"ebird_{random.randint(1,9999)}").geocode(f"{city}, Israel")
            if geo: 
                clat, clon = geo.latitude, geo.longitude
                st.success(f"📍 {city}")
        except Exception as e:
            st.error(f"שגיאה: {e}")
    
    st.subheader("🔍 פרמטרים")
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 50)
    days = st.slider("ימים אחורה:", 1, 30, 14)
    
    st.divider()
    st.caption("birds.json: רשימת ציפורות בפורמט [{'heb':'...','eng':'...','sci':'...'}]")

if not api_key:
    st.warning("⚠️ הזן API Key מ-eBird")
    st.info("📝 קבל מפתח חינם: https://ebird.org/api/keygen")
    st.stop()

engine = eBirdEngine(api_key)

if st.button("🚀 סריקה מלאה (כל המוקדים)", type="primary", use_container_width=True):
    progress_bar = st.progress(0, "מתחיל...")
    
    with st.spinner("סורק את כל המוקדים באזור..."):
        df, hotspot_counts = engine.fetch_comprehensive_data_with_hotspots(
            clat, clon, radius, days, progress_bar
        )
        
        if not df.empty:
            df['distance'] = df.apply(
                lambda x: engine.calculate_distance(clat, clon, x['lat'], x['lng']),
                axis=1
            )
            
            st.session_state['master_df'] = df
            st.session_state['hotspot_counts'] = hotspot_counts
            
            progress_bar.progress(1.0, "✅ הושלם!")
            time.sleep(0.3)
            progress_bar.empty()
            
            st.success(f"""
            ✅ **הסריקה הושלמה!**
            - 📊 {len(df):,} תצפיות
            - 📍 {df['locId'].nunique()} מוקדים  
            - 🦅 {df['sciName'].nunique()} מינים שונים
            """)
        else:
            st.error("❌ לא נמצאו נתונים")
            progress_bar.empty()

if 'master_df' in st.session_state:
    df = st.session_state['master_df']
    hotspot_counts = st.session_state.get('hotspot_counts', {})
    
    tab1, tab2, tab3 = st.tabs([
        "🏆 10 מוקדים עשירים", 
        "🎯 תצפיות שיא למין",
        "📊 סטטיסטיקה"
    ])

    with tab1:
        st.header("🏆 המוקדים העשירים ביותר")
        
        # שימוש בנתונים המדויקים מה-hotspot counts
        location_data = []
        
        for loc_id, data in hotspot_counts.items():
            distance = engine.calculate_distance(clat, clon, data['lat'], data['lng'])
            
            # מציאת התצפית האחרונה במוקד זה
            loc_obs = df[df['locId'] == loc_id]
            latest_date = ""
            if not loc_obs.empty and 'obsDt' in loc_obs.columns:
                latest_date = loc_obs['obsDt'].max()
            
            # יצירת לינק ל-eBird
            ebird_link = f"https://ebird.org/hotspot/{loc_id}"
            
            location_data.append({
                "מיקום": data['name'],
                "מספר מינים": data['count'],
                "מרחק (ק\"מ)": round(distance, 1),
                "תאריך אחרון": latest_date,
                "קישור": ebird_link,
                "locId": loc_id
            })
        
        if location_data:
            locations_df = pd.DataFrame(location_data)
            top_10 = locations_df.sort_values("מספר מינים", ascending=False).head(10)
            
            st.write(f"**🔍 נבדקו {len(locations_df)} מוקדים**")
            
            # הצגת הטבלה עם קישורים
            for idx, row in top_10.iterrows():
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 2, 1])
                    with col1:
                        st.write(f"**{row['מיקום']}**")
                    with col2:
                        st.write(f"🦅 {row['מספר מינים']}")
                    with col3:
                        st.write(f"📍 {row['מרחק (ק״מ)']} ק\"מ")
                    with col4:
                        st.write(f"🕐 {row['תאריך אחרון']}")
                    with col5:
                        st.link_button("🔗", row['קישור'])
                    st.divider()
            
            # גרף
            st.subheader("📊 גרף השוואתי")
            st.bar_chart(top_10.set_index('מיקום')['מספר מינים'])
        else:
            st.info("אין נתוני מוקדים זמינים")

    with tab2:
        st.header("🎯 תצפיות שיא לפי מין")
        
        birds_list = load_birds_data()
        
        # יצירת מפת ציפורות
        bird_map = {}
        for bird in birds_list:
            key = f"{bird.get('heb', 'Unknown')} ({bird.get('eng', 'Unknown')})"
            bird_map[key] = bird.get('sci', '')
        
        selected_bird = st.selectbox(
            "🔍 בחר ציפור:",
            [""] + sorted(list(bird_map.keys())),
            key="bird_select"
        )
        
        if selected_bird:
            target_sci = bird_map.get(selected_bird, "")
            
            if not target_sci:
                st.error("לא נמצא שם מדעי")
            else:
                matches = df[df['sciName'].str.contains(target_sci, case=False, na=False, regex=False)].copy()
                
                if not matches.empty:
                    matches['sort_qty'] = pd.to_numeric(matches['howMany'], errors='coerce').fillna(1).astype(int)
                    top_10 = matches.sort_values("sort_qty", ascending=False).head(10)
                    
                    # בדיקה אילו עמודות קיימות
                    available_cols = []
                    col_mapping = {
                        'locName': 'מיקום',
                        'howMany': 'כמות',
                        'distance': 'מרחק (ק"מ)',
                        'obsDt': 'תאריך',
                        'userDisplayName': 'צופה'
                    }
                    
                    for col, name in col_mapping.items():
                        if col in top_10.columns:
                            available_cols.append(col)
                    
                    if available_cols:
                        display = top_10[available_cols].copy()
                        display.columns = [col_mapping[col] for col in available_cols]
                        
                        if 'מרחק (ק"מ)' in display.columns:
                            display['מרחק (ק"מ)'] = display['מרחק (ק"מ)'].round(1)
                        
                        st.write(f"**נמצאו {len(matches)} תצפיות של {selected_bird}**")
                        st.dataframe(display.reset_index(drop=True), use_container_width=True, hide_index=True)
                    else:
                        st.error("לא ניתן להציג נתונים - עמודות חסרות")
                else:
                    st.info(f"לא נמצאו תצפיות של {selected_bird}")

    with tab3:
        st.header("📊 סטטיסטיקה כללית")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("סה\"כ תצפיות", f"{len(df):,}")
        with col2:
            st.metric("מינים שונים", f"{df['sciName'].nunique()}")
        with col3:
            st.metric("מוקדים", f"{df['locId'].nunique()}")
        
        st.subheader("🦅 המינים הנצפים ביותר")
        
        # ספירת תצפיות לפי מין ושם באנגלית
        if 'comName' in df.columns:
            species_counts = df.groupby('comName').size().sort_values(ascending=False).head(10)
            st.bar_chart(species_counts)
            
            # טבלה מפורטת
            species_details = []
            for species_name in species_counts.index:
                species_df = df[df['comName'] == species_name]
                total_individuals = 0
                
                # חישוב סכום הפרטים
                for qty in species_df['howMany']:
                    try:
                        if pd.notna(qty) and qty != 'X':
                            total_individuals += int(qty)
                        else:
                            total_individuals += 1  # X = לפחות 1
                    except:
                        total_individuals += 1
                
                species_details.append({
                    "מין (אנגלית)": species_name,
                    "מספר תצפיות": len(species_df),
                    "סה\"כ פרטים": total_individuals
                })
            
            st.write("**פירוט מינים:**")
            st.dataframe(
                pd.DataFrame(species_details),
                use_container_width=True,
                hide_index=True
            )
        else:
            # אם אין comName, נשתמש ב-sciName
            st.info("שם אנגלי לא זמין - מציג שמות מדעיים")
            species_counts = df['sciName'].value_counts().head(10)
            st.bar_chart(species_counts)
        
        st.subheader("📅 תצפיות לפי תאריך")
        if 'obsDt' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['obsDt']).dt.date
                daily_counts = df.groupby('date').size().sort_index()
                st.line_chart(daily_counts)
            except:
                st.info("לא ניתן להציג גרף תאריכים")
