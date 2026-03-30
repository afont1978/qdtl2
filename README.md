# Barcelona Mobility Control Room v3

Version 3 of the Barcelona mobility prototype with:
- central layered map
- hotspot focus selector
- real Barcelona hotspots from CSV
- stable scenario switching via form
- clearer navigation between overview, twins, risk and audit

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```


## v5 stable live architecture
This version uses a single Streamlit fragment as a dedicated Live Monitor. The rest of the tabs are static snapshots to reduce flicker.
