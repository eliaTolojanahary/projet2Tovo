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


def get_conn():
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    return conn


def safe_fmt(val, decimals=1, default=0.0):
    """Formate une valeur float ou retourne default si None."""
    return round(float(val), decimals) if val is not None else default


def generate_reports():
    """
    Phase 5 — Génère un rapport météo par location/jour depuis weather_daily,
    insère dans weather_report et déclenche les alertes si seuils dépassés.
    """
    conn = get_conn()
    cur = conn.cursor()

    # Entrées weather_daily sans rapport existant
    cur.execute('''
        SELECT wd.id, wd.location_id, wd.date,
               wd.temp_avg, wd.temp_min, wd.temp_max,
               wd.precipitation_sum, wd.humidity_avg, wd.wind_speed_avg
        FROM weather_daily wd
        LEFT JOIN weather_report wr
            ON wr.location_id = wd.location_id AND wr.date = wd.date
        WHERE wr.id IS NULL
    ''')
    rows = cur.fetchall()
    print(f'[reporter] {len(rows)} rapports à générer')

    for row in rows:
        wd_id, location_id, d, temp_avg, temp_min, temp_max, precip, hum, wind = row

        # Nom de la station
        cur.execute('SELECT nom FROM weather_locations WHERE id=%s', (location_id,))
        station_row = cur.fetchone()
        station = station_row[0] if station_row else 'station inconnue'

        # Texte de synthèse (avec valeurs None gérées proprement)
        summary = (
            f"Le {d}, à {station} : "
            f"température moyenne {safe_fmt(temp_avg)}°C "
            f"(min {safe_fmt(temp_min)}°C / max {safe_fmt(temp_max)}°C), "
            f"précipitations {safe_fmt(precip)} mm, "
            f"humidité moyenne {safe_fmt(hum)}%, "
            f"vent moyen {safe_fmt(wind)} km/h."
        )

        try:
            cur.execute(
                '''INSERT INTO weather_report
                   (location_id, date, summary_text, temp_avg, temp_min, temp_max,
                    precipitation_sum, humidity_avg, wind_speed_avg)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (location_id, date) DO NOTHING''',
                (location_id, d, summary, temp_avg, temp_min, temp_max, precip, hum, wind)
            )
        except Exception as e:
            print(f'[reporter] INSERT report ERREUR location={location_id} date={d}: {e}')
            continue

        # --- Logique d'alertes ---
        checks = [
            ('temperature_2m', temp_max, 'CHALEUR'),
            ('precipitation',  precip,   'PLUIE_INTENSE'),
            ('wind_speed_10m', wind,     'VENT_FORT'),
        ]
        for var_code, value, alert_code in checks:
            if value is None:
                continue
            cur.execute('''
                SELECT wt.seuil_max, wt.severite
                FROM weather_thresholds wt
                JOIN variables v ON v.id = wt.variable_id
                WHERE v.code = %s AND wt.seuil_max IS NOT NULL
            ''', (var_code,))
            for seuil_max, severite in cur.fetchall():
                if value > seuil_max:
                    cur.execute('SELECT id FROM alert_types WHERE code=%s', (alert_code,))
                    at = cur.fetchone()
                    alert_type_id = at[0] if at else None
                    message = (
                        f"{alert_code} à {station} le {d} : "
                        f"valeur {value:.1f} dépasse le seuil {seuil_max} (sévérité {severite})"
                    )
                    try:
                        cur.execute(
                            'INSERT INTO alerts(location_id, alert_type_id, severite, message) VALUES (%s,%s,%s,%s)',
                            (location_id, alert_type_id, severite, message)
                        )
                    except Exception as e:
                        print(f'[reporter] INSERT alert ERREUR: {e}')

    cur.close()
    conn.close()
    print('[reporter] terminé')


if __name__ == '__main__':
    generate_reports()