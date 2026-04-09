
# app.py — Streamlit Version
import streamlit as st
import anthropic
import json
import re
import requests
import pandas as pd
import folium
import branca.colormap as cm
from folium.plugins import HeatMap, MarkerCluster
import io

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="AI GIS Map Generator",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ AI GIS Map Generator")
st.markdown("Generate interactive maps from plain English descriptions and data spreadsheets.")

# ============================================================
# API KEY — Stored safely in Streamlit secrets
# ============================================================
CLAUDE_API_KEY = st.secrets["CLAUDE_API_KEY"]
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# ============================================================
# GEOJSON SOURCES
# ============================================================
GEOJSON_SOURCES = {
    "us_counties":
        "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json",
    "us_states":
        "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json",
    "canada_provinces":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/canada.geojson",
    "world_countries":
        "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
    "france_departments":
        "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson",
    "germany_states":
        "https://raw.githubusercontent.com/isellsoap/deutschlandGeoJSON/main/2_bundeslaender/4_niedrig.geo.json",
    "brazil_states":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson",
    "mexico_states":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/mexico.geojson",
    "australia_states":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/australia.geojson",
    "japan_prefectures":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/japan.geojson",
    "china_provinces":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/china.geojson",
    "south_africa_provinces":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/south-africa.geojson",
    "nigeria_states":
        "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/nigeria.geojson",
}

GEOJSON_KEY_MAP = {
    "us_counties":            {"key_on": "feature.id",                    "name_prop": None},
    "us_states":              {"key_on": "feature.properties.name",       "name_prop": "name"},
    "canada_provinces":       {"key_on": "feature.properties.name",       "name_prop": "name"},
    "world_countries":        {"key_on": "feature.properties.name",       "name_prop": "name"},
    "france_departments":     {"key_on": "feature.properties.nom",        "name_prop": "nom"},
    "germany_states":         {"key_on": "feature.properties.NAME_1",     "name_prop": "NAME_1"},
    "brazil_states":          {"key_on": "feature.properties.name",       "name_prop": "name"},
    "mexico_states":          {"key_on": "feature.properties.name",       "name_prop": "name"},
    "australia_states":       {"key_on": "feature.properties.STATE_NAME", "name_prop": "STATE_NAME"},
    "japan_prefectures":      {"key_on": "feature.properties.name",       "name_prop": "name"},
    "china_provinces":        {"key_on": "feature.properties.name",       "name_prop": "name"},
    "south_africa_provinces": {"key_on": "feature.properties.name",       "name_prop": "name"},
    "nigeria_states":         {"key_on": "feature.properties.name",       "name_prop": "name"},
}

REGION_CENTERS = {
    "us_counties":        {"lat": 39.5,  "lon": -98.35, "zoom": 4},
    "us_states":          {"lat": 39.5,  "lon": -98.35, "zoom": 4},
    "canada_provinces":   {"lat": 56.0,  "lon": -96.0,  "zoom": 4},
    "world_countries":    {"lat": 20.0,  "lon": 0.0,    "zoom": 2},
    "france_departments": {"lat": 46.5,  "lon": 2.5,    "zoom": 6},
    "germany_states":     {"lat": 51.2,  "lon": 10.4,   "zoom": 6},
    "brazil_states":      {"lat": -14.0, "lon": -51.0,  "zoom": 4},
    "mexico_states":      {"lat": 24.0,  "lon": -102.0, "zoom": 5},
    "australia_states":   {"lat": -25.0, "lon": 133.0,  "zoom": 4},
    "japan_prefectures":  {"lat": 36.0,  "lon": 138.0,  "zoom": 5},
    "china_provinces":    {"lat": 35.0,  "lon": 105.0,  "zoom": 4},
    "south_africa_provinces": {"lat": -29.0, "lon": 25.0, "zoom": 6},
    "nigeria_states":     {"lat": 9.0,   "lon": 8.0,    "zoom": 6},
}

US_STATE_FIPS = {
    "ohio":"39","texas":"48","california":"06","florida":"12",
    "new york":"36","illinois":"17","pennsylvania":"42",
    "georgia":"13","michigan":"26","north carolina":"37",
}

# ============================================================
# CACHED GEOJSON FETCHER
# ============================================================
@st.cache_data
def fetch_geojson(region_type):
    url = GEOJSON_SOURCES.get(region_type)
    if not url:
        raise ValueError(f"No source for {region_type}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

# ============================================================
# AI PARSER
# ============================================================
def parse_map_request(user_input, columns=[]):
    region_list  = "
".join([f"- {k}" for k in GEOJSON_SOURCES.keys()])
    columns_info = f"Available CSV columns: {columns}" if columns else "No CSV uploaded."

    prompt = (
        "You are a GIS mapping assistant. Convert this request into JSON only.

"
        f"User request: {user_input}
"
        f"{columns_info}

"
        "Available region types:
"
        f"{region_list}

"
        "Return ONLY this JSON:
"
        "{
"
        '    "map_type": "region" or "marker" or "heatmap" or "cluster",
'
        '    "region_type": "one region type from above or null",
'
        '    "state_filter": "US state name lowercase or null",
'
        '    "region_name_column": "CSV column with region names",
'
        '    "data_column": "CSV column with numeric values",
'
        '    "title": "map title",
'
        '    "color_scheme": "YlOrRd or Blues or Greens or PuRd or RdYlGn or OrRd"
'
        "}"
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    raw   = message.content[0].text.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {
        "map_type": "marker",
        "region_type": None,
        "state_filter": None,
        "region_name_column": None,
        "data_column": None,
        "title": "My Map",
        "color_scheme": "YlOrRd"
    }
    
# ============================================================
# AUTO DETECT KEY
# ============================================================
def auto_detect_key(geojson_data, sample_names):
    if not geojson_data["features"]:
        return None, None
    all_props  = geojson_data["features"][0].get("properties", {})
    all_keys   = list(all_props.keys())
    normalized = [n.lower().strip() for n in sample_names]
    best_key, best_score = None, 0
    for key in all_keys:
        vals    = [str(f["properties"].get(key,"")).lower().strip()
                   for f in geojson_data["features"]]
        matches = sum(1 for n in normalized if n in vals)
        score   = matches / len(normalized) if normalized else 0
        if score > best_score:
            best_score = score
            best_key   = key
    if best_key and best_score > 0:
        return best_key, f"feature.properties.{best_key}"
    return None, None

# ============================================================
# MAP GENERATOR
# ============================================================
def generate_map(params, df=None):
    region_type  = params.get("region_type")
    data_col     = params.get("data_column")
    name_col     = params.get("region_name_column")
    color_scheme = params.get("color_scheme", "YlOrRd")
    state_filter = params.get("state_filter","").lower() if params.get("state_filter") else None
    map_type     = params.get("map_type","marker")

    center = REGION_CENTERS.get(region_type, {"lat":20,"lon":0,"zoom":2})

    m = folium.Map(
        location=[center["lat"], center["lon"]],
        zoom_start=center["zoom"],
        tiles="CartoDB positron"
    )

    m.get_root().html.add_child(folium.Element(f"""
        <div style="position:fixed;top:10px;left:50%;
                    transform:translateX(-50%);
                    background:white;padding:10px 20px;
                    border-radius:8px;
                    box-shadow:2px 2px 6px rgba(0,0,0,0.3);
                    z-index:1000;font-family:Arial;
                    font-size:16px;font-weight:bold;">
            {params.get("title","My Map")}
        </div>
    """))

    if map_type == "region" and df is not None and data_col and name_col:
        geojson_data = fetch_geojson(region_type)
        key_info     = GEOJSON_KEY_MAP.get(region_type, {"key_on":"feature.properties.name","name_prop":"name"})
        key_on       = key_info["key_on"]
        name_prop    = key_info["name_prop"]

        if region_type == "us_counties":
            fips_prefix = US_STATE_FIPS.get(state_filter,"") if state_filter else ""
            fips_lookup = {}
            for feature in geojson_data["features"]:
                fid  = feature.get("id","")
                name = feature.get("properties",{}).get("NAME","").lower().strip()
                if state_filter and not fid.startswith(fips_prefix):
                    continue
                fips_lookup[name] = fid

            df = df.copy()
            df[name_col] = df[name_col].str.lower().str.strip().str.replace(" county","",regex=False)
            df["fips"]   = df[name_col].map(fips_lookup)
            df[data_col] = pd.to_numeric(df[data_col], errors="coerce")
            df           = df.dropna(subset=["fips", data_col])

            if state_filter:
                geojson_data = {**geojson_data, "features": [
                    f for f in geojson_data["features"]
                    if f.get("id","").startswith(fips_prefix)
                ]}

            folium.Choropleth(
                geo_data=geojson_data, data=df,
                columns=["fips", data_col], key_on="feature.id",
                fill_color=color_scheme, fill_opacity=0.75,
                line_opacity=0.6, line_color="white", line_weight=1,
                legend_name=data_col.replace("_"," ").title(),
                highlight=True, nan_fill_color="#d9d9d9"
            ).add_to(m)

        else:
            df = df.copy()
            df[name_col] = df[name_col].str.strip()
            df[data_col] = pd.to_numeric(df[data_col], errors="coerce")
            df           = df.dropna(subset=[data_col])

            detected_prop, detected_key = auto_detect_key(geojson_data, df[name_col].tolist())
            if detected_key:
                key_on    = detected_key
                name_prop = detected_prop

            folium.Choropleth(
                geo_data=geojson_data, data=df,
                columns=[name_col, data_col], key_on=key_on,
                fill_color=color_scheme, fill_opacity=0.75,
                line_opacity=0.6, line_color="white", line_weight=1,
                legend_name=data_col.replace("_"," ").title(),
                highlight=True, nan_fill_color="#d9d9d9"
            ).add_to(m)

        tooltip_fields  = [name_prop] if name_prop else []
        tooltip_aliases = ["Region:"] if name_prop else []
        folium.GeoJson(
            geojson_data,
            style_function=lambda x: {"fillColor":"transparent","color":"transparent","weight":0},
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_fields, aliases=tooltip_aliases,
                style="font-family:Arial;font-size:12px;"
            ) if tooltip_fields else None
        ).add_to(m)

    elif df is not None:
        lat_col = next((c for c in df.columns if c.lower() in ["lat","latitude"]), None)
        lon_col = next((c for c in df.columns if c.lower() in ["lon","lng","longitude"]), None)

        if lat_col and lon_col:
            df = df.copy()
            df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
            df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
            df           = df.dropna(subset=[lat_col, lon_col])

            if map_type == "heatmap":
                HeatMap(df[[lat_col, lon_col]].values.tolist(), radius=15).add_to(m)
            elif map_type == "cluster":
                mc = MarkerCluster().add_to(m)
                for _, row in df.iterrows():
                    folium.Marker([row[lat_col], row[lon_col]]).add_to(mc)
            else:
                for _, row in df.iterrows():
                    folium.CircleMarker(
                        location=[row[lat_col], row[lon_col]],
                        radius=8, color="#3498DB",
                        fill=True, fill_opacity=0.7
                    ).add_to(m)

    folium.LayerControl().add_to(m)
    return m._repr_html_()

# ============================================================
# STREAMLIT UI
# ============================================================
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("⚙️ Map Settings")

    prompt = st.text_area(
        "Describe your map",
        placeholder="e.g. Show Ohio county poverty levels as shaded regions",
        height=100
    )

    uploaded_file = st.file_uploader("Upload CSV (optional)", type=["csv"])

    df = None
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.success(f"✅ {len(df)} rows loaded")
        st.dataframe(df.head(3))

    generate = st.button("🗺️ Generate Map", type="primary", use_container_width=True)

    st.markdown("---")
    st.markdown("**Example prompts:**")
    st.markdown("- Show Ohio county poverty levels")
    st.markdown("- World countries by happiness score")
    st.markdown("- US states by unemployment rate")
    st.markdown("- Heatmap of earthquake locations")

with col2:
    st.subheader("🗺️ Your Map")

    if generate and prompt:
        with st.spinner("Asking Claude..."):
            try:
                columns = df.columns.tolist() if df is not None else []
                params  = parse_map_request(prompt, columns)
                st.caption(f"Map type: `{params['map_type']}` | Region: `{params.get('region_type','point data')}`")
                map_html = generate_map(params, df)
                st.components.v1.html(map_html, height=600, scrolling=False)
                st.download_button(
                    label="⬇️ Download Map",
                    data=map_html,
                    file_name="map.html",
                    mime="text/html"
                )
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    else:
        st.info("👈 Enter a prompt and click Generate Map")
