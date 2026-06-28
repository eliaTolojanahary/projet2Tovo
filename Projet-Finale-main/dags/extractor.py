#!/usr/bin/env python3
# extractor.py - Version améliorée
import os
import json
import requests
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WeatherExtractor:
    def __init__(self):
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        self.base_url = os.getenv('OPENWEATHER_BASE_URL', 'https://api.openweathermap.org/data/2.5')
        # Open-Meteo : utilisé par run_current() / run_hourly_daily()
        # (l'API officielle du projet, ne nécessite pas de clé API)
        self.open_meteo_url = os.getenv('OPEN_METEO_BASE_URL', 'https://api.open-meteo.com/v1/forecast')
        self.db_conn = None
        
    def connect_db(self):
        """Établit la connexion PostgreSQL"""
        self.db_conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            dbname=os.getenv('DB_NAME', 'weather_madagascar'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', '')
        )
        return self.db_conn
    
    def get_locations(self):
        """Récupère les stations météo depuis la BDD"""
        with self.db_conn.cursor() as cur:
            cur.execute("""
                SELECT id, nom, latitude, longitude, api_source, api_id 
                FROM weather_locations
            """)
            return cur.fetchall()
    
    def fetch_current_weather(self, lat, lon):
        """Récupère la météo actuelle depuis l'API"""
        url = f"{self.base_url}/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'fr'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur API: {e}")
            return None

    def fetch_open_meteo(self, lat, lon, mode):
        """
        Récupère les données météo depuis Open-Meteo.
        mode: 'current' | 'hourly' | 'daily'
        """
        params = {'latitude': lat, 'longitude': lon, 'timezone': 'auto'}

        if mode == 'current':
            params['current'] = 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,surface_pressure'
        elif mode == 'hourly':
            params['hourly'] = 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,surface_pressure'
        elif mode == 'daily':
            params['daily'] = 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,uv_index_max'
        else:
            raise ValueError(f"mode inconnu: {mode}")

        try:
            response = requests.get(self.open_meteo_url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur API Open-Meteo ({mode}): {e}")
            return None

    def save_raw(self, location_id, api_type, raw_json):
        """Sauvegarde la réponse brute JSON dans weather_raw (lue ensuite par transformer.py)"""
        if not raw_json:
            return False
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO weather_raw (location_id, api_type, raw_json, fetched_at)
                    VALUES (%s, %s, %s, %s)
                """, (location_id, api_type, json.dumps(raw_json), datetime.now()))
                self.db_conn.commit()
                logger.info(f"weather_raw sauvegardé pour location {location_id} ({api_type})")
                return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde weather_raw: {e}")
            self.db_conn.rollback()
            return False
    
    def save_weather_data(self, location_id, data):
        """Sauvegarde les données météo en BDD"""
        if not data:
            return None
        
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO weather_measurements 
                    (location_id, measurement_time, temperature_c, humidity_percent, 
                     pressure_hpa, wind_speed_ms, wind_direction_deg, 
                     cloud_cover_percent, visibility_m, weather_condition, data_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (location_id, measurement_time) DO UPDATE
                    SET temperature_c = EXCLUDED.temperature_c,
                        humidity_percent = EXCLUDED.humidity_percent
                """, (
                    location_id,
                    datetime.fromtimestamp(data.get('dt', 0)),
                    data.get('main', {}).get('temp'),
                    data.get('main', {}).get('humidity'),
                    data.get('main', {}).get('pressure'),
                    data.get('wind', {}).get('speed'),
                    data.get('wind', {}).get('deg'),
                    data.get('clouds', {}).get('all'),
                    data.get('visibility'),
                    data.get('weather', [{}])[0].get('description'),
                    'openweathermap'
                ))
                self.db_conn.commit()
                logger.info(f"Données sauvegardées pour location {location_id}")
                return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde: {e}")
            self.db_conn.rollback()
            return False
    
    def run_extraction(self):
        """Exécute l'extraction complète"""
        logger.info("Début de l'extraction des données météo")
        
        try:
            self.connect_db()
            locations = self.get_locations()
            logger.info(f"{len(locations)} stations à traiter")
            
            success_count = 0
            for location in locations:
                loc_id, name, lat, lon, api_source, api_id = location
                logger.info(f"Traitement de {name} ({lat}, {lon})")
                
                weather_data = self.fetch_current_weather(lat, lon)
                if weather_data:
                    if self.save_weather_data(loc_id, weather_data):
                        success_count += 1
            
            logger.info(f"Extraction terminée: {success_count}/{len(locations)} succès")
            
            # Log dans la table ETL
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO etl_logs (process_name, status, records_processed, completed_at)
                    VALUES (%s, %s, %s, %s)
                """, ('extractor', 'success' if success_count > 0 else 'partial', 
                      success_count, datetime.now()))
                self.db_conn.commit()
            
        except Exception as e:
            logger.error(f"Erreur critique: {e}")
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO etl_logs (process_name, status, error_message, completed_at)
                    VALUES (%s, %s, %s, %s)
                """, ('extractor', 'failed', str(e), datetime.now()))
                self.db_conn.commit()
        finally:
            if self.db_conn:
                self.db_conn.close()

    def run_open_meteo_extraction(self, mode):
        """
        Exécute l'extraction Open-Meteo pour toutes les stations, pour un mode donné.
        mode: 'current' | 'hourly' | 'daily'
        Écrit dans weather_raw (lu ensuite par transformer.py).
        """
        logger.info(f"Début de l'extraction Open-Meteo ({mode})")

        try:
            self.connect_db()
            locations = self.get_locations()
            logger.info(f"{len(locations)} stations à traiter")

            success_count = 0
            for location in locations:
                loc_id, name, lat, lon, api_source, api_id = location
                logger.info(f"[{mode}] Traitement de {name} ({lat}, {lon})")

                raw_data = self.fetch_open_meteo(lat, lon, mode)
                if raw_data:
                    if self.save_raw(loc_id, mode, raw_data):
                        success_count += 1

            logger.info(f"Extraction {mode} terminée: {success_count}/{len(locations)} succès")

            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO etl_logs (process_name, status, records_processed, completed_at)
                    VALUES (%s, %s, %s, %s)
                """, (f'extractor_{mode}', 'success' if success_count > 0 else 'partial',
                      success_count, datetime.now()))
                self.db_conn.commit()

        except Exception as e:
            logger.error(f"Erreur critique ({mode}): {e}")
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO etl_logs (process_name, status, error_message, completed_at)
                    VALUES (%s, %s, %s, %s)
                """, (f'extractor_{mode}', 'failed', str(e), datetime.now()))
                self.db_conn.commit()
        finally:
            if self.db_conn:
                self.db_conn.close()

if __name__ == "__main__":
    extractor = WeatherExtractor()
    extractor.run_extraction()


# ──────────────────────────────────────────────
# Fonctions wrapper au niveau module
# Appelées directement par weather_etl_dag.py (PythonOperator)
# ──────────────────────────────────────────────

def run_current():
    """
    Utilisée par le DAG weather_current_dag (@hourly).
    Récupère la météo 'current' via Open-Meteo et la stocke dans weather_raw.
    """
    extractor = WeatherExtractor()
    extractor.run_open_meteo_extraction('current')


def run_hourly_daily():
    """
    Utilisée par le DAG weather_daily_dag (@daily).
    Récupère les données 'hourly' ET 'daily' via Open-Meteo et les stocke dans weather_raw.
    """
    extractor = WeatherExtractor()
    extractor.run_open_meteo_extraction('hourly')

    # Nouvelle connexion car run_open_meteo_extraction ferme self.db_conn en finally
    extractor2 = WeatherExtractor()
    extractor2.run_open_meteo_extraction('daily')