#!/usr/bin/env python3
# seed.py - Version corrigée
import os
import csv
import json
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5433'),
        dbname=os.getenv('DB_NAME', 'weather_madagascar'),
        user=os.getenv('DB_USER', 'weather_user'),
        password=os.getenv('DB_PASSWORD', 'weather_pass')
    )

def load_regions(conn):
    """Charge les régions de Madagascar"""
    regions_path = 'static_data/regions_madagascar.csv'
    if not os.path.exists(regions_path):
        print(f"Fichier non trouvé: {regions_path}")
        return
    
    with open(regions_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        regions = [(row['id'], row['nom'], row['chef_lieu']) 
                   for row in reader]
    
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO regions (id, nom, chef_lieu) 
            VALUES %s 
            ON CONFLICT (id) DO UPDATE 
            SET nom = EXCLUDED.nom, chef_lieu = EXCLUDED.chef_lieu
        """, regions)
    conn.commit()
    print(f"✓ {len(regions)} régions chargées")

def load_climate_types(conn):
    """Charge les types de climat"""
    climate_path = 'static_data/climate_types.txt'
    if not os.path.exists(climate_path):
        print(f"Fichier non trouvé: {climate_path}")
        return
    
    with open(climate_path, 'r', encoding='utf-8') as f:
        climates = [(i+1, line.strip()) 
                    for i, line in enumerate(f.readlines()) if line.strip()]
    
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO climate_types (id, nom, description) 
            VALUES %s 
            ON CONFLICT (id) DO UPDATE 
            SET nom = EXCLUDED.nom
        """, [(c[0], c[1], f"Climat {c[1]}") for c in climates])
    conn.commit()
    print(f"✓ {len(climates)} types de climat chargés")

def load_variables(conn):
    """
    Charge le catalogue des variables météo (variables.json d'Amboara).
    Indispensable : transformer.py et quality.py ont besoin de cette table
    pour mapper un code ('temperature_2m', 'precipitation'...) vers un id.
    Si variables.json n'existe pas encore, on charge une liste par défaut
    couvrant les variables utilisées par le pipeline (current/hourly/daily
    Open-Meteo) pour ne pas bloquer le reste du seed.
    """
    variables_path = 'static_data/variables.json'

    default_variables = [
        ('temperature_2m', '°C', 'Température à 2 mètres'),
        ('relative_humidity_2m', '%', 'Humidité relative à 2 mètres'),
        ('precipitation', 'mm', 'Précipitations'),
        ('wind_speed_10m', 'km/h', 'Vitesse du vent à 10 mètres'),
        ('surface_pressure', 'hPa', 'Pression à la surface'),
        ('uv_index_max', 'index', 'Index UV maximal journalier'),
    ]

    if os.path.exists(variables_path):
        with open(variables_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Format attendu: {"variables": [{"code": "...", "unite": "...", "description": "..."}, ...]}
        rows = [(v['code'], v.get('unite'), v.get('description'))
                for v in data.get('variables', [])]
        if not rows:
            print(f"variables.json vide, utilisation de la liste par défaut")
            rows = default_variables
    else:
        print(f"Fichier non trouvé: {variables_path} — utilisation de la liste par défaut")
        rows = default_variables

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO variables (code, unite, description)
            VALUES %s
            ON CONFLICT (code) DO UPDATE
            SET unite = EXCLUDED.unite, description = EXCLUDED.description
        """, rows)
    conn.commit()
    print(f"✓ {len(rows)} variables chargées")

def load_alert_types(conn):
    """
    Charge les types d'alerte (alerts_types.json d'Amboara).
    Indispensable : reporter.py fait `SELECT id FROM alert_types WHERE code=%s`.
    Si le fichier n'existe pas encore, charge une liste par défaut couvrant
    les codes déjà utilisés dans reporter.py (CHALEUR, PLUIE_INTENSE, VENT_FORT).
    """
    alert_types_path = 'static_data/alerts_types.json'

    default_alert_types = [
        ('CHALEUR', 'Alerte chaleur'),
        ('PLUIE_INTENSE', 'Alerte pluie intense'),
        ('VENT_FORT', 'Alerte vent fort'),
    ]

    if os.path.exists(alert_types_path):
        with open(alert_types_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Format attendu: {"load_alert_thresholds": [{"code": "...", "libelle": "..."}, ...]}
        rows = [(a['code'], a.get('libelle')) for a in data.get('alert_types', [])]
        if not rows:
            print(f"alerts_types.json vide, utilisation de la liste par défaut")
            rows = default_alert_types
    else:
        print(f"Fichier non trouvé: {alert_types_path} — utilisation de la liste par défaut")
        rows = default_alert_types

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO alert_types (code, libelle)
            VALUES %s
            ON CONFLICT (code) DO UPDATE
            SET libelle = EXCLUDED.libelle
        """, rows)
    conn.commit()
    print(f"✓ {len(rows)} types d'alerte chargés")

def load_weather_locations(conn):
    """Charge les stations météo"""
    locations_path = 'static_data/weather_locations.csv'
    if not os.path.exists(locations_path):
        print(f"Fichier non trouvé: {locations_path}")
        return
    
    with open(locations_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        locations = [(row['id'], row['nom'], row['latitude'], 
                      row['longitude'], row['region_id']) for row in reader]
    
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO weather_locations (id, nom, latitude, longitude, region_id) 
            VALUES %s 
            ON CONFLICT (id) DO UPDATE 
            SET nom = EXCLUDED.nom, latitude = EXCLUDED.latitude, 
                longitude = EXCLUDED.longitude, region_id = EXCLUDED.region_id
        """, locations)
    conn.commit()
    print(f"✓ {len(locations)} stations météo chargées")

def load_alert_thresholds(conn):
    """
    Charge les seuils d'alerte (weather_thresholds.json d'Amboara).
    Le fichier référence une variable par son CODE (ex: 'temperature_2m'),
    on le convertit en variable_id via la table `variables` (chargée juste avant).
    """
    thresholds_path = 'static_data/weather_thresholds.json'
    if not os.path.exists(thresholds_path):
        print(f"Fichier non trouvé: {thresholds_path}")
        return

    with open(thresholds_path, 'r', encoding='utf-8') as f:
        thresholds = json.load(f)

    with conn.cursor() as cur:
        # Récupère le mapping code -> id depuis la table variables
        cur.execute('SELECT id, code FROM variables')
        var_map = {code: vid for vid, code in cur.fetchall()}

        count = 0
        for threshold in thresholds.get('thresholds', []):
            code = threshold.get('variable')
            variable_id = var_map.get(code)
            if variable_id is None:
                print(f"  ⚠ variable inconnue '{code}', seuil ignoré")
                continue

            cur.execute("""
                INSERT INTO weather_thresholds
                (variable_id, region_id, seuil_min, seuil_max, severite, message)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (variable_id, region_id) DO UPDATE
                SET seuil_min = EXCLUDED.seuil_min,
                    seuil_max = EXCLUDED.seuil_max,
                    severite = EXCLUDED.severite,
                    message = EXCLUDED.message
            """, (
                variable_id,
                threshold.get('region_id'),
                threshold.get('min_value'),
                threshold.get('max_value'),
                threshold.get('alert_level', 'warning'),
                threshold.get('message', '')
            ))
            count += 1
    conn.commit()
    print(f"✓ {count} seuils d'alerte chargés")

def main():
    print("🚀 Initialisation de la base de données météo Madagascar")

    conn = None
    try:
        conn = get_db_connection()
        print("✓ Connexion PostgreSQL établie")
        
        # Charger d'abord le schéma SQL unifié
        schema_path = './schema.sql'
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
            print("✓ Schéma SQL unifié chargé")
        else:
            print(f"⚠ Schéma non trouvé à {schema_path} (déjà appliqué manuellement ?)")

        # Charger les données statiques
        # Ordre important : climate_types/variables/alert_types avant les tables
        # qui les référencent (regions -> climate_types, weather_thresholds -> variables)
        load_climate_types(conn)
        load_regions(conn)
        load_weather_locations(conn)
        load_variables(conn)
        load_alert_types(conn)
        load_alert_thresholds(conn)  # dépend de load_variables (mapping code -> id)
        
        print("\n✅ Seed terminé avec succès!")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 1
    finally:
        if conn:
            conn.close()
    
    return 0

if __name__ == "__main__":
    exit(main())