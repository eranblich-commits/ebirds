
import streamlit as st
import requests
import pandas as pd

# הגדרות דף
st.set_page_config(page_title="eBird Israel Explorer", layout="wide")

class eBirdStreamlit:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
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

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

explorer = eBirdStreamlit()

st.title("🇮🇱 eBird Israel Data Explorer")

with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("הכנס API Key:", type="password")
    days = st.slider("ימים אחורה לבדיקה:", 1, 30, 7)
    
    selected_names = st.multiselect(
        "בחר מחוזות:", 
        options=list(explorer.israel_districts.keys()),
        default=["HaMerkaz (Center)"]
    )
    region_codes = [explorer.israel_districts[name] for name in selected_names]
    
    if st.button("רענן נתונים (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

if not api_key:
    st.warning("אנא הכנס API Key בסרגל הצד.")
    st.stop()

# יצירת טאבים לממשק נקי יותר
tab1, tab2 = st.tabs(["📊 סקירת אזורים", "🎯 חיפוש מין ספציפי"])

with tab1:
    col1, col2 = st.columns(2)
    action_most_birds = col1.button("🔍 מצא ריכוזי ציפורים")
    action_most_species = col2.button("🦜 מצא עושר מינים")

    if action_most_birds or action_most_species:
        with st.spinner("טוען נתונים..."):
            hotspots = explorer.get_hotspots(tuple(region_codes), api_key)
            results = []
            max_hs = 40 
            progress_bar = st.progress(0)
            
            for i, hs in enumerate(hotspots[:max_hs]):
                obs = explorer.get_observations(hs['locId'], api_key, days)
                if obs:
                    unique_species = len(set(o.get('sciName', '') for o in obs))
                    total_birds = sum(o.get('howMany', 0) for o in obs)
                    # תיקון השגיאה: שימוש ב-.get() למניעת KeyError
                    last_observer = obs[0].get('userDisplayName', 'לא ידוע')
                    
                    results.append({
                        "מיקום": hs.get('locName', 'ללא שם'),
                        "מספר מינים": unique_species,
                        "סה\"כ פרטים": total_birds,
                        "צפר אחרון": last_observer,
                        "lat": hs.get('lat'),
                        "lon": hs.get('lng')
                    })
                progress_bar.progress((i + 1) / max_hs)
            
            df = pd.DataFrame(results)
            if not df.empty:
                sort_col = "סה\"כ פרטים" if action_most_birds else "מספר מינים"
                df = df.sort_values(by=sort_col, ascending=False)
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
                st.map(df)

with tab2:
    st.subheader("חיפוש מיקומים עבור מין ספציפי")
    species_name = st.text_input("הכנס שם ציפור (באנגלית או שם מדעי):")
    find_button = st.button("חפש תצפיות")

    if find_button and species_name:
        with st.spinner(f"מחפש את {species_name}..."):
            hotspots = explorer.get_hotspots(tuple(region_codes), api_key)
            species_results = []
            
            for hs in hotspots[:50]:
                obs = explorer.get_observations(hs['locId'], api_key, days)
                # סינון לפי שם המין (תומך בשם נפוץ או מדעי)
                matches = [o for o in obs if species_name.lower() in o.get('comName', '').lower() 
                           or species_name.lower() in o.get('sciName', '').lower()]
                
                if matches:
                    best_obs = max(matches, key=lambda x: x.get('howMany', 0))
                    species_results.append({
                        "מיקום": hs['locName'],
                        "כמות מקסימלית": best_obs.get('howMany', 0),
                        "תאריך": best_obs.get('obsDt', ''),
                        "צפר": best_obs.get('userDisplayName', 'לא ידוע'),
                        "lat": hs['lat'],
                        "lon": hs['lng']
                    })
            
            if species_results:
                sdf = pd.DataFrame(species_results).sort_values(by="כמות מקסימלית", ascending=False)
                st.success(f"נמצאו {len(sdf)} מיקומים עם תצפיות של {species_name}")
                st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True)
                st.map(sdf)
            else:
                st.info("לא נמצאו תצפיות למין זה באזורים שנבחרו.")
