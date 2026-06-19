import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import psycopg2

BASE = Path(__file__).parent
load_dotenv(BASE / '.env')

DB = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('DB_NAME', 'weather_madagascar'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}


def get_conn():
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    return conn


def load_variable_map(conn):
    cur = conn.cursor()
    cur.execute('SELECT id, code FROM variables')
    rows = cur.fetchall()
    cur.close()
    return {code: vid for vid, code in rows}


def fetch_unprocessed_raw(conn):
    """Récupère les entrées weather_raw pas encore transformées."""
    cur = conn.cursor()
    cur.execute('''
        SELECT r.id, r.location_id, r.api_type, r.raw_json
        FROM weather_raw r
        WHERE r.id NOT IN (
            SELECT DISTINCT source_raw_id FROM weather_clean
            WHERE source_raw_id IS NOT NULL
        )
        ORDER BY r.fetched_at
    ''')
    rows = cur.fetchall()
    cur.close()
    return rows


def insert_clean(conn, location_id, variable_id, valeur, ts, source_raw_id):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO weather_clean(location_id, variable_id, valeur, timestamp, source_raw_id) VALUES (%s,%s,%s,%s,%s)",
        (location_id, variable_id, valeur, ts, source_raw_id)
    )
    cur.close()


def process_current(conn, raw, var_map):
    """
    Parse la réponse 'current' de Open-Meteo (nouveau format avec 'current').
    Ex: raw['current'] = {'time': '2024-01-01T12:00', 'temperature_2m': 25.3, ...}
    """
    data = raw.get('current') or raw.get('current_weather') or {}
    ts_str = data.get('time')
    if not ts_str:
        return
    ts = datetime.fromisoformat(ts_str)
    location_id = raw['_location_id']
    source_raw_id = raw['_id']

    # Mapping : clé Open-Meteo → code variable en base
    field_map = {
        'temperature_2m': 'temperature_2m',
        'relative_humidity_2m': 'relative_humidity_2m',
        'precipitation': 'precipitation',
        'wind_speed_10m': 'wind_speed_10m',
        'surface_pressure': 'surface_pressure',
        # ancien format current_weather
        'temperature': 'temperature_2m',
        'windspeed': 'wind_speed_10m',
    }
    for field, code in field_map.items():
        if field in data and code in var_map and data[field] is not None:
            insert_clean(conn, location_id, var_map[code], float(data[field]), ts, source_raw_id)


def process_hourly(conn, raw, var_map):
    """
    Parse la réponse 'hourly'.
    Ex: raw['hourly'] = {'time': [...], 'temperature_2m': [...], ...}
    """
    hourly = raw.get('hourly') or {}
    times = hourly.get('time', [])
    location_id = raw['_location_id']
    source_raw_id = raw['_id']

    for code, arr in hourly.items():
        if code == 'time' or code not in var_map:
            continue
        vid = var_map[code]
        for i, val in enumerate(arr[:len(times)]):
            ts = datetime.fromisoformat(times[i])
            v = None if val is None else float(val)
            insert_clean(conn, location_id, vid, v, ts, source_raw_id)


def process_daily(conn, raw, var_map):
    """
    Parse la réponse 'daily'.
    Ex: raw['daily'] = {'time': [...], 'temperature_2m_max': [...], ...}
    """
    daily = raw.get('daily') or {}
    times = daily.get('time', [])
    location_id = raw['_location_id']
    source_raw_id = raw['_id']

    for code, arr in daily.items():
        if code == 'time' or code not in var_map:
            continue
        vid = var_map[code]
        for i, val in enumerate(arr[:len(times)]):
            ts = datetime.fromisoformat(times[i])
            v = None if val is None else float(val)
            insert_clean(conn, location_id, vid, v, ts, source_raw_id)


def run_transform():
    """Phase 4 — Transformation : parse weather_raw → weather_clean."""
    conn = get_conn()
    var_map = load_variable_map(conn)
    raws = fetch_unprocessed_raw(conn)
    print(f'[transform] {len(raws)} entrées à traiter')

    for r in raws:
        rid, location_id, api_type, raw_json = r
        # psycopg2 retourne JSONB déjà parsé en dict, sinon on parse
        raw = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        raw['_id'] = rid
        raw['_location_id'] = location_id

        try:
            if api_type == 'current':
                process_current(conn, raw, var_map)
            elif api_type == 'hourly':
                process_hourly(conn, raw, var_map)
            elif api_type == 'daily':
                process_daily(conn, raw, var_map)
        except Exception as e:
            print(f'[transform] raw_id={rid} ERREUR: {e}')

    conn.close()


def run_aggregate():
    """Phase 4 — Agrégation journalière : weather_clean → weather_daily."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO weather_daily(location_id, date, temp_avg, temp_min, temp_max,
                                  precipitation_sum, humidity_avg, wind_speed_avg, uv_index_max)
        SELECT
            location_id,
            date(timestamp) AS d,
            avg(CASE WHEN v.code = 'temperature_2m'       THEN wc.valeur END),
            min(CASE WHEN v.code = 'temperature_2m'       THEN wc.valeur END),
            max(CASE WHEN v.code = 'temperature_2m'       THEN wc.valeur END),
            sum(CASE WHEN v.code = 'precipitation'        THEN wc.valeur END),
            avg(CASE WHEN v.code = 'relative_humidity_2m' THEN wc.valeur END),
            avg(CASE WHEN v.code = 'wind_speed_10m'       THEN wc.valeur END),
            max(CASE WHEN v.code = 'uv_index_max'         THEN wc.valeur END)
        FROM weather_clean wc
        JOIN variables v ON v.id = wc.variable_id
        GROUP BY location_id, date(timestamp)
        ON CONFLICT (location_id, date) DO UPDATE SET
            temp_avg          = EXCLUDED.temp_avg,
            temp_min          = EXCLUDED.temp_min,
            temp_max          = EXCLUDED.temp_max,
            precipitation_sum = EXCLUDED.precipitation_sum,
            humidity_avg      = EXCLUDED.humidity_avg,
            wind_speed_avg    = EXCLUDED.wind_speed_avg,
            uv_index_max      = EXCLUDED.uv_index_max
    ''')
    cur.close()
    conn.close()
    print('[aggregate] weather_daily mis à jour')


def run_all():
    """Point d'entrée combiné pour tests manuels."""
    run_transform()
    run_aggregate()


if __name__ == '__main__':
    run_all()
