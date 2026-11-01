# Data dictionary

This dictionary describes the generated network dataset. CSV values are text; consumers should parse them using the types below. Blank values are optional and become SQL `NULL`. All identifiers are immutable uppercase strings. The first ten sections are the ten core entities; supporting/evaluation tables follow. All data is synthetic.

## Core entities (10)

### 1. Facility — `facilities.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `facility_id` | string | yes | `FAC-NNN` | Primary key; referenced by all facility equipment. |
| `name` | string | yes | Non-empty | Human-readable facility label. |
| `lifecycle_state` | enum | yes | `active` | Must be a supported lifecycle value. |

### 2. Pump — `pumps.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `pump_id` | string | yes | `PUMP-NNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `line_id` | string | yes | Line ID | FK to Line; one pump per line. |
| `nominal_flow_m3_h` | decimal | yes | m³/h, positive | Nominal flow must be > 0. |
| `shutoff_head_m` | decimal | yes | m, positive | Pump head at zero flow; must be > 0. |
| `lifecycle_state` | enum | yes | `active` | Must be a supported lifecycle value. |

### 3. Tank — `tanks.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `tank_id` | string | yes | `TANK-NNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `tank_role` | enum | yes | `shared_source`, `shared_destination`, `buffer` | Two shared hydraulic tanks and reserve tanks per facility. |
| `capacity_m3` | decimal | yes | m³, positive | Must be > 0. |
| `area_m2` | decimal | yes | m², positive | Must be > 0; used to compute level. |
| `initial_volume_m3` | decimal | yes | m³, between 0 and capacity | Must be within the tank capacity. |
| `lifecycle_state` | enum | yes | `active` | Must be a supported lifecycle value. |

### 4. Valve — `valves.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `valve_id` | string | yes | `VALVE-NNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `line_id` | string | yes | Line ID | FK to Line. |
| `normal_opening_pct` | decimal | yes | percent, 0–100 | Must be within the physical range. |
| `sequence_order` | integer | yes | Positive integer | Unique within its line; determines series order. |
| `resistance_k` | decimal | yes | m/(m³/h)² in the simplified model | Must be nonnegative. |
| `lifecycle_state` | enum | yes | `active` | Must be a supported lifecycle value. |

### 5. Pipe — `pipes.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `pipe_id` | string | yes | `PIPE-NNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility; endpoint nodes must belong to this facility. |
| `line_id` | string | no | Line ID or blank for a reserve-tank manifold | Optional FK to Line. |
| `from_node_id` | string | yes | Tank, pump, or valve ID | Must resolve to an equipment node in the same facility. |
| `to_node_id` | string | yes | Tank, pump, or valve ID | Must resolve to a different equipment node in the same facility. |
| `resistance_k` | decimal | yes | m/(m³/h)² | Must be nonnegative. |
| `edge_role` | enum | yes | `line_segment`, `buffer_manifold` | Describes topology edge purpose. |
| `sequence_order` | integer | no | Positive integer or blank | Present for line segments; optional for manifold edges. |
| `lifecycle_state` | enum | yes | `active` | Must be a supported lifecycle value. |

### 6. Line — `lines.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `line_id` | string | yes | `LINE-NNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `source_tank_id` | string | yes | Tank ID | FK to Tank in the same facility. |
| `destination_tank_id` | string | yes | Tank ID | FK to Tank; distinct from source tank. |
| `pump_id` | string | yes | Pump ID | FK to Pump; one pump per line. |
| `valve_id` | string | yes | Valve ID | FK to the final valve in this series train; full train is in `line_valves.csv`. |
| `pipe_id` | string | yes | Pipe ID | FK to the outlet segment; full route is in `line_pipes.csv`. |

### 7. Sensor — `sensors.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `sensor_id` | string | yes | `SNS-NNNNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `line_id` | string | no | Line ID or blank for tank-level sensor | Optional FK to Line. |
| `entity_type` | enum | yes | `pump`, `pipe`, `valve_train`, `tank` | Measurement target kind. |
| `entity_id` | string | no | Equipment ID or blank for pipe-mounted sensor | Polymorphic reference; use `pipe_id` for pipe sensors. |
| `node_id` | string | no | Equipment node ID or blank | Location reference when mounted on a node. |
| `pipe_id` | string | no | Pipe ID or blank | Optional FK to Pipe. |
| `position` | enum | yes | `inlet`, `outlet`, `discharge`, `valve_train_outlet`, `pipe_outlet`, `level` | Defines sensor location/sign convention. |
| `metric` | enum | yes | `flow`, `pressure`, `level` | Determines units and noise model. |
| `unit` | enum | yes | Flow=`m3/h`; pressure=`kPa`; level=`m` | Must agree with `metric`. |
| `initial_level_m` | decimal | no | m, tank sensors only | Configured starting level for the static reserve tanks. |

### 8. Telemetry — `telemetry.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `telemetry_id` | string | yes | `TLM-...` | Primary key. |
| `timestamp_utc` | timestamp | yes | ISO-8601 UTC ending in `Z` | Must parse; sample time within run window. |
| `sim_run_id` | string | yes | SimulationRun ID | FK to SimulationRun. |
| `operating_mode_id` | string | yes | Mode ID | FK to OperatingMode. |
| `facility_id` | string | yes | Facility ID | FK to Facility and consistent with sensor/run. |
| `line_id` | string | no | Line ID or blank for tank-level telemetry | Optional FK to Line. |
| `sensor_id` | string | yes | Sensor ID | FK to Sensor. |
| `entity_id` | string | no | Equipment ID or blank | Location metadata; no fault label. |
| `node_id` | string | no | Node ID or blank | Location metadata. |
| `pipe_id` | string | no | Pipe ID or blank | Optional FK to Pipe. |
| `position` | enum | yes | Same location values as Sensor | Must match sensor location. |
| `metric` | enum | yes | `flow`, `pressure`, `level` | Must match sensor metric. |
| `value` | decimal | yes | Unit from sensor | Finite measured value only. |
| `unit` | enum | yes | `m3/h`, `kPa`, `m` | Must match sensor unit. |
| `quality_flag` | enum | yes | `good` | Non-diagnostic quality field in this version. |

### 9. SimulationRun — `simulation_runs.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `sim_run_id` | string | yes | `SIM-2026-NNNNNN` | Primary key. |
| `facility_id` | string | yes | Facility ID | FK to Facility. |
| `seed` | integer | yes | Integer | Reproduces the random stream. |
| `config_hash` | string | yes | SHA-256 hex | Hash of canonical `config_json`. |
| `config_json` | JSON object | yes | Noise assumptions, seed, sample count, model inputs | Must parse; fault schedule/labels forbidden. |
| `started_at_utc` | timestamp | yes | ISO-8601 UTC | Fixed synthetic start instant. |
| `status` | enum | yes | `complete` | Run completed successfully. |

### 10. OperatingMode — `operating_modes.csv`

| Field | Type | Required | Allowed values / units | Unique / validation |
|---|---|---|---|---|
| `operating_mode_id` | string | yes | `MODE-NNN` | Primary key. |
| `name` | string | yes | `nominal` | Unique mode name recommended. |
| `description` | string | yes | Non-empty | Human-readable mode meaning. |
| `effective_from_utc` | timestamp | yes | ISO-8601 UTC | Beginning of validity interval. |
| `effective_to_utc` | timestamp | no | ISO-8601 UTC or blank | Optional open end; when present must follow start. |

## Relationships and ER diagram

```mermaid
erDiagram
  FACILITY ||--o{ TANK : owns
  FACILITY ||--o{ PUMP : owns
  FACILITY ||--o{ VALVE : owns
  FACILITY ||--o{ PIPE : owns
  FACILITY ||--o{ SENSOR : owns
  FACILITY ||--o{ SIMULATION_RUN : has
  TANK ||--o{ LINE : source_or_destination
  PUMP ||--|| LINE : serves
  LINE ||--o{ LINE_VALVES : contains
  VALVE ||--o{ LINE_VALVES : assigned_to
  LINE ||--o{ LINE_PIPES : contains
  PIPE ||--o{ LINE_PIPES : assigned_to
  SENSOR ||--o{ TELEMETRY : emits
  SIMULATION_RUN ||--o{ TELEMETRY : produces
  OPERATING_MODE ||--o{ TELEMETRY : labels
  VALVE ||--o{ VALVE_MODE_STATE : has_state
  OPERATING_MODE ||--o{ VALVE_MODE_STATE : governs
  TELEMETRY ||--o| ALARM : triggers
  SIMULATION_RUN ||--o{ GROUND_TRUTH : labeled_by
```

`line_valves.csv` and `line_pipes.csv` are many-to-many bridges; the line row's `valve_id`/`pipe_id` are convenience references to the final valve and outlet pipe. The valve/mode bridge is `valve_mode_states.csv`; its key includes valve, mode, and effective start. Both mode and bridge rows use effective-from/to timestamps, where end is optional. Tank sensors have no `line_id`; pipe-mounted sensors have a `pipe_id` and may have no `entity_id`. Tank and line links on telemetry are therefore optional depending on sensor location. `Alarm` has one required triggering telemetry row and an optional line association in the general schema. Pipe endpoints are polymorphic node references and must be validated against the equipment union in the same facility.

## Supporting and evaluation tables

| File | Key fields and validation |
|---|---|
| `line_valves.csv`, `line_pipes.csv` | Composite keys (`line_id`, asset ID); both columns are required FKs; sequence order is positive and unique per line. |
| `valve_mode_states.csv` | Composite temporal key (`valve_id`, `operating_mode_id`, `effective_from_utc`); state is `open` in the nominal mode; effective end is optional. |
| `alarms.csv` | `alarm_id` primary key; references run, facility, optional line, and triggering telemetry. `status` is `open`. |
| `ground_truth.csv` | `scenario_id` primary key; references run, evidence sensor, and evidence telemetry. Contains fault type/parameters, process-fault flag, effect, window noise, `detectable`, and `alarm_detected`; keep separate from features. Sensor faults set `is_process_fault=false`. |
| `process_truth.csv` | `telemetry_id` primary/FK; includes true value, injected noise, and sigma. Evaluation-only; never include in model features. |
| `equipment_events.csv` | `event_id` primary key; references run and cause scenario. Captures state change and restoration. |
| `network_balance.csv` | Composite key (timestamp, run, facility); true/measured residuals, flows, storage rate and tank levels. |
| `fault_location_rules.csv` | Expected signal direction per fault/location; documentation rows, not telemetry. |
| `negative_fixtures.csv` | `case_id` primary key; five isolated invalid examples and validator outcome. |
| `boundary_fixtures.csv` | `boundary_id` primary key; three valid near-limit examples and range-check outcome. |

## SQL, JSON, validation, and limits

`data/seed.sql` contains table DDL, primary/foreign keys, and inserts for every generated table, including evaluation tables. `data/export.json` is the feature-oriented JSON and contains no `ground_truth`, `process_truth`, `network_balance`, `alarms`, or `equipment_events` tables. `data/ground_truth.json` separately contains those evaluation/validation tables plus the network validation summary. Both JSON files use compact row arrays with an adjacent ordered `columns` list. `src/validate_sqlite.py` loads the full SQL seed into SQLite and checks FK integrity and joins among telemetry/sensors/runs/modes, telemetry/process truth, ground truth/evidence, alarms/trigger telemetry, and valve/mode rows. The full SQL seed is a validation bundle; detector feature tables must never join to ground-truth/process-truth tables.

`source_manifest.json` records synthetic provenance, seed, relative generator command, SHA-256 hashes for CSV/SQL/JSON/summary outputs, and CSV row counts. `network_validation_summary.json` records row totals, connectivity, validation outcomes, and residual statistics.

The process solver is steady state at each one-minute sample. Shared source/destination tanks evolve; the eight buffer tanks per facility are reserve tanks with configured levels and no simulated flow. Runs last about 69–71 minutes to retain full sensor coverage at exactly 100,000 telemetry rows; this dataset has no diurnal demand profile. Noise settings (2% flow, 1% pressure, 0.5% level relative sigma) are synthetic assumptions, not measured instrument noise. The residual tolerance is a two-sided 99% Gaussian envelope propagated from independent inlet/outlet flow noise, not a measured residual standard deviation or a 3σ residual limit.
