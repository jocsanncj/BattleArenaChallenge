"""Página local que inicia el acceso con Google desde el navegador del jugador."""

import secrets
import webbrowser
from concurrent.futures import Future
from dataclasses import dataclass, field
from threading import Event, Thread

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request
from werkzeug.serving import BaseWSGIServer, make_server

from shared.firebase_config import configuracion_firebase_web

from .service import Sesion, preparar_acceso_google


load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
_servidor: BaseWSGIServer | None = None


@dataclass
class IntentoGoogle:
    clave: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    cancelado: Event = field(default_factory=Event)
    resultado: Future[tuple[Sesion, dict]] = field(default_factory=Future, repr=False)


_intento_actual: IntentoGoogle | None = None
_MENSAJES_ERROR = {
    "auth/operation-not-allowed": "El proyecto de Firebase no permite el acceso con Google.",
    "auth/unauthorized-domain": "El dominio de acceso todavía no está autorizado en Firebase.",
    "auth/unauthorized-continue-uri": "El dominio de acceso todavía no está autorizado en Firebase.",
    "auth/popup-blocked": "El navegador bloqueó la ventana de acceso con Google.",
    "auth/network-request-failed": "No se pudo conectar con Firebase. Revisa la conexión.",
    "auth/account-exists-with-different-credential": "Este correo ya tiene una cuenta. Usa su método de acceso original.",
    "credencial-incompleta": "Google no devolvió una credencial para el juego.",
}


@app.get("/login/google")
def login_google():
    config = configuracion_firebase_web()
    if not config["apiKey"]:
        return "Configura FIREBASE_API_KEY en el archivo .env.", 503
    return render_template("google_login.html", firebase_config=config)


def _intento_validado() -> IntentoGoogle:
    """Vincula la respuesta del navegador con el intento abierto desde Pygame."""
    intento = _intento_actual
    if _servidor is None or intento is None:
        abort(409)
    origen = f"http://localhost:{_servidor.server_port}"
    if request.host_url.rstrip("/") != origen or request.headers.get("Origin") != origen:
        abort(403)
    clave = request.headers.get("X-Intento", "")
    if not clave.isascii() or not secrets.compare_digest(intento.clave, clave):
        abort(409)
    return intento


@app.post("/login/google/cancelar")
def cancelar_login_google():
    intento = _intento_validado()
    if intento.resultado.done():
        abort(409)
    intento.cancelado.set()
    return "", 204


@app.post("/login/google/fallar")
def fallar_login_google():
    intento = _intento_validado()
    if intento.cancelado.is_set() or intento.resultado.done():
        abort(409)
    datos = request.get_json(silent=True)
    codigo = datos.get("codigo") if isinstance(datos, dict) else None
    if not isinstance(codigo, str):
        abort(400)
    mensaje = _MENSAJES_ERROR.get(codigo, "No se pudo iniciar sesión con Google. Inténtalo de nuevo.")
    intento.resultado.set_exception(RuntimeError(mensaje))
    return jsonify(error=mensaje)


@app.post("/login/google/completar")
def completar_login_google():
    intento = _intento_validado()
    if intento.cancelado.is_set() or intento.resultado.done():
        abort(409)
    datos = request.get_json(silent=True)
    credencial = datos.get("accessToken") if isinstance(datos, dict) else None
    if not isinstance(credencial, str) or not credencial:
        abort(400)
    try:
        resultado = preparar_acceso_google(credencial)
    except (RuntimeError, OSError, ValueError) as error:
        mensaje = str(error)
        intento.resultado.set_exception(RuntimeError(mensaje))
        return jsonify(error=mensaje), 400
    # El jugador puede haber salido de la pantalla durante la consulta a Firebase.
    if intento is not _intento_actual:
        abort(409)
    intento.resultado.set_result(resultado)
    return "", 204


def descartar_login_google(intento: IntentoGoogle | None) -> None:
    global _intento_actual
    if intento is _intento_actual:
        _intento_actual = None


def abrir_login_google() -> IntentoGoogle | None:
    """Abre la página en el navegador sin bloquear el bucle de Pygame."""
    global _servidor, _intento_actual
    if _servidor is None:
        _servidor = make_server("127.0.0.1", 0, app)
        Thread(target=_servidor.serve_forever, daemon=True).start()
    intento = IntentoGoogle()
    _intento_actual = intento
    url = f"http://localhost:{_servidor.server_port}/login/google#{intento.clave}"
    if webbrowser.open_new_tab(url):
        return intento
    _intento_actual = None
    return None
