import streamlit as st
import folium
from streamlit_folium import st_folium
#from model_switcher import get_converter
from db_connector import *
from embedding_model import *
import pandas as pd
import json
from datetime import datetime
import requests
import os
import geopandas as gpd
def extract_aggregates_with_alias(sql: str):
    """
    Extract aggregates from SQL with expressions and aliases.
    Returns list of dicts: [{'func': 'SUM', 'alias': 'area_km2', 'expr': 'SUM(aland)/1000000.0'}]
    """
    sql_clean = sql.replace("\n", " ").strip()
    # Pattern explanation:
    # 1. Aggregate function (sum|count|avg|min|max)
    # 2. Column inside parentheses
    # 3. Optional expression after parentheses
    # 4. Mandatory AS alias
    pattern = r"(sum|count|avg|min|max)\s*\((.*?)\)\s*(.*?)\s+as\s+([a-z0-9_]+)"
    matches = re.findall(pattern, sql_clean, flags=re.I)

    result = []
    for func, inner_col, expr_tail, alias in matches:
        expr_full = f"{func}({inner_col}){expr_tail}".strip()
        result.append({'func': func.upper(), 'alias': alias, 'expr': expr_full})
    return result
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Page config
st.set_page_config(
    page_title="Chat with the Map - US Counties",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .sql-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state

if 'nl_converter' not in st.session_state:
    st.session_state.nl_converter = EmbeddingNLToSQL()

if 'db_connector' not in st.session_state:
    st.session_state.db_connector = DBConnector()

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'db_connected' not in st.session_state:
    st.session_state.db_connected = False

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    # Database Configuration
    with st.expander("🗄️ Database Settings", expanded=False):
        db_name = st.text_input("Database Name", value="USCountyDB")
        db_user = st.text_input("Username", value="postgres")
        db_password = st.text_input("Password", type="password", value = "postgres")
        db_host = st.text_input("Host", value="localhost")
        db_port = st.text_input("Port", value="5432")

        if st.button("🔌 Test Connection"):
            with st.spinner("Testing connection..."):
                st.session_state.db_connector = DBConnector(
                    dbname=db_name,
                    user=db_user,
                    password=db_password,
                    host=db_host,
                    port=db_port
                )
                test_result = st.session_state.db_connector.test_connection()

                if test_result["success"]:
                    st.success(f"✅ Connected! Found {test_result['count']} counties")
                    st.session_state.db_connected = True
                else:
                    st.error(f"❌ Connection failed: {test_result['error']}")
                    st.session_state.db_connected = False

    # Model Configuration
    st.divider()

    # Statistics
    st.subheader("📊 Session Stats")
    st.metric("Queries Executed", len(st.session_state.chat_history))

    if st.button("🗑️ Clear History"):
        st.session_state.chat_history = []
        st.rerun()

# Main Title
st.markdown('<p class="main-header">🗺️ Chat with the Map - US Counties</p>', unsafe_allow_html=True)
st.markdown("Ask questions about US counties in natural language!")

# Connection Status Banner
if st.session_state.db_connected:
    st.success("✅ Database connected")
else:
    st.warning("⚠️ Please configure and test database connection in the sidebar")

st.divider()

# Main Layout
tab1, tab2, tab3 = st.tabs(["🗺️ Map & Chat", "📋 Query Log", "📖 Sample Queries"])

with tab1:
    # Two column layout
    col1, col2 = st.columns([3, 2])

    # Left column: reserve map location early
    with col1:
        st.subheader("Map Visualization")
        map_container = st.container()
        # Initialize state holders if not present
        if 'latest_geojson' not in st.session_state:
            st.session_state.latest_geojson = None
        if 'last_map_geojson' not in st.session_state:
            st.session_state.last_map_geojson = None

    with col2:
        st.subheader("💬 Chat Interface")

        # Chat input
        user_query = st.text_area(
            "Ask a question:",
            placeholder="e.g., Show me Madison County, Idaho",
            height=100,
            key="query_input"
        )

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            submit_btn = st.button("🚀 Submit Query", type="primary")

        with col_btn2:
            clear_btn = st.button("🔄 Clear")

        if clear_btn:
            st.session_state.query_input = ""
            st.rerun()

        if submit_btn and user_query:
            if not st.session_state.db_connected:
                st.error("⚠️ Please connect to the database first!")
            else:
                with st.spinner("🤔 Processing your query..."):
                    # Step 1: Convert NL to SQL
                    st.info("🔄 Converting natural language to SQL...")
                    nl_result = st.session_state.nl_converter.convert(user_query)
                    #print(nl_result)

                    if nl_result["success"]:
                        st.success(f"✅ Query converted in {nl_result['generation_time']}s")

                        # Display generated SQL
                        st.markdown("**Generated SQL:**")
                        st.code(nl_result["sql"], language="sql")

                        # Step 2: Execute SQL
                        st.info("🔄 Executing query...")
                        db_result = st.session_state.db_connector.execute_query(nl_result["sql"])

                        if db_result["success"]:
                            st.success(f"✅ Query executed in {db_result['query_time']}s ({db_result['row_count']} rows)")

                            # Display results
                            if not db_result["data"].empty:
                                # Generate human-readable summary
                                df = db_result["data"]
                                row_count = len(df)

                                # Build summary text
                                summary_parts = []

                                if row_count == 1:
                                    # Single result - show key attributes
                                    summary_parts.append(f"**Found 1 county:**\n")
                                    for col in df.columns:
                                        if col.lower() not in ('geometry', 'geom', 'gemoetry'):
                                            val = df[col].iloc[0]
                                            if pd.notna(val):
                                                # Format large numbers with commas
                                                if isinstance(val, (int, float)) and abs(val) > 999:
                                                    val = f"{val:,.0f}"
                                                summary_parts.append(f"- **{col}**: {val}")
                                else:
                                    # Multiple results - show summary stats
                                    summary_parts.append(f"**Found {row_count} counties:**\n")

                                    # Show name column if available
                                    if 'name' in df.columns:
                                        names = df['name'].tolist()
                                        if len(names) <= 5:
                                            summary_parts.append(f"- {', '.join(str(n) for n in names)}")
                                        else:
                                            summary_parts.append(f"- {', '.join(str(n) for n in names[:5])}, and {len(names)-5} more...")

                                    # Show numeric summaries if available
                                    numeric_cols = df.select_dtypes(include=['number']).columns
                                    for col in numeric_cols:
                                        if col.lower() not in ('statefp', 'countyfp', 'countyns', 'geoid', 'lsad'):
                                            if 'area' in col.lower():
                                                total = df[col].sum()
                                                summary_parts.append(f"- **Total {col}**: {total:,.0f}")
                                            elif len(numeric_cols) <= 3:  # Only show stats for few numeric columns
                                                avg = df[col].mean()
                                                summary_parts.append(f"- **Average {col}**: {avg:,.2f}")

                                # Display summary
                                st.markdown("\n".join(summary_parts))

                                # Show detailed table in expander
                                with st.expander("📊 View detailed data table"):
                                    st.dataframe(df, use_container_width=True)

                                # Try to get GeoJSON if query has a geometry-like column
                                geom_cols = [col for col in ("gemoetry", "geom", "geometry") if col in db_result["data"].columns]
                                if geom_cols:
                                    st.info(f"🗺️ Detected geometry column: {geom_cols[0]}. Generating map...")
                                    geo_result = st.session_state.db_connector.get_geojson(nl_result["sql"])
                                    print(geo_result)
                                    print("HERE!!!")

                                    if geo_result["success"]:
                                        # Persist latest geojson for immediate same-run rendering
                                        st.session_state.latest_geojson = geo_result['geojson']
                                        # Add to history with geometry
                                        st.session_state.chat_history.append({
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            "query": user_query,
                                            "sql": nl_result["sql"],
                                            "llm_prompt": nl_result.get("llm_prompt"),
                                            "result": db_result["data"],
                                            "row_count": db_result['row_count'],
                                            "nl_time": nl_result['generation_time'],
                                            "db_time": db_result['query_time'],
                                            "geojson": geo_result['geojson'],
                                            "gpd_result" : geo_result['gpd_result']
                                        })
                                        st.success("🗺️ Map updated!")
                                    else:
                                        st.error(f"❌ Map generation failed: {geo_result.get('error', 'Unknown error')}")
                                        st.session_state.chat_history.append({
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            "query": user_query,
                                            "sql": nl_result["sql"],
                                            "llm_prompt": nl_result.get("llm_prompt"),
                                            "result": db_result["data"],
                                            "row_count": db_result['row_count'],
                                            "nl_time": nl_result['generation_time'],
                                            "db_time": db_result['query_time']
                                        })
                                else:
                                    # No geometry, just tabular results
                                    st.session_state.chat_history.append({
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "query": user_query,
                                        "sql": nl_result["sql"],
                                        "llm_prompt": nl_result.get("llm_prompt"),
                                        "result": db_result["data"],
                                        "row_count": db_result['row_count'],
                                        "nl_time": nl_result['generation_time'],
                                        "db_time": db_result['query_time'],
                                        "gpd_result" : None
                                    })
                            else:
                                st.info("No results returned")
                        else:
                            st.error(f"❌ Database error: {db_result['error']}")
                    else:
                        st.error(f"❌ Conversion error: {nl_result['error']}")

    # Render the map after processing so it reflects the just-submitted query without needing st.rerun
    # Use fragment to isolate map interactions and prevent full page reruns


    @st.fragment




    def plot_geodf_with_sql():
        """
        Plots a result (GeoDataFrame or DataFrame) in Streamlit.
        - Uses Folium map with hover/tooltips if geometry exists
        - Always displays a table
        - Handles empty results gracefully
        """
        # ---------------------------------------------------------
        # Fetch latest result from chat history
        # ---------------------------------------------------------
        if len(st.session_state.chat_history) == 0:
            st.warning("No data to plot.")
            empty_map = folium.Map(location=[0, 0], zoom_start=2)
            st_folium(empty_map, width=700, height=500, key="empty_map")
            return

        latest = st.session_state.chat_history[-1]
        result = latest.get('gpd_result')

        # ---------------------------------------------------------
        # Handle empty results
        # ---------------------------------------------------------
        if result is None or (hasattr(result, "empty") and result.empty):
            #st.warning("No data to plot.")
            result = latest.get('result')
            st.dataframe(result)
            return

        # ---------------------------------------------------------
        # Always show table
        # ---------------------------------------------------------

        # ---------------------------------------------------------
        # Only plot map if geometry exists
        # ---------------------------------------------------------

        gdf = result.copy()
        if not isinstance(gdf, gpd.GeoDataFrame):
            gdf = gpd.GeoDataFrame(gdf, geometry="geometry")

        # Ensure CRS is EPSG:4326 for folium
        try:
            gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass  # already in correct CRS

        # Remove duplicated columns
        gdf = gdf.loc[:, ~gdf.columns.duplicated()]

        # Columns to show in tooltip
        tooltip_columns = [c for c in gdf.columns if c != gdf.geometry.name]

        # Create Folium map
        centroid = gdf.geometry.centroid.to_crs(4326)
        m = folium.Map(
            location=[centroid.y.mean(), centroid.x.mean()],
            zoom_start=5
        )

        folium.GeoJson(
            gdf,
            style_function=lambda x: {
                'fillColor': 'blue',
                'color': 'black',
                'weight': 1,
                'fillOpacity': 0.5
            },
            tooltip=folium.GeoJsonTooltip(
                fields=tooltip_columns,
                aliases=tooltip_columns,
                localize=True
            )
        ).add_to(m)

        # Render map in Streamlit
        st_folium(m, width=700, height=500, key="main_map")
    with map_container:
        #render_map()
        plot_geodf_with_sql()

with tab2:
    st.subheader("📋 Query Execution Log")

    if st.session_state.chat_history:
        for i, entry in enumerate(reversed(st.session_state.chat_history)):
            with st.expander(f"Query {len(st.session_state.chat_history) - i}: {entry['query'][:50]}...", expanded=(i==0)):
                col_a, col_b, col_c = st.columns(3)

                with col_a:
                    st.metric("Rows Returned", entry['row_count'])
                with col_b:
                    st.metric("NL→SQL Time", f"{entry['nl_time']}s")
                with col_c:
                    st.metric("DB Query Time", f"{entry['db_time']}s")

                st.markdown(f"**Timestamp:** {entry['timestamp']}")
                st.markdown(f"**Natural Language:** {entry['query']}")
                st.markdown("**Generated SQL:**")
                st.code(entry['sql'], language="sql")

                # Show LLM prompt if available
                #if 'llm_prompt' in entry and entry['llm_prompt']:
                    #with st.expander("🔎 View Prompt Sent to LLM", expanded=False):
                        #st.code(entry['llm_prompt'], language="markdown")

                if not entry['result'].empty:
                    st.markdown("**Results:**")
                    st.dataframe(entry['result'], use_container_width=True)
    else:
        st.info("No queries executed yet. Try asking a question in the Chat tab!")

with tab3:
    st.subheader("📖 Sample Queries to Try")

    st.markdown("""
    Here are some example questions you can ask (click to copy):

    ### 🔍 Basic Queries
    - `Show me Madison County, Idaho`
    - `How many counties are called Madison County?`
    - `List all counties in Florida`
    - `List all counties in WA`

    ### 🏷️ Name-Based Queries
    - `Which counties start with 'San ' in California?`
    - `Which counties have multi-word names in Minnesota?`
    - `What are the three most frequent county names in USA?`

    ### 📏 Area & Size Queries
    - `What is the land area of Riverside County, California?`
    - `Rank all counties in Arizona by area`
    - `Which county in NC has the smallest area?`
    - `Which counties nationwide have area < 100 mi²?`

    ### 📐 Perimeter Queries
    - `Return the perimeter length of Orange County, California`
    - `Which counties in South Dakota have perimeter > 800 mi?`

    ### 🗺️ Spatial Queries
    - `Which counties in California touch Nevada?`
    - `How many neighbors does Utah County, UT have?`
    - `Which county in AL has the most neighbors?`

    ### 🔬 Advanced Geometry Queries
    - `Which counties have holes in their geometry?`
    - `Which counties are multipart polygons?`
    - `Which counties' centroid falls outside the polygon?`

    **Note:** Words in quotes are parameter values and can be replaced with other values.
    """)

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <small>CS 279 Capstone Project - Milestone 2 | Chat with the Map | Powered by LLM API & PostGIS</small>
</div>
""", unsafe_allow_html=True)
