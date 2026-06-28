"""
DAG Airflow — Weather ETL Madagascar
======================================
Phase 7 du todo : orchestre toutes les étapes du pipeline.

Architecture des tâches :
    [extract_current]  (toutes les heures)
           |
    [extract_hourly_daily]  (une fois par jour — BranchPythonOperator)
           |
    [transform_clean]
           |
    [aggregate_daily]
           |
    [generate_reports]
           |
    [quality_checks]

Deux DAGs séparés pour respecter les deux fréquences du todo :
  - weather_current_dag  : @hourly  → extraction current + transformation
  - weather_daily_dag    : @daily   → extraction hourly/daily + toute la chaîne
"""

from datetime import datetime, timedelta
import os
import sys

from airflow import DAG
from airflow.operators.python import PythonOperator

# Ajoute le dossier parent (elia/) au path Python pour les imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import extractor
import transformer
import reporter
import quality

# ──────────────────────────────────────────────
# Arguments communs aux deux DAGs
# ──────────────────────────────────────────────
DEFAULT_ARGS = {
    'owner': 'elia',
    'depends_on_past': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': False,   # mettre True + email si configuré
    'email_on_retry': False,
}

# ──────────────────────────────────────────────
# DAG 1 — Extraction current (toutes les heures)
# ──────────────────────────────────────────────
with DAG(
    dag_id='weather_current_dag',
    default_args=DEFAULT_ARGS,
    description='Extraction météo actuelle (Open-Meteo) — toutes les heures',
    schedule_interval='@hourly',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['weather', 'current'],
) as current_dag:

    t_extract_current = PythonOperator(
        task_id='extract_current',
        python_callable=extractor.run_current,
        doc_md="""
        Appelle Open-Meteo avec `current=temperature_2m,...` pour chaque station.
        Stocke la réponse brute dans `weather_raw` (api_type='current').
        """
    )

    t_transform = PythonOperator(
        task_id='transform_clean',
        python_callable=transformer.run_transform,
        doc_md="""
        Parse les entrées non traitées de `weather_raw` → `weather_clean`.
        """
    )

    t_quality = PythonOperator(
        task_id='quality_checks',
        python_callable=quality.run_checks,
        doc_md="""
        Vérifie les valeurs hors plage et NULL dans `weather_clean`.
        Logue les anomalies dans `data_quality`.
        """
    )

    # Chaîne : extract → transform → quality
    t_extract_current >> t_transform >> t_quality


# ──────────────────────────────────────────────
# DAG 2 — Pipeline complet quotidien
# ──────────────────────────────────────────────
with DAG(
    dag_id='weather_daily_dag',
    default_args=DEFAULT_ARGS,
    description='Pipeline ETL complet — extraction hourly/daily, agrégation, rapports',
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['weather', 'daily', 'etl'],
) as daily_dag:

    t_extract_hd = PythonOperator(
        task_id='extract_hourly_daily',
        python_callable=extractor.run_hourly_daily,
        doc_md="""
        Appelle Open-Meteo en mode `hourly` et `daily` pour chaque station.
        Stocke dans `weather_raw`.
        """
    )

    t_transform2 = PythonOperator(
        task_id='transform_clean',
        python_callable=transformer.run_transform,
        doc_md="Parse weather_raw non traité → weather_clean."
    )

    t_aggregate = PythonOperator(
        task_id='aggregate_daily',
        python_callable=transformer.run_aggregate,
        doc_md="""
        Calcule temp_avg/min/max, précipitations, humidité, vent par jour et station.
        Insère/met à jour `weather_daily`.
        """
    )

    t_reports = PythonOperator(
        task_id='generate_reports',
        python_callable=reporter.generate_reports,
        doc_md="""
        Génère un rapport textuel par station/jour depuis `weather_daily`.
        Déclenche les alertes si les seuils sont dépassés.
        """
    )

    t_quality2 = PythonOperator(
        task_id='quality_checks',
        python_callable=quality.run_checks,
        doc_md="Contrôle qualité final sur weather_clean."
    )

    # Chaîne complète
    t_extract_hd >> t_transform2 >> t_aggregate >> t_reports >> t_quality2
