import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

# הגדרות דף
st.set_page_config(page_title="eBird Israel Radius", layout="wide")

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        # רשימת ערים עם כפר סבא כברירת מחדל
        self.city_coordinates = {
            "כפר סבא (Kfar Saba)": {"lat": 32.175, "lon": 34.906},
            "חיפה (Haifa)": {"lat": 32.794, "lon": 34.989},
            "תל אביב (Tel Aviv)": {"lat": 32.085, "lon": 34.781},
            "ירושלים (Jerusalem)": {"lat": 31.768, "lon": 35.213},
            "באר שבע (Beersheba)": {"lat": 31.253, "lon": 34.791},
            "אילת (Eilat)": {"lat": 29.558, "lon": 34.948},
            "נחשולים / מעגן מיכאל": {"lat": 32.561, "lon": 34.923}
        }

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

    @st.cache_data(ttl=3600)
    def get_nearby_hotspots(_self, lat, lon, dist, api_key):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/ref/hotspot/geo"
        params = {"lat": lat, "lng": lon, "dist": dist, "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

    @st.cache_data(ttl=600)
    def get_observations(_self, loc_id, api_key, days):
        headers = _self.get_headers(api_key)
        url = f"{_self.base_url}/data/obs/{loc_id}/recent"
        params = {"back": days, "includeProvisional": "true", "fmt": "json"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else []

def display_custom_map(df, center_lat, center_lon):
    if df.empty: return
    view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=11)
    
    scatter_layer = pdk.Layer(
        "ScatterplotLayer", df, get_position=["lon", "lat"],
        get_color=[200, 30, 0, 160], get_radius=200, pickable=True
    )
    
    text_layer = pdk.Layer(
        "TextLayer", df, get_position=["lon", "lat"],
        get_text="מיקום", get_size=15, get_color=[255, 255, 255],
        get_alignment_baseline="'bottom'", get_pixel_offset=[0, -10]
    )

    st.pydeck_chart(pdk.Deck(layers=[scatter_layer, text_layer], initial_view_state=view_state, tooltip={"text": "{מיקום}"}))

explorer = eBirdRadiusExplorer()
st.title("📍 eBird Israel Explorer")

with st.sidebar:
    st.header("הגדרות חיפוש")
    api_key = st.text_input("הכנס API Key:", type="password")
    
    # בחירת עיר עם כפר סבא כברירת מחדל (index=0)
    city_list = list(explorer.city_coordinates.keys())
    city = st.selectbox("בחר עיר מרכזית:", city_list, index=0)
    
    lat = explorer.city_coordinates[city]["lat"]
    lon = explorer.city_coordinates[city]["lon"]
    
    st.divider()
    radius = st.slider("רדיוס חיפוש (ק\"מ):", 1, 50, 15)
    days = st.slider("ימים אחורה:", 1, 30, 7)
    
    if st.button("🗑️ רענן זיכרון (Clear Cache)"):
        st.cache_data.clear()
        st.rerun()

if not api_key:
    st.info("אנא הכנס API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין"])

with tab1:
    if st.button(f"🔍 חפש תצפיות סביב {city.split(' ')[0]}"):
        with st.spinner(f"סורק מוקדים ברדיוס {radius} ק\"מ מכפר סבא..."):
            hotspots = explorer.get_nearby_hotspots(lat, lon, radius, api_key)
            results = []
            
            progress_bar = st.progress(0)
            total_hs = min(len(hotspots), 80)
            
            for i, hs in enumerate(hotspots[:total_hs]):
                obs = explorer.get_observations(hs['locId'], api_key, days)
                if obs:
                    results.append({
                        "מיקום": hs.get('locName', 'ללא שם'),
                        "ק\"מ": round(hs.get('dist', 0), 1),
                        "מינים": len(set(o.get('sciName', '') for o in obs)),
                        "פרטים": sum(o.get('howMany', 0) for o in obs),
                        "תאריך": obs[0].get('obsDt', '').split(' ')[0],
                        "lat": hs['lat'], "lon": hs['lng']
                    })
                progress_bar.progress((i + 1) / total_hs)
            
            if results:
                df = pd.DataFrame(results).sort_values(by="מינים", ascending=False)
                st.dataframe(
                    df.drop(columns=['lat', 'lon']),
                    use_container_width=True,
                    column_config={
                        "מיקום": st.column_config.TextColumn("מיקום", pinned=True),
                        "ק\"מ": st.column_config.NumberColumn("ק\"מ", format="%.1f")
                    }
                )
                display_custom_map(df, lat, lon)
            else:
                st.info("לא נמצאו תצפיות מעניינות ברדיוס זה.")

with tab2:
    st.subheader(f"חיפוש מין ספציפי סביב {city}")
    species_name = st.text_input("שם ציפור (באנגלית/מדעי):", placeholder="למשל: Common Crane")
    if st.button("🎯 חפש"):
        with st.spinner(f"מחפש {species_name}..."):
            hotspots = explorer.get_nearby_hotspots(lat, lon, radius, api_key)
            s_results = []
            for hs in hotspots[:80]:
                obs = explorer.get_observations(hs['locId'], api_key, days)
                matches = [o for o in obs if species_name.lower() in o.get('comName', '').lower() or species_name.lower() in o.get('sciName', '').lower()]
                if matches:
                    best = max(matches, key=lambda x: x.get('howMany', 0))
                    s_results.append({
                        "מיקום": hs['locName'],
                        "ק\"מ": round(hs.get('dist', 0), 1),
                        "כמות": best.get('howMany', 0),
                        "תאריך": best.get('obsDt', '').split(' ')[0],
                        "lat": hs['lat'], "lon": hs['lng']
                    })
            if s_results:
                sdf = pd.DataFrame(s_results).sort_values(by="כמות", ascending=False)
                st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True,
                             column_config={"מיקום": st.column_config.TextColumn("מיקום", pinned=True)})
                display_custom_map(sdf, lat, lon)
            else:
                st.info("לא נמצאו תצפיות למין זה ברדיוס שנבחר.")
