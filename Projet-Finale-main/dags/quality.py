import os
from pathlib import Path
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

# Plages acceptables par variable (Phase 6)
RANGES = {
    'temperature_2m':       (-10, 50),
    'relative_humidity_2m': (0, 100),
    'precipitation':        (0, 500),
    'wind_speed_10m':       (0, 200),
    'surface_pressure':     (900, 1100),
    'uv_index_max':         (0, 20),
}


def get_conn():
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    return conn


def run_checks(dry_run=False):
    """
    Phase 6 — Contrôle qualité sur weather_clean.
    Vérifie les valeurs NULL et hors plage, logue dans data_quality.
    dry_run=True : affiche les anomalies sans les insérer.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Seulement les nouvelles entrées pas encore contrôlées
    cur.execute('''
        SELECT wc.id, wc.location_id, wc.variable_id, v.code, wc.valeur
        FROM weather_clean wc
        JOIN variables v ON v.id = wc.variable_id
        WHERE wc.id NOT IN (
            SELECT DISTINCT source_raw_id FROM data_quality
            WHERE source_raw_id IS NOT NULL
        )
    ''')
    rows = cur.fetchall()
    print(f'[quality] {len(rows)} entrées à vérifier')

    anomaly_count = 0
    for rid, location_id, variable_id, code, valeur in rows:
        anomaly_type = None
        valeur_detectee = valeur

        if valeur is None:
            anomaly_type = 'NULL_VALUE'
            valeur_detectee = None
        elif code in RANGES:
            lo, hi = RANGES[code]
            if valeur < lo or valeur > hi:
                anomaly_type = 'OUT_OF_RANGE'

        if anomaly_type:
            anomaly_count += 1
            print(f'  [quality] {anomaly_type} | {code}={valeur} | location={location_id}')
            if not dry_run:
                cur.execute(
                    '''INSERT INTO data_quality(location_id, variable_id, anomaly_type, valeur_detectee)
                       VALUES (%s,%s,%s,%s)''',
                    (location_id, variable_id, anomaly_type, valeur_detectee)
                )

    cur.close()
    conn.close()
    print(f'[quality] {anomaly_count} anomalies détectées{"  (dry-run, non enregistrées)" if dry_run else " enregistrées"}')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='Affiche sans enregistrer')
    args = p.parse_args()
    run_checks(dry_run=args.dry_run)
