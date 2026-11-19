"""Entrada web del cliente móvil, en el mismo origen que la API del juego."""

from flask import Blueprint, render_template

from shared.domain.avatares import AVATARES_PREDETERMINADOS
from shared.firebase_config import configuracion_firebase_web


movil = Blueprint("movil", __name__)


@movil.get("/movil")
def inicio():
    # US30 comparte con escritorio el catálogo de US06. El móvil envía el ID del avatar elegido a /api/game/avatar.
    return render_template(
        "movil.html",
        firebase_config=configuracion_firebase_web(),
        avatares=AVATARES_PREDETERMINADOS,
    )
