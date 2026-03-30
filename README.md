# Barcelona Mobility Control Room

Clean starter repository for a separate project focused on a hybrid quantum-classical urban mobility control room for Barcelona.

## Included
- `app.py`: Streamlit UI with stable scenario switching
- `mobility_runtime.py`: mobility runtime anchored to Barcelona hotspots
- `barcelona_mobility_hotspots.csv`: hotspot dataset used by the runtime
- `requirements.txt`
- `.streamlit/config.toml`
- `.gitignore`

## Run locally
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Notes
- Keep `barcelona_mobility_hotspots.csv` in the repo root next to `mobility_runtime.py`.
- This package is intentionally minimal so it can be used as a new standalone repository.


## Sprint 1 structured layout

This repository has been reorganized to prepare a modular architecture under `src/mobility_os/` while keeping the application working through a compatibility wrapper in the project root.


## Sprint 2

This structured version adds a first modular decision stack:
- situation interpreter
- problem decomposer
- priority arbiter
- route selector
- intervention planner
- validator
- decision memory


## Sprint 6 — Urban Model v2

This version introduces a separated synthetic city engine, a scenario engine and JSON-based demand/scenario/policy profiles under `data/`. The runtime now consumes those modules instead of hardcoding the full urban context inline.
