import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import math
from streamlit_js_eval import get_geolocation
from geopy.geocoders import Nominatim

# הגדרות דף
st.set_page_config(page_title="eBird Israel Pro", layout="wide")

# מילון שמות ציפורים (עברית - אנגלית - מדעי)
# הוספתי רשימה לדוגמה, ניתן להרחיב אותה בקלות
BIRDS_DICT = [
    {"heb": "עגור מצוי", "eng": "Common Crane", "sci": "Grus grus"},
    {"heb": "סיקסק", "eng": "Spur-winged Lapwing", "sci": "Vanellus spinosus"},
    {"heb": "שלדג לבן-חזה", "eng": "White-throated Kingfisher", "sci": "Halcyon smyrnensis"},
    {"heb": "בז מצוי", "eng": "Common Kestrel", "sci": "Falco tinnunculus"},
    {"heb": "צופית בוהקת", "eng": "Palestine Sunbird", "sci": "Cinnyris osea"},
    {"heb": "דוכיפת", "eng": "Eurasian Hoopoe", "sci": "Upupa epops"},
    {"heb": "שקנאי מצוי", "eng": "Great White Pelican", "sci": "Pelecanus onocrotalus"},
    {"heb": "חסידה לבנה", "eng": "White Stork", "sci": "Ciconia ciconia"},
    {"heb": "דית שחורה", "eng": "Black Kite", "sci": "Milvus migrans"},
    {"heb": "עקב עיטי", "eng": "Long-legged Buzzard", "sci": "Buteo rufinus"},
    {"heb": "זרזיר מצוי", "eng": "Common Starling", "sci": "Sturnus vulgaris"},
    {"heb": "נחליאלי לבן", "eng": "White Wagtail", "sci": "Motacilla alba"},
    {"heb": "כרוון מצוי", "eng": "Eurasian Stone-curlew", "sci": "Burhinus oedicnemus"},
    {"heb": "לבנית קטנה", "eng": "Little Egret", "sci": "Egretta garzetta"},
    {"heb": "אנפת לילה", "eng": "Black-crowned Night-Heron", "sci": "Nycticorax nycticorax"}
]

# יצירת רשימה לתצוגה בתיבת הבחירה: "עברית (אנגלית)"
BIRD_OPTIONS = [f"{b['heb']} ({b['eng']})" for b in BIRDS_DICT]
# מפה לשליפה מהירה של השם המדעי לפי הבחירה
BIRD_TO_SCI = {f"{b['heb']} ({b['eng']})": b['sci'] for b in BIRDS_DICT}

class eBirdRadiusExplorer:
    def __init__(self):
        self.base_url = "https://api.ebird.org/v2"
        self.geolocator = Nominatim(user_agent="ebird_explorer_il_v4")

    def get_headers(self, api_key):
        return {"X-eBirdApiToken": api_key}

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

explorer = eBirdRadiusExplorer()
st.title("🇮🇱 eBird Israel Pro")

with st.sidebar:
    st.header("הגדרות")
    api_key = st.text_input("API Key:", type="password")
    mode = st.radio("מרכז חיפוש:", ["כפר סבא", "המיקום שלי", "עיר אחרת"])
    
    clat, clon = 32.175, 34.906 # כפ"ס
    if mode == "המיקום שלי":
        loc = get_geolocation()
        if loc: clat, clon = loc['coords']['latitude'], loc['coords']['longitude']
    elif mode == "עיר אחרת":
        city_name = st.text_input("שם עיר באנגלית:", "Haifa")
        res = explorer.geolocator.geocode(f"{city_name}, Israel")
        if res: clat, clon = res.latitude, res.longitude

    radius = st.slider("רדיוס (ק\"מ):", 1, 50, 15)
    days = st.slider("ימים אחורה:", 1, 30, 7)

if not api_key:
    st.info("אנא הזן API Key בסרגל הצד.")
    st.stop()

tab1, tab2 = st.tabs(["📊 תצפיות באזור", "🎯 חיפוש מין"])

with tab1:
    if st.button("🔍 חפש הכל בסביבה"):
        with st.spinner("סורק מוקדים..."):
            hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
            results = []
            for hs in hotspots[:60]:
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
            if results:
                df = pd.DataFrame(results).sort_values(by="מינים", ascending=False)
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True,
                             column_config={"מיקום": st.column_config.TextColumn(pinned=True)})
                # מפה
                st.pydeck_chart(pdk.Deck(
                    layers=[pdk.Layer("ScatterplotLayer", df, get_position=["lon", "lat"], get_color=[200, 30, 0, 160], get_radius=300, pickable=True)],
                    initial_view_state=pdk.ViewState(latitude=clat, longitude=clon, zoom=11),
                    tooltip={"text": "{מיקום}"}
                ))

with tab2:
    st.subheader("חיפוש מין עם השלמה (עברית ואנגלית)")
    
    # תיבת בחירה עם השלמה אוטומטית הכוללת עברית ואנגלית
    selected_bird = st.selectbox(
        "התחל להקליד שם ציפור (בעברית או באנגלית):",
        options=[""] + BIRD_OPTIONS,
        format_func=lambda x: "בחר מין..." if x == "" else x
    )

    if st.button("🎯 חפש את הציפור"):
        if selected_bird:
            sci_name = BIRD_TO_SCI[selected_bird]
            with st.spinner(f"מחפש {selected_bird}..."):
                hotspots = explorer.get_nearby_hotspots(clat, clon, radius, api_key)
                s_results = []
                for hs in hotspots[:60]:
                    obs = explorer.get_observations(hs['locId'], api_key, days)
                    # חישוב התאמה לפי השם המדעי (הכי מדויק)
                    matches = [o for o in obs if sci_name.lower() in o.get('sciName','').lower()]
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
                    st.success(f"נמצאו {len(sdf)} מיקומים!")
                    st.dataframe(sdf.drop(columns=['lat', 'lon']), use_container_width=True,
                                 column_config={"מיקום": st.column_config.TextColumn(pinned=True)})
                else:
                    st.info("לא נמצאו תצפיות של המין הנבחר ברדיוס ובתקופה זו.")
