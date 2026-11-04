# Inventaire des sources (2026-10-10T20:32:08+00:00)

Toutes les valeurs sont recalculées à partir des fichiers. Constats hérités : section dédiée.

| Source | Type | Taille | Lignes | Col. | Sép. | Période | Doublons exacts | Clé candidate unique ? |
|---|---|---|---|---|---|---|---|---|
| `data/historical/cita/events/cita_events_historical.csv` | CITA csv | 0.04 Mo | 223 | 16 | `,` | collection_time: 2026-10-07T18:30:00.324388 → 2026-10-07T18:41:06.172293; creation_time: 2025-03-30T14:20:12+02:00 → 2026-10-07T19:34:05+02:00; start_time: 2023-03-24T18:30:00+01:00 → 2026-10-07T19:34:05+02:00 | 0 | creation_time+start_time+destination+latitude+longitude: non (204 doublons) |
| `data/historical/cita/events/cita_events_live.csv` | CITA csv | 8.00 Mo | 36402 | 18 | `,` | collection_time: 2026-10-07T18:57:22.737813 → 2026-10-09T09:58:12.691942; creation_time: 2025-03-30T14:20:12+02:00 → 2026-10-09T10:45:31+02:00; start_time: 2023-03-24T18:30:00+01:00 → 2026-10-09T10:45:31+02:00; version_time: 2025-05-12T10:38:13+02:00 → 2026-10-09T10:45:45+02:00 | 0 | creation_time+start_time+destination+latitude+longitude+version_time: non (36287 doublons) |
| `data/historical/cita/traffic/cita_traffic_historical.csv` | CITA csv | 0.23 Mo | 2717 | 10 | `,` | collection_time: 2026-10-07T18:31:02.844955 → 2026-10-07T18:41:05.656861; timestamp: 2026-10-07T19:28:00+02:00 → 2026-10-07T19:38:00+02:00 | 54 | road+timestamp+latitude+longitude: non (2040 doublons) |
| `data/historical/cita/traffic/cita_traffic_historical_fixed.csv` | CITA csv | 12.21 Mo | 106808 | 11 | `;` | collection_time: 2026-10-07T18:45:27.546975 → 2026-10-09T09:58:17.485119; timestamp: 2026-10-07T19:38:00+02:00 → 2026-10-09T10:53:00+02:00 | 0 | measurement_site+timestamp+direction: non (104933 doublons) |
| `data/historical/cita/traffic/cita_traffic_live.csv` | CITA csv | 1.82 Mo | 31925 | 10 | `,` | collection_time: 2026-10-07T18:59:32.387020 → 2026-10-09T09:58:08.208068 | 0 | collection_time+road+latitude+longitude+direction: non (17224 doublons) |
| `data/raw/cita/trafficstatus_a1.xml` | XML | 0.17 Mo | 40 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_a13.xml` | XML | 0.22 Mo | 51 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_a3.xml` | XML | 0.11 Mo | 29 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_a4.xml` | XML | 0.11 Mo | 25 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_a6.xml` | XML | 0.17 Mo | 36 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_a7.xml` | XML | 0.20 Mo | 48 | - | `-` | - | - | - |
| `data/raw/cita/trafficstatus_b40.xml` | XML | 0.08 Mo | 18 | - | `-` | - | - | - |
| `data/raw/cita_events/situationrecord36.xml` | XML | 0.07 Mo | 18 | - | `-` | - | - | - |
| `data/raw/weather/weather_static.xml` | XML | 0.08 Mo | - | - | `-` | - | - | - |
| `data/raw/gtfs/extracted/agency.txt` | GTFS | 0.00 Mo | 6 | 6 | `,` | - | 0 | agency_id: oui |
| `data/raw/gtfs/extracted/calendar.txt` | GTFS | 0.01 Mo | 267 | 10 | `,` | - | 0 | service_id: oui |
| `data/raw/gtfs/extracted/calendar_dates.txt` | GTFS | 0.03 Mo | 1858 | 3 | `,` | - | 0 | service_id+date: oui |
| `data/raw/gtfs/extracted/frequencies.txt` | GTFS | 0.00 Mo | 0 | 5 | `,` | - | 0 | - |
| `data/raw/gtfs/extracted/routes.txt` | GTFS | 0.02 Mo | 716 | 8 | `,` | - | 0 | route_id: oui |
| `data/raw/gtfs/extracted/shapes.txt` | GTFS | 40.82 Mo | 1437953 | 4 | `,` | - | 0 | shape_id+shape_pt_sequence: oui |
| `data/raw/gtfs/extracted/stop_times.txt` | GTFS | 33.05 Mo | 660706 | 8 | `,` | - | 0 | trip_id+stop_sequence: oui |
| `data/raw/gtfs/extracted/stops.txt` | GTFS | 0.24 Mo | 2805 | 10 | `,` | - | 0 | stop_id: oui |
| `data/raw/gtfs/extracted/transfers.txt` | GTFS | 0.11 Mo | 2903 | 8 | `,` | - | 0 | from_stop_id+to_stop_id+from_route_id+to_route_id+from_trip_id+to_trip_id: oui |
| `data/raw/gtfs/extracted/trips.txt` | GTFS | 1.78 Mo | 28993 | 10 | `,` | - | 0 | trip_id: oui |
| `data/raw/gtfs/luxembourg_gtfs.zip` | GTFS zip | 16.85 Mo | - | - | `-` | - | - | - |
| `data/raw/traffic/trafic_2025.xlsx` | PCH xlsx | 150.90 Mo | 815739 | 36 | `-` | - | - | - |

## Colonnes entièrement vides

- `data/historical/cita/events/cita_events_historical.csv` : impact, comment, location_description
- `data/historical/cita/events/cita_events_live.csv` : event_type, road, impact, comment
- `data/historical/cita/traffic/cita_traffic_historical.csv` : measurement_site, speed_kmh, occupancy_percent, vehicle_flow
- `data/historical/cita/traffic/cita_traffic_historical_fixed.csv` : vehicle_flow
- `data/historical/cita/traffic/cita_traffic_live.csv` : measurement_site, timestamp, occupancy_percent
- `data/raw/gtfs/extracted/agency.txt` : agency_lang, agency_phone
- `data/raw/gtfs/extracted/frequencies.txt` : trip_id, start_time, end_time, headway_secs, exact_times
- `data/raw/gtfs/extracted/routes.txt` : route_long_name
- `data/raw/gtfs/extracted/stop_times.txt` : stop_headsign
- `data/raw/gtfs/extracted/stops.txt` : stop_code, stop_desc, parent_station, platform_code
- `data/raw/gtfs/extracted/transfers.txt` : from_trip_id, to_trip_id

## Sorties existantes et statut

| Fichier | Statut |
|---|---|
| `data/interim/pch/pch_trafic_2025_export_v1.PARTIAL_INVALID_killed_20261010.csv.gz` | INVALID - truncated partial export (process killed), kept, not used |
| `data/interim/cita/cita_events_combined.csv` | INVALID - produced by prepare_cita.py with sep=';' forced (4/5 sources read as 1 column) |
| `data/interim/cita/cita_events_states.csv` | current |
| `data/interim/cita/cita_traffic_combined.csv` | INVALID - produced by prepare_cita.py with sep=';' forced (4/5 sources read as 1 column) |
| `data/interim/cita/cita_traffic_fixed_unique.csv` | DIAGNOSTIC ONLY - site attribution unreliable |
| `data/interim/pch/pch_trafic_2025_export_v1.csv.xz` | current |
| `data/processed/cita_events/cita_events_clean.csv` | current |
| `data/processed/cita_events.csv` | LEGACY - convert_events.py output from one XML snapshot, no ids; superseded |
| `data/processed/cita_traffic/cita_traffic_clean.csv` | DIAGNOSTIC ONLY - site attribution unreliable (faulty v1 collector); never for spatial models |
| `data/processed/cita_traffic.csv` | LEGACY - convert_cita.py output from one XML snapshot: no sensor id, no speed; not used |
| `data/reports/CITA_DATA_QUALITY.md` | current |
| `data/reports/cita_diagnostic.json` | current |
| `data/reports/cita_events_cleaning_report.json` | current |
| `data/reports/cita_events_combined_initial_report.json` | INVALID - same cause as the *_combined.csv files |
| `data/reports/cita_events_matching.csv` | current |
| `data/reports/cita_traffic_cleaning_report.json` | current |
| `data/reports/cita_traffic_combined_initial_report.json` | INVALID - same cause as the *_combined.csv files |

## Dossiers sources vides

- `data/raw/accidents`
- `data/raw/cita/events`
- `data/raw/cita/traffic`
- `data/raw/pch`
- `data/historical/cita/travel_time`

## Constats hérités

- cita_traffic_historical_fixed.csv: values of the LAST sensor of each road XML with the position of the FIRST one (faulty v1 collector) — revérifié : by tests/test_collect_cita_fixed.py (old parser executed on raw XML)
- cita_traffic_live.csv: speed rows and flow rows separate, no sensor id, no measurement time — revérifié : here (fully empty columns)
- data/interim/cita/*_combined.csv and *_combined_initial_report.json produced with sep=';' forced: INVALID — revérifié : here (column count of the combined files)
