# Barcelona Mobility Control Room — V2

This is a clean V2 prototype for a Barcelona-focused urban mobility control room.

It includes:
- a central geolocated city map,
- real Barcelona hotspots loaded from CSV,
- a synthetic mobility runtime with classical / quantum / fallback routing,
- stable scenario switching,
- cleaner operator views for twins, risk and audit.

## Files
- `app.py`: Streamlit UI
- `mobility_runtime.py`: synthetic city runtime
- `barcelona_mobility_hotspots.csv`: hotspot catalogue

## Run
```bash
streamlit run app.py
```
