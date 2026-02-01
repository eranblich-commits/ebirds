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
        """שואב נתונים מכמה מקורות במקביל ומגדיל את כמות התצפיות"""
        all_data = []
        
        # פרמטרים בסיסיים
        base_params = {
            "lat": lat, 
            "lng": lon, 
            "dist": dist, 
            "back": days, 
            "fmt": "json", 
            "includeProvisional": "true",
            "maxResults": 10000  # מקסימום תוצאות
        }
        
        # 1. תצפיות אחרונות כלליות
        try:
            r_recent = requests.get(
                f"{self.base_url}/data/obs/geo/recent", 
                headers=self.headers, 
                params=base_params,
                timeout=30
            )
            if r_recent.status_code == 200:
                all_data.extend(r_recent.json())
        except Exception as e:
            st.warning(f"שגיאה בטעינת תצפיות רגילות: {e}")
        
        # 2. תצפיות 'ראויות לציון'
        try:
            r_notable = requests.get(
                f"{self.base_url}/data/obs/geo/recent/notable", 
                headers=self.headers, 
                params=base_params,
                timeout=30
            )
            if r_notable.status_code == 200:
                all_data.extend(r_notable.json())
        except Exception as e:
            st.warning(f"שגיאה בטעינת תצפיות ראויות לציון: {e}")
        
        # 3. תצפיות של מינים נדירים (species)
        try:
            r_species = requests.get(
                f"{self.base_url}/data/obs/geo/recent/species", 
                headers=self.headers, 
                params=base_params,
                timeout=30
            )
            if r_species.status_code == 200:
                all_data.extend(r_species.json())
        except Exception as e:
            st.warning(f"שגיאה בטעינת תצפיות מינים: {e}")
        
        if not all_data:
            return pd.DataFrame()
        
        # המרה ל-DataFrame והסרת כפילויות
        df = pd.DataFrame(all_data)
        
        # הסרת כפילויות מדויקות
        if not df.empty:
            # נשמור רק שורות ייחודיות לפי מזהה דיווח, מין וכמות
            dedup_cols = ['subId', 'sciName']
            if 'howMany' in df.columns:
                dedup_cols.append('howMany')
            df = df.drop_duplicates(subset=dedup_cols, keep='first')
        
        return df

def load_birds_data():
    """טוען את רשימת הציפורות - אם birds_data.py לא קיים, משתמש ברשימה בסיסית"""
    try:
        from birds_data import ALL_BIRDS
        return ALL_BIRDS
    except (ImportError, ModuleNotFoundError):
        # רשימה בסיסית של ציפורות נפוצות בישראל אם הקובץ לא קיים
        st.warning("קובץ birds_data.py לא נמצא - משתמש ברשימה בסיסית")
        return [
            {"heb": "דרור הבית", "eng": "House Sparrow", "sci": "Passer domesticus"},
            {"heb": "בולבול", "eng": "Common Bulbul", "sci": "Pycnonotus barbatus"},
            {"heb": "עורב מצוי", "eng": "Hooded Crow", "sci": "Corvus cornix"},
            {"heb": "תור מצוי", "eng": "European Turtle Dove", "sci": "Streptopelia turtur"},
            {"heb": "יונת בית", "eng": "Rock Dove", "sci": "Columba livia"},
            {"heb": "זמיר לבנון", "eng": "Palestine Sunbird", "sci": "Cinnyris osea"},
            {"heb": "דוכיפת", "eng": "Eurasian Hoopoe", "sci": "Upupa epops"},
            {"heb": "סיסון מצוי", "eng": "European Greenfinch", "sci": "Chloris chloris"},
        ]

st.title("🇮🇱 צפרות ישראל - גרסת המקסימום האמיתי")

with st.sidebar:
    api_key = st.text_input("API Key:", type="password")
    mode = st.radio("מרכז:", ["כפר סבא", "GPS", "עיר"])
    clat, clon = 32.175, 34.906
    if mode == "GPS":
        loc = get_geolocation()
        if loc: 
            clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    elif mode == "עיר":
        city = st.text_input("שם עיר:", "Kfar Saba")
        try:
            geo = Nominatim(user_agent=f"ua_{random.randint(1,999)}").geocode(f"{city}, Israel")
            if geo: 
                clat, clon = geo.latitude, geo.longitude
        except Exception as e:
            st.error(f"שגיאה במציאת העיר: {e}")
    
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
            st.success(f"✅ נטענו {len(df)} תצפיות ייחודיות מ-{df['locId'].nunique()} מוקדים שונים")
        else:
            st.error("לא התקבלו נתונים מה-API. בדוק את ה-API Key והפרמטרים.")

if 'master_df' in st.session_state:
    df = st.session_state['master_df']
    tab1, tab2 = st.tabs(["📊 10 מוקדים עשירים", "🎯 10 תצפיות שיא למין"])

    with tab1:
        # חישוב עושר מינים אמיתי לכל מוקד
        summary = []
        for loc_id, group in df.groupby('locId'):
            # ספירת מינים ייחודיים באמת (לפי שם מדעי)
            unique_species = group['sciName'].nunique()
            
            summary.append({
                "מיקום": group.iloc[0]['locName'],
                "מרחק (ק\"מ)": round(group.iloc[0]['distance'], 1),
                "מספר מינים": unique_species,
                "סה\"כ תצפיות": len(group),
                "עדכון": group['obsDt'].max()
            })
        
        summary_df = pd.DataFrame(summary)
        
        # מיון לפי מספר מינים (עושר) בסדר יורד
        top_10_locs = summary_df.sort_values("מספר מינים", ascending=False).head(10)
        
        st.write("### 🏆 10 המוקדים עם מגוון המינים הגדול ביותר ברדיוס")
        st.write(f"**נבדקו {len(summary_df)} מוקדים סה\"כ**")
        
        # הצגה בטבלה ברורה
        display_cols = ["מיקום", "מספר מינים", "סה\"כ תצפיות", "מרחק (ק\"מ)", "עדכון"]
        st.dataframe(
            top_10_locs[display_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True
        )

    with tab2:
        # טעינת רשימת הציפורות
        birds_list = load_birds_data()
        bird_map = {
            f"{b.get('heb', 'Unknown')} ({b.get('eng', 'Unknown')})": b.get('sci', '') 
            for b in birds_list
        }
        
        selected_bird = st.selectbox("בחר ציפור לניתוח כמויות:", [""] + sorted(list(bird_map.keys())))
        
        if selected_bird:
            target_sci = bird_map.get(selected_bird, "")
            
            if not target_sci:
                st.error("לא נמצא שם מדעי לציפור זו")
            else:
                # סינון המין המבוקש - חיפוש גמיש בשם המדעי
                matches = df[df['sciName'].str.contains(target_sci, case=False, na=False, regex=False)].copy()
                
                if not matches.empty:
                    # טיפול בכמויות (X הופך ל-1 לצורכי מיון)
                    matches['sort_qty'] = pd.to_numeric(matches['howMany'], errors='coerce').fillna(1).astype(int)
                    
                    # הצגת 10 התצפיות הגדולות ביותר (ללא איחוד מוקדים - כל דיווח בנפרד!)
                    top_10_obs = matches.sort_values("sort_qty", ascending=False).head(10)
                    
                    display_df = top_10_obs[['locName', 'howMany', 'distance', 'obsDt', 'userDisplayName']].copy()
                    display_df.columns = ['מיקום', 'כמות', 'מרחק (ק\"מ)', 'תאריך', 'צופה']
                    display_df['מרחק (ק\"מ)'] = display_df['מרחק (ק\"מ)'].round(1)
                    
                    st.write(f"### 🎯 10 התצפיות הגדולות ביותר של {selected_bird}")
                    st.write(f"**נמצאו {len(matches)} תצפיות סה\"כ**")
                    st.dataframe(
                        display_df.reset_index(drop=True),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info(f"לא נמצאו תצפיות של {selected_bird} במאגר שנסרק (שם מדעי: {target_sci})")
