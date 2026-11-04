# Readiness by objective (v1)

Generated 2026-10-10T20:56:06+00:00 by `scripts/data_pipeline/build_task_datasets_v1.py`.

## A. Incident detection

**Verdict: NOT TRAINABLE**

| Measured | Value |
|---|---|
| events_with_real_id | 24 |
| unplanned_events | 4 |
| accident_events | 0 |
| days_with_traffic_data | 2 |
| traffic_rows_with_event_context | 114 |

| Criterion | Threshold |
|---|---|
| min_unplanned_incident_events | 100 |
| min_accident_events | 30 |
| min_days_continuous_traffic | 28 |

## B. Forecasting +5/+10/+15 min

**Verdict: NOT TRAINABLE**

| Measured | Value |
|---|---|
| sensors | 247 |
| max_steps_per_sensor | 2 |
| distinct_timestamps | 3 |
| target_pairs_per_horizon | {5: 0, 10: 0, 15: 0} |
| lag1_available_rows | 0 |

| Criterion | Threshold |
|---|---|
| min_consecutive_days_per_sensor | 7 |
| min_steps_per_sensor | 2016 |
| max_missing_step_pct | 10.0 |
| min_sensors | 20 |
| min_target_pairs_per_horizon | 10000 |

## C. SUMO / RL

**Verdict: SIMULATION ONLY: RL can be trained and evaluated in SUMO; no real observation inside the Kirchberg zone, so no calibration or real validation**

| Measured | Value |
|---|---|
| cita_sensors_in_kirchberg_zone | 0 |
| pch_posts_in_kirchberg_zone | 0 |
| cita_sensors_in_lust_bbox | 63 |
| pch_posts_in_lust_bbox | 32 |
| pch_posts_with_unverified_lust_edge_candidates | 23 |
| gtfs_trips_at_kirchberg_zone_stops | 4684 |
| simulated_kpi_rows | 78 |

| Criterion | Threshold |
|---|---|
| min_real_observation_points_in_sim_zone | 1 |
| min_days_for_calibration | 5 |

## D. Impact KPIs

**Verdict: SIMULATED KPIs ONLY: no real baseline for travel time / queues / waiting in the zone**

| Measured | Value |
|---|---|
| kpis_catalogued | 9 |
| kpis_with_real_source | 2 |
| kpis_with_simulated_values | 8 |

| Criterion | Threshold |
|---|---|
| real_baseline_kpis_required | ['travel_time', 'speed', 'flow'] |

## Datasets

| Output | Rows x columns |
|---|---|
| `data/processed/tasks/task_A_event_label_inventory_v1.csv` | 24 x 16 |
| `data/processed/tasks/task_A_traffic_with_event_context_v1.csv` | 492 x 14 |
| `data/processed/tasks/task_B_forecast_panel_v1.csv` | 492 x 26 |
| `data/processed/tasks/task_C_real_cita_observables_lust_bbox_v1.csv` | 123 x 12 |
| `data/processed/tasks/task_C_real_pch_potential_demand_profiles_v1.csv` | 1968 x 18 |
| `data/processed/tasks/task_C_SIMULATED_kpis_kirchberg_v1.csv` | 78 x 6 |
| `data/processed/tasks/task_D_kpi_catalogue_v1.csv` | 9 x 6 |
