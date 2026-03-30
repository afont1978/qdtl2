# Sprint 8 — Rail & Interchange Expansion

This sprint extends the Barcelona mobility model with:

- Metro TMB
- Rodalies / Renfe
- FGC
- Interchange nodes

## New twins
- MetroStationTwin
- MetroLineTwin
- RodaliesStationTwin
- RodaliesLineTwin
- FGCStationTwin
- FGCLineTwin
- InterchangeNodeTwin

## New aggregated state
- urban_rail_burden
- metro_pressure_index
- rodalies_pressure_index
- fgc_pressure_index
- interchange_pressure_index
- rail_disruption_pressure
- airport_rail_access_pressure
- city_intermodal_score
- dominant_rail_subsystem
- dominant_interchange
- rail_assisted_mitigation_potential

## New decision subproblems
- rail_load_balancing_problem
- interchange_overload_problem
- airport_access_multimodal_problem
- rail_disruption_response_problem
- event_evacuation_multimodal_problem

## Data updates
- Extended hotspot CSV with rail/interchange nodes and aliases
- Added optional `scenario_library_high_complexity_v2.json` in `data/` when available
- Base scenario library patched with rail and interchange shocks

## Notes
This sprint focuses on model/runtime expansion. The UI can surface these new fields in a later sprint.
