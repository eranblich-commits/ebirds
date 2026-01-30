import streamlit as st
import requests
import pandas as pd
import time

# הגדרות דף
st.set_page_config(page_title="eBird Israel Explorer", layout="wide")

class eBirdStreamlit:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        # מחוזות ישראל המקוריים
        self.israel_districts = {
            "HaZafon (North)": "IL-Z",
            "HaMerkaz (Center)": "IL-M",
            "HaDarom (South)": "IL-D",
            "Haifa": "IL-HA",
            "Yerushalayim (Jerusalem)": "IL-JM",
            "Tel Aviv": "IL-TA"
        }

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    # מנגנון הזיכרון: שומר את רשימת המוקדים ל-60 דקות כדי לא להוריד מחדש
    @st.cache_data(ttl=3600)
    def get_hotspots(_self, region_codes, api_key):
        all_hotspots = []
        headers = _self.get_headers(api_key)
        for code in region_codes:
            url = f"{_self.base_url}/ref/hotspot/{code}"
            res = requests.get(url, headers=headers, params={"fmt": "json"})
            if res.status_code == 200:
                all_hotspots.extend(res.json())
        return all_hotspots

    # מנגנון הזיכרון: שומר תצפיות ל-10 דקות (כדי להישאר מעודכן אך לחסוך זמן)
    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

# אתחול המערכת
explorer = eBirdStreamlit()

st.title("🇮🇱 eBird Israel Data Explorer")

# סרגל צד
with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("הכנס API Key:", type="password")
    days = st.slider("ימים אחורה:", 1, 30, 7)
    
    selected_names = st.multiselect(
        "בחר מחוזות:", 
        options=list(explorer.israel_districts.keys()),
        default=["HaMerkaz (Center)"]
    )
    region_codes = [explorer.israel_districts[name] for name in selected_names]
    
    # כפתור לניקוי הזיכרון הידני אם רוצים רענון כפוי
    if st.button("רענן נתונים (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

if not api_key:
    st.warning("אנא הכנס API Key בסרגל הצד.")
    st.stop()

# ממשק כפתורים
col1, col2 = st.columns(2)
action_most_birds = col1.button("🔍 מצא ריכוזי ציפורים")
action_most_species = col2.button("🦜 מצא עושר מינים")

if action_most_birds or action_most_species:
    with st.spinner("טוען נתונים (בפעם הראשונה זה עשוי לקחת זמן, לאחר מכן זה יהיה מיידי)..."):
        hotspots = explorer.get_hotspots(tuple(region_codes), api_key)
        results = []
        
        # הגבלת כמות המוקדים לחיפוש מהיר בדוגמה
        max_hotspots = 40 
        progress_bar = st.progress(0)
        
        for i, hs in enumerate(hotspots[:max_hotspots]):
            # כאן המערכת תבדוק אם המידע כבר קיים בזיכרון
            obs = explorer.get_observations(hs['locId'], api_key, days)
            if obs:
                unique_species = len(set(o['sciName'] for o in obs))
                total_birds = sum(o.get('howMany', 0) for o in obs)
                results.append({
                    "מיקום": hs['locName'],
                    "מספר מינים": unique_species,
                    "סה\"כ פרטים": total_birds,
                    "תפר אחרון": obs[0]['userDisplayName'], # תוקן: עברית נשמרת
                    "lat": hs['lat'],
                    "lon": hs['lng']
                })
            progress_bar.progress((i + 1) / max_hotspots)
        
        df = pd.DataFrame(results)
        
        if not df.empty:
            sort_col = "סה\"כ פרטים" if action_most_birds else "מספר מינים"
            df = df.sort_values(by=sort_col, ascending=False)
            
            st.subheader(f"תוצאות לפי {sort_col}")
            st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
            st.map(df)
