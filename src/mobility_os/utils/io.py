from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Hotspot:
    name: str
    lat: float
    lon: float
    category: str
    streets: str
    why: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def resolve_project_root(start: Optional[Path] = None) -> Path:
    current = (start or Path(__file__).resolve()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / 'data').exists() or (candidate / 'app.py').exists():
            return candidate
    return Path.cwd()


def resolve_data_path(filename: str, explicit_path: Optional[str] = None) -> Path:
    candidates: List[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    project_root = resolve_project_root()
    candidates.extend([
        project_root / 'data' / filename,
        project_root / filename,
        Path.cwd() / 'data' / filename,
        Path.cwd() / filename,
    ])
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def load_hotspots_csv(explicit_path: Optional[str] = None) -> Dict[str, Hotspot]:
    path = resolve_data_path('barcelona_mobility_hotspots.csv', explicit_path)
    hotspots: Dict[str, Hotspot] = {}
    if not path.exists():
        return hotspots
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            hs = Hotspot(
                name=row['name'],
                lat=float(row['lat']),
                lon=float(row['lon']),
                category=row['category'],
                streets=row['streets'],
                why=row['why'],
            )
            hotspots[hs.name] = hs
    return hotspots
