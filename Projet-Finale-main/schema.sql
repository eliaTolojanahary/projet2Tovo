-- ==============================================================
-- schema.sql - Schéma UNIFIÉ - Weather Analytics Madagascar
-- ==============================================================
-- Ce schéma remplace la version précédente de Manoa. Il a été
-- reconstruit en croisant les besoins réels de :
--   extractor.py, transformer.py, quality.py, reporter.py, seed.py
-- afin que tout le pipeline ETL fonctionne sans erreur de table
-- ou de colonne manquante.
--
-- PostGIS retiré : latitude/longitude restent en DECIMAL simples
-- (le projet n'a pas besoin de fonctions géospatiales avancées).
-- ==============================================================


-- ──────────────────────────────────────────────
-- Référentiels statiques (Amboara / Manoa)
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS climate_types (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY,  -- pas SERIAL : seed.py insère des id explicites depuis le CSV
    nom VARCHAR(100) NOT NULL UNIQUE,
    chef_lieu VARCHAR(100),
    superficie_km2 DECIMAL(10,2),
    population INTEGER,
    climate_type_id INTEGER REFERENCES climate_types(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weather_locations (
    id INTEGER PRIMARY KEY,  -- pas SERIAL : seed.py insère des id explicites depuis le CSV
    nom VARCHAR(100) NOT NULL,
    latitude DECIMAL(10,8) NOT NULL,
    longitude DECIMAL(11,8) NOT NULL,
    region_id INTEGER REFERENCES regions(id),
    altitude_m DECIMAL(8,2),
    api_source VARCHAR(50),
    api_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nom, region_id)
);

-- Catalogue des variables météo (temperature_2m, precipitation, ...)
-- Utilisé par transformer.py et quality.py pour mapper code -> id
CREATE TABLE IF NOT EXISTS variables (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,   -- ex: 'temperature_2m', 'precipitation'
    unite VARCHAR(20),                  -- ex: '°C', 'mm', 'km/h'
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Types d'alerte (chaleur, pluie intense, vent fort...)
CREATE TABLE IF NOT EXISTS alert_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,   -- ex: 'CHALEUR', 'PLUIE_INTENSE', 'VENT_FORT'
    libelle VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ──────────────────────────────────────────────
-- Pipeline ETL — données brutes et nettoyées
-- ──────────────────────────────────────────────

-- Données brutes JSON reçues de l'API (Open-Meteo).
-- Phase 2 du todo d'Elia : "Stocker la réponse brute JSON -> weather_raw"
CREATE TABLE IF NOT EXISTS weather_raw (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    api_type VARCHAR(20) NOT NULL,      -- 'current' | 'hourly' | 'daily'
    raw_json JSONB NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Données nettoyées, une ligne par (location, variable, timestamp).
-- Alimentée par transformer.py depuis weather_raw.
CREATE TABLE IF NOT EXISTS weather_clean (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    variable_id INTEGER REFERENCES variables(id),
    valeur DECIMAL(10,3),
    timestamp TIMESTAMP NOT NULL,
    source_raw_id INTEGER REFERENCES weather_raw(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, variable_id, timestamp)
);

-- Mesures météo "classiques" en colonnes (utilisée par extractor.py
-- pour l'API current avec écriture directe, en parallèle de weather_raw).
CREATE TABLE IF NOT EXISTS weather_measurements (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    measurement_time TIMESTAMP NOT NULL,
    temperature_c DECIMAL(5,2),
    humidity_percent DECIMAL(5,2),
    pressure_hpa DECIMAL(7,2),
    wind_speed_ms DECIMAL(5,2),
    wind_direction_deg INTEGER,
    precipitation_mm DECIMAL(6,2),
    cloud_cover_percent DECIMAL(5,2),
    visibility_m INTEGER,
    weather_condition VARCHAR(100),
    data_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, measurement_time)
);

-- Agrégations journalières — alimentée par transformer.py (run_aggregate)
-- et lue par reporter.py.
CREATE TABLE IF NOT EXISTS weather_daily (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    date DATE NOT NULL,
    temp_avg DECIMAL(5,2),
    temp_min DECIMAL(5,2),
    temp_max DECIMAL(5,2),
    precipitation_sum DECIMAL(8,2),
    humidity_avg DECIMAL(5,2),
    wind_speed_avg DECIMAL(5,2),
    uv_index_max DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, date)
);

-- Conservée pour compatibilité (équivalent agrégat alternatif, non
-- utilisée directement par les scripts actuels mais gardée au cas où).
CREATE TABLE IF NOT EXISTS daily_aggregates (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    date DATE NOT NULL,
    avg_temp_c DECIMAL(5,2),
    min_temp_c DECIMAL(5,2),
    max_temp_c DECIMAL(5,2),
    total_precipitation_mm DECIMAL(8,2),
    avg_humidity_percent DECIMAL(5,2),
    avg_wind_speed_ms DECIMAL(5,2),
    data_completeness_pct DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, date)
);


-- ──────────────────────────────────────────────
-- Rapports, seuils et alertes
-- ──────────────────────────────────────────────

-- Rapport texte par station/jour — alimentée par reporter.py.
CREATE TABLE IF NOT EXISTS weather_report (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    date DATE NOT NULL,
    summary_text TEXT,
    temp_avg DECIMAL(5,2),
    temp_min DECIMAL(5,2),
    temp_max DECIMAL(5,2),
    precipitation_sum DECIMAL(8,2),
    humidity_avg DECIMAL(5,2),
    wind_speed_avg DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, date)
);

-- Seuils d'alerte par variable — lus par reporter.py (seuil_max, severite).
CREATE TABLE IF NOT EXISTS weather_thresholds (
    id SERIAL PRIMARY KEY,
    variable_id INTEGER REFERENCES variables(id),
    region_id INTEGER REFERENCES regions(id),  -- NULL = seuil global (toutes régions)
    seuil_min DECIMAL(10,2),
    seuil_max DECIMAL(10,2),
    severite VARCHAR(20) DEFAULT 'warning',    -- ex: 'warning', 'critical'
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(variable_id, region_id)
);

-- Alertes générées par reporter.py quand un seuil est dépassé.
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    alert_type_id INTEGER REFERENCES alert_types(id),
    severite VARCHAR(20),
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ──────────────────────────────────────────────
-- Qualité des données et logs ETL
-- ──────────────────────────────────────────────

-- Anomalies détectées par quality.py (NULL_VALUE, OUT_OF_RANGE...).
CREATE TABLE IF NOT EXISTS data_quality (
    id SERIAL PRIMARY KEY,
    location_id INTEGER REFERENCES weather_locations(id),
    variable_id INTEGER REFERENCES variables(id),
    anomaly_type VARCHAR(30) NOT NULL,   -- 'NULL_VALUE' | 'OUT_OF_RANGE'
    valeur_detectee DECIMAL(10,3),
    source_raw_id INTEGER REFERENCES weather_raw(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Logs d'exécution ETL — alimentée par extractor.py.
CREATE TABLE IF NOT EXISTS etl_logs (
    id SERIAL PRIMARY KEY,
    process_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    records_processed INTEGER,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ──────────────────────────────────────────────
-- Index pour les performances
-- ──────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_weather_raw_location_type
    ON weather_raw(location_id, api_type);
CREATE INDEX IF NOT EXISTS idx_weather_clean_location_var_ts
    ON weather_clean(location_id, variable_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_weather_measurements_location_time
    ON weather_measurements(location_id, measurement_time);
CREATE INDEX IF NOT EXISTS idx_weather_measurements_time
    ON weather_measurements(measurement_time);
CREATE INDEX IF NOT EXISTS idx_weather_daily_date
    ON weather_daily(date);
CREATE INDEX IF NOT EXISTS idx_daily_aggregates_date
    ON daily_aggregates(date);
CREATE INDEX IF NOT EXISTS idx_weather_report_date
    ON weather_report(date);
CREATE INDEX IF NOT EXISTS idx_alerts_created
    ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_data_quality_created
    ON data_quality(created_at);
CREATE INDEX IF NOT EXISTS idx_etl_logs_status
    ON etl_logs(status);