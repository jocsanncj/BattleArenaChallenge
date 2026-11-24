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


# La URL selecciona retratos para la ficha o personajes para la arena. El ID identifica el mismo PNG que
# usa el escritorio. Si el navegador pide un personaje desconocido, Flask responde con 404.
@movil.get("/movil/avatares/<any(retratos,personajes):tipo>/<avatar_id>.png")
def imagen_avatar(tipo, avatar_id):
    if avatar_id not in NOMBRES_PERSONAJES:
        abort(404)
    return send_from_directory(MEDIA / tipo, f"{avatar_id}.png")


# El reproductor del móvil solicita esta URL al entrar en la arena. Flask sirve Orbital.wav desde Media
# para que el navegador pueda reproducir la misma pista que el escritorio.
@movil.get("/movil/audio/arena.wav")
def musica_arena():
    return send_from_directory(MEDIA, "Orbital.wav")


# Al mostrar el podio, el reproductor pide esta URL. wav_celebracion prepara los bytes de la melodía
# compartida y send_file los entrega como audio/wav desde memoria.
@movil.get("/movil/audio/resultados.wav")
def musica_resultados():
    return send_file(BytesIO(wav_celebracion()), mimetype="audio/wav", conditional=True)


# GET /movil prepara el HTML que abre el teléfono. Pasa la configuración pública a Firebase y convierte
# el catálogo de personajes y mapas de escritorio en opciones y rutas que puede usar el navegador.
@movil.get("/movil")
def inicio():
    # La plantilla muestra el nombre y el retrato. Al guardar un avatar del catálogo, US30 envía
    # a /api/game/avatar el ID de US06 que también identifica al personaje dentro de la arena.
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
