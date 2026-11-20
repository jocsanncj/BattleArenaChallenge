import json
from pathlib import Path
from shared.domain.arena import MapaArena

ARCHIVO = Path(__file__).resolve().parents[1] / "Media" / "escenarios.json"
MAPAS = tuple(MapaArena(item["nombre"], tuple(item["plano"]))
              for item in json.loads(ARCHIVO.read_text(encoding="utf-8")))


