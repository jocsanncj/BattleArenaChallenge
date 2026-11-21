"""Entrada web del cliente móvil, en el mismo origen que la API del juego."""

from io import BytesIO
from pathlib import Path

from flask import Blueprint, abort, render_template, send_file, send_from_directory, url_for

from shared.domain.avatares import NOMBRES_PERSONAJES
from shared.escenarios import MAPAS
from shared.firebase_config import configuracion_firebase_web
from shared.musica import wav_celebracion


movil = Blueprint("movil", __name__)
MEDIA = Path(__file__).resolve().parents[1] / "Media"


@movil.get("/movil/avatares/<any(retratos,personajes):tipo>/<avatar_id>.png")
def imagen_avatar(tipo, avatar_id):
    if avatar_id not in NOMBRES_PERSONAJES:
        abort(404)
    return send_from_directory(MEDIA / tipo, f"{avatar_id}.png")


@movil.get("/movil/audio/arena.wav")
def musica_arena():
    return send_from_directory(MEDIA, "Orbital.wav")


@movil.get("/movil/audio/resultados.wav")
def musica_resultados():
    return send_file(BytesIO(wav_celebracion()), mimetype="audio/wav", conditional=True)


@movil.get("/movil")
def inicio():
    # US30 comparte con escritorio el catálogo de US06. El móvil envía el ID del avatar elegido a /api/game/avatar.
    return render_template(
        "movil.html",
        firebase_config=configuracion_firebase_web(),
        avatares=[
            {
                "id": avatar_id,
                "nombre": nombre,
                "retrato": url_for("movil.imagen_avatar", tipo="retratos", avatar_id=avatar_id),
                "personaje": url_for("movil.imagen_avatar", tipo="personajes", avatar_id=avatar_id),
            }
            for avatar_id, nombre in NOMBRES_PERSONAJES.items()
        ],
        escenarios=[mapa.nombre for mapa in MAPAS],
    )
