from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from .io import Hotspot


def hotspots_to_dataframe(hotspots: dict[str, Hotspot]) -> pd.DataFrame:
    rows = [hs.to_dict() for hs in hotspots.values()]
    return pd.DataFrame(rows)


def get_hotspot_by_name(name: str, hotspots: dict[str, Hotspot]) -> Optional[Hotspot]:
    return hotspots.get(name)


def filter_hotspots_by_layer(df: pd.DataFrame, layers: Iterable[str]) -> pd.DataFrame:
    if df.empty:
        return df
    layers = list(layers)
    if not layers:
        return df
    mask = pd.Series(False, index=df.index)
    for layer in layers:
        if layer == 'Intermodal / public transport':
            mask |= df['category'].str.contains('Intermodal|bus|tranv', case=False, na=False)
        elif layer == 'Urban core / tourism':
            mask |= df['category'].str.contains('Urban core|tourism|Centro|turismo', case=False, na=False)
        elif layer == 'Logistics / curb / port':
            mask |= df['category'].str.contains('logíst|curb|port|mercan|cruceros', case=False, na=False)
        elif layer == 'Airport / gateway':
            mask |= df['category'].str.contains('airport|gateway|aeroport', case=False, na=False)
    return df[mask] if mask.any() else df


def get_default_hotspot_for_scenario(scenario: str, hotspots: dict[str, Hotspot]) -> Optional[Hotspot]:
    mapping = {
        'corridor_congestion': 'Plaça de les Glòries Catalanes',
        'school_area_risk': 'Plaça de Catalunya / Ronda Universitat',
        'urban_logistics_saturation': 'Plaça Cerdà / Passeig de la Zona Franca',
        'gateway_access_stress': 'Aeropuerto Josep Tarradellas BCN-El Prat T1',
        "event_mobility": "Plaça d'Espanya",
    }
    return hotspots.get(mapping.get(scenario, ''))
