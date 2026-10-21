# Importa el decorador para definir modelos de datos concisos.
from dataclasses import dataclass


# Marca el perfil como inmutable para evitar modificar accidentalmente la respuesta.
@dataclass(frozen=True)
## @brief Modelo inmutable con los datos visibles del perfil de jugador.
class PlayerProfile:
    ## @brief Nombre público de la cuenta.
    name: str
    ## @brief Dirección de correo guardada para la cuenta.
    email: str
    ## @brief Indica si se confirmó la dirección de correo.
    email_verified: bool
    ## @brief Ruta del avatar o None cuando no existe uno asignado.
    avatar: str | None
    ## @brief Puntuación máxima guardada del jugador.
    record: int
    ## @brief Cantidad total de partidas registradas.
    matches_played: int
    ## @brief Cantidad de partidas ganadas.
    wins: int
    ## @brief Cantidad de partidas perdidas.
    losses: int
    ## @brief Cantidad de partidas empatadas.
    draws: int
    ## @brief Posición competitiva o None si no hay puntuación clasificable.
    ranking: int | None
    ## @brief Títulos de logros guardados para el jugador.
    achievements: tuple[str, ...]
    ## @brief Registros históricos serializables de las partidas.
    match_history: tuple[dict[str, object], ...]
    ## @brief Convierte el perfil a la estructura JSON utilizada por la API.
    ## @return Diccionario con identidad, estadísticas y datos históricos.
    def to_dict(self) -> dict[str, object]:
        # Construye un nuevo diccionario para desacoplar la respuesta del modelo.
        return {
            # Expone el identificador legible de la cuenta.
            "name": self.name,
            # Expone el correo asociado al jugador.
            "email": self.email,
            # Mantiene el nombre de campo esperado por el cliente actual.
            "verificado": self.email_verified,
            # Envía None cuando el usuario todavía no tiene avatar.
            "avatar": self.avatar,
            # Incluye la mejor puntuación persistida.
            "record": self.record,
            # Agrupa los contadores de partidas bajo un objeto de estadísticas.
            "statistics": {
                "matches_played": self.matches_played,
                "wins": self.wins,
                "losses": self.losses,
                "draws": self.draws,
            },
            # Incluye la posición o None para cuentas sin clasificación.
            "ranking": self.ranking,
            # Convierte la tupla inmutable en lista compatible con JSON.
            "achievements": list(self.achievements),
            # Convierte también el historial a una lista para serializarlo.
            "match_history": list(self.match_history),
        }
