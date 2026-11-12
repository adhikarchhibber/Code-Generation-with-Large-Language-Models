import pandas as pd
import geopandas as gpd
from shapely import wkt
from sqlalchemy import create_engine, text

# Configuration
db_user = "postgres"
db_pass = "postgres"
db_host = "localhost"
db_name = "USCountyDB"
csv_file = "TIGER2018_COUNTY_with_state.csv"
table_name = "counties"
geom_col = "geometry"



engine = create_engine(f'postgresql+psycopg2://{db_user}:{db_pass}@{db_host}/{db_name}')


# 3. Load CSV
df = pd.read_csv(csv_file)
df.columns = ['GEOMETRY', 'STATEFP',
'COUNTYFP' ,
'COUNTYNS' ,
'GEOID',
'NAME',
'NAMELSAD' ,
'LSAD',
'CLASSFP',
'MTFCC',
'CSAFP',
'CBSAFP',
'METDIVFP' ,
'FUNCSTAT' ,
'ALAND' ,
'AWATER' ,
'INTPTLAT' ,
'INTPTLON' ,
'STATE' ,
'STATEAABRV']
df.columns
#make all columns lowercase
df.columns = df.columns.str.lower()

# Convert WKT to geometry if needed
if df[geom_col].dtype == "object" and isinstance(df[geom_col].iloc[0], str):
    df[geom_col] = df[geom_col].apply(wkt.loads)

# Create GeoDataFrame
gdf = gpd.GeoDataFrame(df, geometry=geom_col)
gdf = gdf.set_crs("EPSG:4326", allow_override=True)

# 4. Import into PostGIS
gdf.to_postgis(table_name, engine, if_exists="replace", index=False)
print(f"CSV '{csv_file}' imported into table '{table_name}'.")

# 5. Create spatial index
with engine.begin() as conn:
    conn.execute(text(f"CREATE INDEX idx_{table_name}_geom ON {table_name} USING GIST ({geom_col});"))
    print(f"GIST spatial index on '{geom_col}' created.")
