import streamlit as st
import requests
import pandas as pd
import math
import random
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim
from datetime import datetime
import time

st.set_page_config(page_title="eBird Israel Ultimate Pro", layout="wide")

class eBirdEngine:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {"X-eBirdApiToken": api_key}
        self.base_url = "https://api.ebird.org/v2"
        self.checklist_cache = {}  # מטמון לדיווחים מלאים

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def get_checklist_details(self, sub_id):
        """שולף דיווח מלא עם כל המינים שבו"""
        if sub_id in self.checklist_cache:
            return self.checklist_cache[sub_id]
        
        try:
            url = f"{self.base_url}/product/checklist/view/{sub_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.checklist_cache[sub_id] = data
                return data
            time.sleep(0.1)  # למנוע חסימה מה-API
        except Exception as e:
            st.warning(f"שגיאה בשליפת דיווח {sub_id}: {e}")
        return None

    def fetch_comprehensive_data(self, lat, lon, dist, days, progress_bar=None):
        """שואב נתונים ואז משלים עם דיווחים מלאים"""
        all_data = []
        
        base_params = {
            "lat": lat, 
            "lng": lon, 
            "dist": dist, 
            "back": days, 
            "fmt": "json", 
            "includeProvisional": "true",
            "maxResults": 10000
        }
        
        # שלב 1: שליפת תצפיות בסיסיות
        endpoints = [
            ("תצפיות רגילות", f"{self.base_url}/data/obs/geo/recent"),
            ("תצפיות ראויות לציון", f"{self.base_url}/data/obs/geo/recent/notable"),
        ]
        
        for idx, (name, url) in enumerate(endpoints):
            try:
                if progress_bar:
                    progress_bar.progress((idx + 1) / (len(endpoints) + 1), f"שולף {name}...")
                response = requests.get(url, headers=self.headers, params=base_params, timeout=30)
                if response.status_code == 200:
                    all_data.extend(response.json())
            except Exception as e:
                st.warning(f"שגיאה בטעינת {name}: {e}")
        
        if not all_data:
            return pd.DataFrame(), {}
        
        # המרה ל-DataFrame
        df = pd.DataFrame(all_data)
        df = df.drop_duplicates(subset=['subId', 'sciName'], keep='first')
        
        # שלב 2: שליפת דיווחים מלאים
        unique_subs = df['subId'].unique()
        if progress_bar:
            progress_bar.progress(0.7, f"שולף {len(unique_subs)} דיווחים מלאים...")
        
        checklist_species_count = {}
        
        for idx, sub_id in enumerate(unique_subs[:100]):  # מגבלה של 100 דיווחים
            if idx % 10 == 0 and progress_bar:
                progress_bar.progress(0.7 + (idx / len(unique_subs[:100])) * 0.3, 
                                    f"עיבוד דיווח {idx + 1}/{min(len(unique_subs), 100)}...")
            
            checklist = self.get_checklist_details(sub_id)
            if checklist and 'obs' in checklist:
                # ספירת מינים ייחודיים בדיווח
                species_in_checklist = set()
                for obs in checklist['obs']:
                    if 'sciName' in obs:
                        species_in_checklist.add(obs['sciName'])
                checklist_species_count[sub_id] = len(species_in_checklist)
        
        return df, checklist_species_count

def load_birds_data():
    """טוען את רשימת הציפורות מהקובץ birds.json"""
    import os
    import json
    
    # נתיבים אפשריים לקובץ
    possible_paths = [
        "/mnt/user-data/uploads/birds.json",  # קובץ שהועלה
        "./birds.json",  # בתיקייה הנוכחית
        "birds.json"  # בתיקיית העבודה
    ]
    
    # ניסיון לטעון מכל נתיב אפשרי
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    birds_data = json.load(f)
                st.success(f"✅ נטען קובץ ציפורים מ: {path}")
                return birds_data
            except Exception as e:
                st.warning(f"שגיאה בקריאת {path}: {e}")
    
    # אם לא נמצא - ניסיון לטעון מ-birds_data.py
    try:
        from birds_data import ALL_BIRDS
        st.info("נטען מקובץ birds_data.py")
        return ALL_BIRDS
    except (ImportError, ModuleNotFoundError):
        pass
    
    # בדיקה כללית של כל הקבצים בתיקיית uploads
    upload_dir = "/mnt/user-data/uploads"
    if os.path.exists(upload_dir):
        files = os.listdir(upload_dir)
        
        # חיפוש כל קובץ JSON
        json_files = [f for f in files if f.endswith('.json')]
        if json_files:
            try:
                with open(os.path.join(upload_dir, json_files[0]), 'r', encoding='utf-8') as f:
                    birds_data = json.load(f)
                st.success(f"✅ נטען קובץ: {json_files[0]}")
                return birds_data
            except Exception as e:
                st.warning(f"שגיאה בקריאת JSON: {e}")
        
        # חיפוש קבצי CSV
        csv_files = [f for f in files if f.endswith('.csv')]
        if csv_files:
            try:
                df = pd.read_csv(os.path.join(upload_dir, csv_files[0]))
                birds = []
                for _, row in df.iterrows():
                    birds.append({
                        "heb": row.get('heb', row.get('hebrew', row.get('שם עברי', 'Unknown'))),
                        "eng": row.get('eng', row.get('english', row.get('שם אנגלי', 'Unknown'))),
                        "sci": row.get('sci', row.get('scientific', row.get('שם מדעי', '')))
                    })
                st.success(f"✅ נטען קובץ CSV: {csv_files[0]}")
                return birds
            except Exception as e:
                st.warning(f"שגיאה בקריאת CSV: {e}")
    
    # רשימה בסיסית כברירת מחדל
    st.error("❌ לא נמצא קובץ birds.json - העלה את הקובץ או שים אותו באותה תיקייה")
    st.info("💡 הקובץ צריך להיות ברשימה של אובייקטים עם המפתחות: heb, eng, sci")
    return [
        {"heb": "דרור הבית", "eng": "House Sparrow", "sci": "Passer domesticus"},
        {"heb": "בולבול", "eng": "Common Bulbul", "sci": "Pycnonotus barbatus"},
        {"heb": "עורב מצוי", "eng": "Hooded Crow", "sci": "Corvus cornix"},
    ]

st.title("🇮🇱 צפרות ישראל - גרסת הדיווחים המלאים")

with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("API Key:", type="password")
    
    st.subheader("מיקום")
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
            geo = Nominatim(user_agent=f"ebird_app_{random.randint(1,9999)}").geocode(f"{city}, Israel")
            if geo: 
                clat, clon = geo.latitude, geo.longitude
                st.success(f"📍 {city}: {clat:.4f}, {clon:.4f}")
        except Exception as e:
            st.error(f"שגיאה: {e}")
    
    st.subheader("פרמטרי חיפוש")
    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 50)
    days = st.slider("ימים אחורה:", 1, 30, 14)
    
    st.info("💡 העלה קובץ birds.json עם רשימת הציפורות או שים אותו באותה תיקייה")

if not api_key:
    st.warning("⚠️ הזן API Key מ-eBird להפעלה")
    st.info("קבל API Key בחינם מ: https://ebird.org/api/keygen")
    st.stop()

engine = eBirdEngine(api_key)

if st.button("🚀 התחל סריקה מלאה", type="primary"):
    progress_bar = st.progress(0, "מתחיל סריקה...")
    
    with st.spinner("שואב נתונים..."):
        df, checklist_counts = engine.fetch_comprehensive_data(clat, clon, radius, days, progress_bar)
        
        if not df.empty:
            # חישוב מרחק
            df['distance'] = df.apply(
                lambda x: engine.calculate_distance(clat, clon, x['lat'], x['lng']), 
                axis=1
            )
            
            # הוספת מידע על כמות מינים בדיווח
            df['checklist_species_count'] = df['subId'].map(checklist_counts)
            
            st.session_state['master_df'] = df
            st.session_state['checklist_counts'] = checklist_counts
            
            progress_bar.progress(1.0, "הושלם!")
            time.sleep(0.5)
            progress_bar.empty()
            
            st.success(f"✅ נטענו {len(df):,} תצפיות מ-{df['locId'].nunique()} מוקדים ו-{len(checklist_counts)} דיווחים מלאים")
        else:
            st.error("❌ לא התקבלו נתונים. בדוק API Key ופרמטרים.")
            progress_bar.empty()

if 'master_df' in st.session_state:
    df = st.session_state['master_df']
    checklist_counts = st.session_state.get('checklist_counts', {})
    
    tab1, tab2, tab3 = st.tabs([
        "📊 10 מוקדים עשירים", 
        "🎯 תצפיות שיא למין",
        "📋 דיווחים מפורטים"
    ])

    with tab1:
        st.header("🏆 המוקדים עם עושר המינים הגבוה ביותר")
        
        # חישוב אמיתי לפי דיווחים מלאים
        location_analysis = []
        
        for loc_id, group in df.groupby('locId'):
            loc_name = group.iloc[0]['locName']
            distance = group.iloc[0]['distance']
            
            # אם יש לנו דיווחים מלאים - נשתמש בהם
            checklists_at_location = group['subId'].unique()
            max_species_in_checklist = 0
            total_unique_species = group['sciName'].nunique()
            
            for sub_id in checklists_at_location:
                if sub_id in checklist_counts:
                    count = checklist_counts[sub_id]
                    if count > max_species_in_checklist:
                        max_species_in_checklist = count
            
            # נשתמש במקסימום בין שתי השיטות
            final_count = max(max_species_in_checklist, total_unique_species)
            
            location_analysis.append({
                "מיקום": loc_name,
                "מרחק (ק\"מ)": round(distance, 1),
                "מספר מינים": final_count,
                "דיווחים": len(checklists_at_location),
                "עדכון אחרון": group['obsDt'].max()
            })
        
        summary_df = pd.DataFrame(location_analysis)
        top_10 = summary_df.sort_values("מספר מינים", ascending=False).head(10)
        
        st.write(f"**נותחו {len(summary_df)} מוקדים**")
        
        # הוספת צבע לשורות
        st.dataframe(
            top_10.reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
        # גרף
        st.bar_chart(top_10.set_index('מיקום')['מספר מינים'])

    with tab2:
        st.header("🎯 תצפיות שיא לפי מין")
        
        birds_list = load_birds_data()
        bird_map = {
            f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') 
            for b in birds_list
        }
        
        selected_bird = st.selectbox(
            "בחר ציפור:", 
            [""] + sorted(list(bird_map.keys())),
            key="bird_selector"
        )
        
        if selected_bird:
            target_sci = bird_map.get(selected_bird, "")
            
            if not target_sci:
                st.error("לא נמצא שם מדעי")
            else:
                matches = df[df['sciName'].str.contains(target_sci, case=False, na=False, regex=False)].copy()
                
                if not matches.empty:
                    matches['sort_qty'] = pd.to_numeric(matches['howMany'], errors='coerce').fillna(1).astype(int)
                    top_10_obs = matches.sort_values("sort_qty", ascending=False).head(10)
                    
                    display_df = top_10_obs[[
                        'locName', 'howMany', 'distance', 'obsDt', 
                        'userDisplayName', 'checklist_species_count'
                    ]].copy()
                    
                    display_df.columns = [
                        'מיקום', 'כמות', 'מרחק (ק\"מ)', 
                        'תאריך', 'צופה', 'סה"כ מינים בדיווח'
                    ]
                    display_df['מרחק (ק\"מ)'] = display_df['מרחק (ק\"מ)'].round(1)
                    
                    st.write(f"**נמצאו {len(matches)} תצפיות של {selected_bird}**")
                    st.dataframe(
                        display_df.reset_index(drop=True),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info(f"לא נמצאו תצפיות של {selected_bird}")

    with tab3:
        st.header("📋 פירוט דיווחים מלאים")
        
        if checklist_counts:
            checklist_df_data = []
            for sub_id, count in sorted(checklist_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
                obs_in_checklist = df[df['subId'] == sub_id].iloc[0]
                checklist_df_data.append({
                    "דיווח": sub_id,
                    "מיקום": obs_in_checklist['locName'],
                    "מינים": count,
                    "תאריך": obs_in_checklist['obsDt'],
                    "צופה": obs_in_checklist['userDisplayName']
                })
            
            checklist_display = pd.DataFrame(checklist_df_data)
            st.write("**20 הדיווחים העשירים ביותר:**")
            st.dataframe(checklist_display, use_container_width=True, hide_index=True)
        else:
            st.info("לא נטענו דיווחים מלאים עדיין")
