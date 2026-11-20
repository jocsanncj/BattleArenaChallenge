from dataclasses import dataclass
from shared.data import ConfiguracionPartida
from shared.escenarios import MAPAS

@dataclass
class ConfiguracionEscenario(ConfiguracionPartida):
    escenario: int = 0
    rotacion: bool = False


def indice_mapa(cfg):
    indice = getattr(cfg, "escenario", 0)
    return indice if type(indice) is int and 0 <= indice < len(MAPAS) else 0
