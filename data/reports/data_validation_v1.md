# Data validation (v1)

73/73 checks passed - 2026-10-10T20:58:22+00:00

| Dataset | Check | Result | Detail |
|---|---|---|---|
| cita_traffic_reference_v1 | file exists | PASS |  |
| cita_traffic_reference_v1 | recommended columns present | PASS |  |
| cita_traffic_reference_v1 | no fabricated vehicle_flow column | PASS |  |
| cita_traffic_reference_v1 | numeric columns parse | PASS |  |
| cita_traffic_reference_v1 | speed 0-250 km/h | PASS |  |
| cita_traffic_reference_v1 | occupancy 0-100 % | PASS |  |
| cita_traffic_reference_v1 | flow >= 0 veh/h | PASS |  |
| cita_traffic_reference_v1 | flow period 3600 s (unit) | PASS |  |
| cita_traffic_reference_v1 | coordinates inside Luxembourg bbox | PASS |  |
| cita_traffic_reference_v1 | measurement_timestamp keeps explicit offset | PASS |  |
| cita_traffic_reference_v1 | *_utc timestamps end in +00:00 | PASS |  |
| cita_traffic_reference_v1 | collection after measurement | PASS |  |
| cita_traffic_reference_v1 | key sensor_id+measurement_timestamp unique (no artificial duplicate) | PASS |  |
| cita_traffic_reference_v1 | sensor id prefix matches road | PASS |  |
| cita_traffic_reference_v1 | data_origin real only | PASS |  |
| cita_traffic_reference_v1 | no legacy rows | PASS |  |
| cita_traffic_reference_v1 | every source_file exists | PASS |  |
| cita_traffic_reference_v1 | missing sensor_id <= 0% | PASS |  |
| cita_traffic_reference_v1 | missing measurement_timestamp <= 0% | PASS |  |
| cita_traffic_reference_v1 | missing speed_kmh <= 15% | PASS |  |
| cita_traffic_reference_v1 | missing occupancy_percent <= 15% | PASS |  |
| cita_traffic_reference_v1 | missing vehicle_flow_rate <= 5% | PASS |  |
| cita_traffic_reference_v1 | missing latitude <= 15% | PASS |  |
| cita_traffic_reference_v1 | missing source_file <= 0% | PASS |  |
| cita_traffic_reference_v1 | missing data_origin <= 0% | PASS |  |
| cita_traffic_reference_v1 | no CITA sensor inside the Kirchberg 4-signal zone (documented fact) | PASS |  |
| cita_events_v1 | file exists cita_events_record_versions_v1.csv | PASS |  |
| cita_events_v1 | file exists cita_events_v1.csv | PASS |  |
| cita_events_v1 | file exists cita_events_correspondence_v1.csv | PASS |  |
| cita_events_v1 | states: (record_id, record_version) unique | PASS |  |
| cita_events_v1 | events: record_id unique | PASS |  |
| cita_events_v1 | record_id prefixed by situation_id | PASS |  |
| cita_events_v1 | every event has its states | PASS |  |
| cita_events_v1 | versions are integers | PASS |  |
| cita_events_v1 | DATEX times keep explicit offsets | PASS |  |
| cita_events_v1 | safety_related_message normalised (true/false/NA) | PASS |  |
| cita_events_v1 | correspondence record_ids exist | PASS |  |
| cita_events_v1 | correspondence confidence in exact/uncertain/none | PASS |  |
| cita_events_v1 | missing record_id <= 0% | PASS |  |
| cita_events_v1 | missing situation_id <= 0% | PASS |  |
| cita_events_v1 | missing record_type <= 0% | PASS |  |
| cita_events_v1 | missing creation_time <= 0% | PASS |  |
| cita_events_v1 | missing overall_start_time <= 0% | PASS |  |
| cita_events_v1 | data_origin real only | PASS |  |
| pch_v1 | posts file exists | PASS |  |
| pch_v1 | daily file exists | PASS |  |
| pch_v1 | POSTE_ID unique in posts | PASS |  |
| pch_v1 | WGS84 coordinates inside Luxembourg bbox (+border posts margin) | PASS |  |
| pch_v1 | daily: key post+date+direction+vehicle unique | PASS |  |
| pch_v1 | daily: hours sum == SUM_TRAF | PASS |  |
| pch_v1 | daily: counts >= 0 | PASS |  |
| pch_v1 | daily: no speed column (counts are not speeds) | PASS |  |
| pch_v1 | daily: data_origin real_pch_2025 | PASS |  |
| pch_v1 | daily: row count equals source export (815739) | PASS |  |
| gtfs_v1 | report exists | PASS |  |
| gtfs_v1 | primary keys unique | PASS |  |
| gtfs_v1 | foreign keys: no orphan | PASS |  |
| gtfs_v1 | times parse, no decrease inside trips | PASS |  |
| gtfs_v1 | trips prepared = trips source | PASS |  |
| gtfs_v1 | >24h times kept (not wrapped) | PASS |  |
| tasks_v1 | task files exist | PASS |  |
| tasks_v1 | task_A_event_label_inventory_v1.csv: only real rows | PASS |  |
| tasks_v1 | task_A_traffic_with_event_context_v1.csv: only real rows | PASS |  |
| tasks_v1 | task_B_forecast_panel_v1.csv: only real rows | PASS |  |
| tasks_v1 | task_C_SIMULATED_kpis_kirchberg_v1.csv: only simulated rows | PASS |  |
| tasks_v1 | task_C_SIMULATED_kpis_kirchberg_v1.csv: no legacy source | PASS |  |
| tasks_v1 | task_C_real_cita_observables_lust_bbox_v1.csv: only real rows | PASS |  |
| tasks_v1 | task_C_real_pch_potential_demand_profiles_v1.csv: only real rows | PASS |  |
| tasks_v1 | task_D_kpi_catalogue_v1.csv: simulated values labelled | PASS |  |
| tasks_v1 | B: split chronological (max train < min test) | PASS |  |
| tasks_v1 | B: lag only when previous step exactly 5 min | PASS |  |
| tasks_v1 | B: targets only where the exact future step exists (no filled gaps) | PASS |  |
| tasks_v1 | B: chronological order inside each sensor | PASS |  |
