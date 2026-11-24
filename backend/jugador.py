## @brief Representa una cuenta de usuario del modelo legado en memoria.
from dataclasses import dataclass, field

@dataclass
class Jugador:
    uid: str
    nombre: str
    correo: str
    correo_verificado: bool = False
    avatar: str | None = None
    record: int = 0
    ranking: int | None = None
    partidas: list = field(default_factory=list)  # historial
    logros: list = field(default_factory=list)
    ## @brief US-04 y US-28: cuenta victorias, derrotas o empates del historial.
    def _contar(self, resultado):
        return sum(
            p.get("result", p.get("resultado")) == resultado
            for p in self.partidas
        )
    ## @brief US-04, US-27 y US-28: convierte perfil, ranking e historial a la API pública.
    def to_dict(self):
        return {
            "name": self.nombre, "email": self.correo,
            "verificado": self.correo_verificado, "avatar": self.avatar,
            "record": self.record,
            "statistics": {"matches_played": len(self.partidas),
                        "wins": self._contar("victoria"),
                        "losses": self._contar("derrota"),
                        "draws": self._contar("empate"),
                        "points_accumulated": sum(
                            partida.get("score", partida.get("puntaje", 0))
                            for partida in self.partidas
                        )},
            "ranking": self.ranking, "achievements": self.logros,
            "match_history": self.partidas,
        }