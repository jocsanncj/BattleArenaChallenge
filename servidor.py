"""API de perfiles de Battle Arena (Flask + SQLite + Firebase Auth)."""
import os
import json
import hashlib
import threading
from functools import wraps
from pathlib import Path
import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError
from flask import Flask, jsonify, request
from backend.repository import (DuplicateEmail, DuplicateUsername, RepositoryError,SQLiteRepository, UserNotFound)

app = Flask(__name__)
datos = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
datos.mkdir(parents=True, exist_ok=True)
repo = SQLiteRepository(datos / "juego.db")
_lock = threading.Lock()


def _firebase_app():
    with _lock:
        try:
            return firebase_admin.get_app()
        except ValueError:
            ruta = os.getenv("FIREBASE_ADMIN_CREDENTIALS", "").strip()
            if not ruta:
                raise RuntimeError("Configura FIREBASE_ADMIN_CREDENTIALS en el servidor.")
            try:
                return firebase_admin.initialize_app(credentials.Certificate(ruta))
            except (OSError, ValueError, FirebaseError) as e:
                raise RuntimeError("No se pudo inicializar Firebase Admin.") from e


def requiere_sesion(f):
    """Valida el token Bearer y le pasa los claims a la ruta."""
    @wraps(f)
    def interior(*args, **kwargs):
        esquema, _, token = request.headers.get("Authorization", "").partition(" ")
        if esquema.casefold() != "bearer" or not token:
            raise PermissionError("Inicia sesión para consultar el perfil.")
        try:
            claims = auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
        except (FirebaseError, ValueError) as e:
            raise PermissionError("La sesión de Firebase no es válida.") from e
        if not isinstance(claims.get("uid"), str) or not isinstance(claims.get("email"), str):
            raise PermissionError("La sesión no incluye una identidad válida.")
        return f(claims, *args, **kwargs)
    return interior


# --- Errores: se declaran una vez, Flask elige el más específico ---
@app.errorhandler(PermissionError)
def _401(e): return jsonify(error=str(e)), 401

@app.errorhandler(ValueError)
def _400(e): return jsonify(error=str(e)), 400

@app.errorhandler(UserNotFound)
def _404(e): return jsonify(error=str(e)), 404

@app.errorhandler(DuplicateUsername)
@app.errorhandler(DuplicateEmail)
def _409(e): return jsonify(error=str(e)), 409

@app.errorhandler(RepositoryError)
def _500(e): return jsonify(error="No se pudo completar la operación."), 500

@app.errorhandler(RuntimeError)
def _503(e): return jsonify(error=str(e)), 503


# --- Rutas ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/disponible")
def disponible():
    return {"disponible": repo.nombre_disponible(request.args.get("nombre", "").strip())}

@app.get("/api/correo")
def correo():
    return {"correo": repo.correo_de(request.args.get("nombre", "").strip())}

@app.get("/api/profile")
@requiere_sesion
def leer_perfil(claims):
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para consultar el perfil.")
    return {"user": repo.obtener(claims["uid"], True).to_dict()}

@app.post("/api/profile")
@requiere_sesion
def guardar_perfil(claims):
    nombre = (request.get_json(silent=True) or {}).get("name")
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 40:
        raise ValueError("El nombre debe tener entre 1 y 40 caracteres.")
    repo.crear(claims["uid"], nombre.strip(), claims["email"])
    return {"user": repo.obtener(claims["uid"], claims["email_verified"]).to_dict()}

# CAMBIO ONLINE: estado compartido de juego en el volumen Docker (/data).
_GAME_FILE = datos / "partida_online.json"
_GAME_LOCK = threading.RLock()

def _id_jugador(claims):
    """Convierte el UID de Firebase en un entero estable compatible con el modelo de juego."""
    return int.from_bytes(hashlib.sha256(claims["uid"].encode("utf-8")).digest()[:4], "big") & 0x7fffffff

def _leer_estado_juego():
    if not _GAME_FILE.exists():
        return {"avatares": {}, "partida": {"configuracion": {"modo_fin": "tiempo", "minutos_fin": 5, "puntos_fin": 20, "segundos_congelacion": 3}, "estado": "esperando", "iniciada_en": None, "jugadores": []}}
    try:
        contenido = json.loads(_GAME_FILE.read_text(encoding="utf-8"))
        return contenido if isinstance(contenido, dict) else {"avatares": {}, "partida": {}}
    except (OSError, ValueError):
        return {"avatares": {}, "partida": {}}

def _guardar_estado_juego(estado):
    datos.mkdir(parents=True, exist_ok=True)
    temporal = _GAME_FILE.with_suffix(".tmp")
    temporal.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, _GAME_FILE)

@app.get("/api/game/avatar")
@requiere_sesion
def leer_avatar_juego(claims):
    """Devuelve el avatar guardado del jugador solicitado; requiere sesión verificada."""
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para jugar online.")
    jugador_id = request.args.get("id", type=int)
    if jugador_id is None:
        jugador_id = _id_jugador(claims)
    with _GAME_LOCK:
        avatar = _leer_estado_juego().get("avatares", {}).get(str(jugador_id))
    return {"avatar": avatar}

@app.put("/api/game/avatar")
@requiere_sesion
def guardar_avatar_juego(claims):
    """Guarda el avatar del usuario autenticado, sin permitir elegir el ID de otra cuenta."""
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para jugar online.")
    eleccion = request.get_json(silent=True) or {}
    if eleccion.get("tipo") not in ("predeterminado", "personalizado") or not isinstance(eleccion.get("valor"), str):
        raise ValueError("La elección de avatar no es válida.")
    if len(eleccion["valor"]) > 2_000_000:
        raise ValueError("La imagen del avatar es demasiado grande.")
    with _GAME_LOCK:
        estado = _leer_estado_juego()
        estado.setdefault("avatares", {})[str(_id_jugador(claims))] = {"tipo": eleccion["tipo"], "valor": eleccion["valor"]}
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.get("/api/game/state")
@requiere_sesion
def leer_partida_juego(claims):
    """Devuelve el estado común de la sala a los clientes autenticados."""
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para jugar online.")
    with _GAME_LOCK:
        return {"partida": _leer_estado_juego().get("partida", {})}

@app.put("/api/game/state")
@requiere_sesion
def guardar_partida_juego(claims):
    """Actualiza la sala compartida; valida la estructura antes de persistirla."""
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para jugar online.")
    partida = request.get_json(silent=True)
    if not isinstance(partida, dict) or not isinstance(partida.get("jugadores"), list) or not isinstance(partida.get("configuracion"), dict):
        raise ValueError("El estado de la partida no tiene un formato válido.")
    if partida.get("estado", "esperando") not in ("esperando", "jugando") or len(partida["jugadores"]) > 4:
        raise ValueError("El estado de la partida no es válido.")
    with _GAME_LOCK:
        estado = _leer_estado_juego()
        estado["partida"] = partida
        _guardar_estado_juego(estado)
    return {"ok": True}

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))

