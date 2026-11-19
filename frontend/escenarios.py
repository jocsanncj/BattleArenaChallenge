"""Planos de US-23 y configuración que intercambia el cliente."""
import json
from dataclasses import dataclass
from pathlib import Path

from shared.data import ConfiguracionPartida
from shared.domain.arena import MapaArena

ARCHIVO = Path(__file__).resolve().parents[1] / "Media" / "escenarios.json"
MAPAS = tuple(MapaArena(item["nombre"], tuple(item["plano"]))
              for item in json.loads(ARCHIVO.read_text(encoding="utf-8")))


@dataclass
class ConfiguracionEscenario(ConfiguracionPartida):
    escenario: int = 0


def indice_mapa(cfg):
    indice = getattr(cfg, "escenario", 0)
    return indice if type(indice) is int and 0 <= indice < len(MAPAS) else 0
