import psycopg2
import pandas as pd
import json
import time
import os
from dotenv import load_dotenv
from typing import Dict
import geopandas as gpd
from sqlalchemy import create_engine, text
# Load environment variables
load_dotenv()

class DBConnector:
    def __init__(self, dbname=None, user=None, password=None, host=None, port=None):
        """Initialize database connector with connection parameters"""
        self.connection_params: Dict[str, str] = {
            "dbname": dbname or os.getenv("DB_NAME", "USCountyDB"),
            "user": user or os.getenv("DB_USER", "postgres"),
            "password": password or os.getenv("DB_PASSWORD", ""),
            "host": host or os.getenv("DB_HOST", "localhost"),
            "port": port or os.getenv("DB_PORT", "5432")
        }

    def test_connection(self):
        """Test database connection"""
        try:
            conn = psycopg2.connect(**self.connection_params)
            cursor = conn.cursor()
            # Ensure default schema is public so unqualified table names work
            cursor.execute("SET search_path TO public")
            cursor.execute("SELECT COUNT(*) FROM counties")
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return {"success": True, "count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_query(self, sql_query):
        """Execute SQL query and return results"""
        start_time = time.time()

        try:
            conn = psycopg2.connect(**self.connection_params)
            cursor = conn.cursor()

            # Ensure default schema is public so queries like `FROM counties` resolve
            cursor.execute("SET search_path TO public")

            cursor.execute(sql_query)

            # Fetch results
            if cursor.description:  # If query returns data
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                df = pd.DataFrame(results, columns=columns)
            else:
                df = pd.DataFrame()


            df = df.loc[:, ~df.columns.duplicated()]
            df = df.drop_duplicates()
            conn.commit()
            cursor.close()
            conn.close()

            end_time = time.time()

            return {
                "success": True,
                "data": df,
                "row_count": len(df),
                "query_time": round(end_time - start_time, 3)
            }

        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "error": str(e),
                "data": pd.DataFrame(),
                "query_time": round(end_time - start_time, 3)
            }


    def gdf_plot_maker(self, sql):
        engine = create_engine("postgresql://{user}:{password}@{host}:{port}/{dbname}".format(**self.connection_params))
        print("in plot maker")
        return gpd.read_postgis(sql, engine, geom_col="geometry")

    def get_geojson(self, sql_query):
        """Execute query and return GeoJSON for mapping"""
        try:
            start_time = time.time()
            gpd_res = self.gdf_plot_maker(text(sql_query))
            end_time = time.time() - start_time
            return {
                "success": True,
                "geojson": "NONE",
                "query_time": end_time,
                "gpd_result" : gpd_res
            }

            if result["success"] and not result["data"].empty:
                geojson_data = result["data"]["geojson"].iloc[0]
                return {
                    "success": True,
                    "geojson": geojson_data,
                    "query_time": result["query_time"],
                    "gpd_result" : gpd_res
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "No geometry data returned")
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
