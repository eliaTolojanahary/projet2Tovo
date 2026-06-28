--
-- PostgreSQL database dump
--

\restrict jtCxWgUJfe3fq89zhY7BTaIm1xXeO7sijafzQqAbm5jU0siegdQfbIcXvuNOqVb

-- Dumped from database version 13.23 (Debian 13.23-1.pgdg13+1)
-- Dumped by pg_dump version 13.23 (Debian 13.23-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: alerts; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.alerts (id, location_id, alert_type_id, severite, message, acknowledged, created_at) FROM stdin;
\.


--
-- Data for Name: weather_raw; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.weather_raw (id, location_id, api_type, raw_json, fetched_at) FROM stdin;
\.


--
-- Data for Name: data_quality; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.data_quality (id, location_id, variable_id, anomaly_type, valeur_detectee, source_raw_id, created_at) FROM stdin;
\.


--
-- Data for Name: etl_logs; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.etl_logs (id, process_name, status, records_processed, error_message, started_at, completed_at, details, created_at) FROM stdin;
\.


--
-- Data for Name: weather_clean; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.weather_clean (id, location_id, variable_id, valeur, "timestamp", source_raw_id, created_at) FROM stdin;
\.


--
-- Data for Name: weather_daily; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.weather_daily (id, location_id, date, temp_avg, temp_min, temp_max, precipitation_sum, humidity_avg, wind_speed_avg, uv_index_max, created_at) FROM stdin;
\.


--
-- Data for Name: weather_report; Type: TABLE DATA; Schema: public; Owner: weather_user
--

COPY public.weather_report (id, location_id, date, summary_text, temp_avg, temp_min, temp_max, precipitation_sum, humidity_avg, wind_speed_avg, created_at) FROM stdin;
\.


--
-- Name: alerts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.alerts_id_seq', 1, false);


--
-- Name: data_quality_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.data_quality_id_seq', 1, false);


--
-- Name: etl_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.etl_logs_id_seq', 1, false);


--
-- Name: weather_clean_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.weather_clean_id_seq', 1, false);


--
-- Name: weather_daily_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.weather_daily_id_seq', 1, false);


--
-- Name: weather_raw_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.weather_raw_id_seq', 1, false);


--
-- Name: weather_report_id_seq; Type: SEQUENCE SET; Schema: public; Owner: weather_user
--

SELECT pg_catalog.setval('public.weather_report_id_seq', 1, false);


--
-- PostgreSQL database dump complete
--

\unrestrict jtCxWgUJfe3fq89zhY7BTaIm1xXeO7sijafzQqAbm5jU0siegdQfbIcXvuNOqVb

