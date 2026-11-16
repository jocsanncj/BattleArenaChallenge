"""API de perfiles de Battle Arena (Flask + SQLite + Firebase Auth)."""
import os
import json
import hashlib
import threading
import time
from functools import wraps
from pathlib import Path
import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError
from flask import Flask, jsonify, request
from backend.repository import (DuplicateEmail, DuplicateUsername, RepositoryError,SQLiteRepository, UserNotFound)
from logica import ARENA_PREDETERMINADA
from us10 import MultiplayerArena
from us16 import GameRules

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
_GAME_ARENA = None
_GAME_USERS = {}
_GAME_PLAYER_IDS = {}
_MOVE_TIMES = {}

def _id_jugador(claims):
    """Convierte el UID de Firebase en un entero estable compatible con el modelo de juego."""
    return int.from_bytes(hashlib.sha256(claims["uid"].encode("utf-8")).digest()[:4], "big") & 0x7fffffff

def _player_id(claims):
    """Usa el identificador estable del modelo de sala sin exponer el UID de Firebase."""
    return str(_id_jugador(claims))

def _partida_vacia():
    return {
        "configuracion": {
            "modo_fin": "tiempo",
            "minutos_fin": 5,
            "puntos_fin": 20,
            "segundos_congelacion": 3,
        },
        "estado": "esperando",
        "iniciada_en": None,
        "jugadores": [],
    }

def _leer_estado_juego():
    if not _GAME_FILE.exists():
        return {"avatares": {}, "partida": _partida_vacia()}
    try:
        contenido = json.loads(_GAME_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("No se pudo leer el estado guardado de la partida.") from error
    if not isinstance(contenido, dict):
        raise RuntimeError("El estado guardado de la partida no tiene un formato válido.")
    contenido.setdefault("avatares", {})
    contenido.setdefault("partida", _partida_vacia())
    if not isinstance(contenido["partida"], dict):
        raise RuntimeError("El estado guardado de la sala no tiene un formato válido.")
    return contenido

def _guardar_estado_juego(estado):
    datos.mkdir(parents=True, exist_ok=True)
    temporal = _GAME_FILE.with_suffix(".tmp")
    temporal.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, _GAME_FILE)

def _validar_jugador(claims):
    if claims.get("email_verified") is not True:
        raise PermissionError("Verifica tu correo para jugar online.")
    jugador = repo.obtener(claims["uid"], True)
    return _id_jugador(claims), _player_id(claims), jugador.nombre

def _estado_arena():
    if _GAME_ARENA is None:
        return None
    estado = _GAME_ARENA.tick()
    jugadores = []
    for jugador in estado.get("players", []):
        jugador["user_id"] = _GAME_PLAYER_IDS[jugador["player_id"]]
        jugadores.append(jugador)
    estado["players"] = jugadores
    if estado.get("winner_id") is not None:
        estado["winner_user_id"] = _GAME_PLAYER_IDS.get(estado["winner_id"])
    return estado

def _iniciar_arena(partida):
    global _GAME_ARENA, _GAME_USERS, _GAME_PLAYER_IDS, _MOVE_TIMES
    jugadores = partida.get("jugadores", [])
    if len(jugadores) != 2:
        raise ValueError("Se necesitan exactamente dos jugadores para iniciar la partida.")
    configuracion = partida.get("configuracion", {})
    modo = configuracion.get("modo_fin")
    if modo not in {"tiempo", "puntos"}:
        raise ValueError("El modo de finalización de la partida no es válido.")
    reglas = GameRules(
        mode="time" if modo == "tiempo" else "points",
        duration_seconds=int(configuracion.get("minutos_fin", 5)) * 60,
        target_score=int(configuracion.get("puntos_fin", 20)),
    )
    arena = MultiplayerArena(lambda _estado: None, rules=reglas)
    _GAME_USERS, _GAME_PLAYER_IDS, _MOVE_TIMES = {}, {}, {}
    posiciones = ARENA_PREDETERMINADA.puntos_inicio()
    estado = _leer_estado_juego()
    for indice, jugador in enumerate(jugadores):
        user_id = str(jugador["id_usuario"])
        eleccion = estado["avatares"].get(user_id) or {}
        avatar_id = eleccion.get("valor", "avatar_1")
        if eleccion.get("tipo") == "personalizado":
            avatar_id = f"personalizado-{user_id}"
        player_id = user_id
        _GAME_USERS[user_id] = player_id
        _GAME_PLAYER_IDS[player_id] = int(user_id)
        x, y = posiciones[indice]
        arena.join_player(player_id, player_id, jugador["nombre_usuario"], avatar_id, x, y)
    arena.begin_match()
    _GAME_ARENA = arena

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
    if (not isinstance(eleccion, dict)
            or eleccion.get("tipo") not in ("predeterminado", "personalizado")
            or not isinstance(eleccion.get("valor"), str)):
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
    """Devuelve la sala y el estado de juego producido por el servidor."""
    _validar_jugador(claims)
    with _GAME_LOCK:
        estado_guardado = _leer_estado_juego()
        partida = estado_guardado["partida"]
        if _GAME_ARENA is None and partida.get("estado") == "jugando":
            partida = _partida_vacia()
            estado_guardado["partida"] = partida
            _guardar_estado_juego(estado_guardado)
        juego = _estado_arena()
        return {"partida": partida, "game": juego}

@app.post("/api/game/join")
@requiere_sesion
def unirse_partida_juego(claims):
    """Une al usuario autenticado a la sala; la identidad nunca se toma del cuerpo HTTP."""
    user_id, player_id, nombre = _validar_jugador(claims)
    with _GAME_LOCK:
        global _GAME_ARENA
        estado = _leer_estado_juego()
        partida = estado["partida"]
        if _GAME_ARENA is None and partida.get("estado") == "jugando":
            partida = _partida_vacia()
            estado["partida"] = partida
        juego = _estado_arena()
        if juego and juego["status"] == "finished":
            _GAME_ARENA = None
            partida = _partida_vacia()
            estado["partida"] = partida
        if _GAME_ARENA is not None:
            player = next((p for p in _GAME_ARENA.snapshot()["players"]
                           if p["player_id"] == player_id), None)
            if player and player["connected"]:
                return {"ok": True}
            if player:
                _GAME_ARENA.join_player(
                    player_id, player_id, nombre, player["avatar_id"],
                    player["x"], player["y"],
                )
                if _GAME_ARENA.has_two_players() and _GAME_ARENA.rules.paused:
                    _GAME_ARENA.begin_match()
                return {"ok": True}
            raise ValueError("La partida ya comenzó y no admite nuevos jugadores.")
        existente = next((j for j in partida["jugadores"] if j["id_usuario"] == user_id), None)
        if existente:
            return {"ok": True}
        if partida.get("estado") != "esperando":
            raise ValueError("La partida ya comenzó. Espere a que termine.")
        if len(partida["jugadores"]) >= 2:
            raise ValueError("La sala está llena; solo admite dos jugadores.")
        if any(j["nombre_usuario"].casefold() == nombre.casefold() for j in partida["jugadores"]):
            raise ValueError("Los jugadores deben tener nombres de usuario diferentes.")
        indice = len(partida["jugadores"])
        partida["jugadores"].append({
            "id_usuario": user_id,
            "nombre_usuario": nombre,
            "indice_inicio": indice,
        })
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.post("/api/game/leave")
@requiere_sesion
def salir_partida_juego(claims):
    """Retira al jugador autenticado; una desconexión durante la partida la pausa."""
    user_id, player_id, _ = _validar_jugador(claims)
    with _GAME_LOCK:
        global _GAME_ARENA
        estado = _leer_estado_juego()
        partida = estado["partida"]
        if _GAME_ARENA is not None:
            _GAME_ARENA.disconnect_player(player_id)
            jugadores = _GAME_ARENA.snapshot()["players"]
            if all(not jugador["connected"] for jugador in jugadores):
                _GAME_ARENA = None
                estado["partida"] = _partida_vacia()
                _guardar_estado_juego(estado)
            return {"ok": True}
        partida["jugadores"] = [j for j in partida["jugadores"] if j["id_usuario"] != user_id]
        if not partida["jugadores"]:
            partida["estado"], partida["iniciada_en"] = "esperando", None
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.put("/api/game/config")
@requiere_sesion
def guardar_configuracion_juego(claims):
    """Actualiza solo la configuración permitida de la sala, nunca el estado de juego."""
    user_id, _, _ = _validar_jugador(claims)
    configuracion = request.get_json(silent=True)
    if not isinstance(configuracion, dict):
        raise ValueError("La configuración de la partida no tiene un formato válido.")
    modo = configuracion.get("modo_fin")
    minutos = configuracion.get("minutos_fin")
    puntos = configuracion.get("puntos_fin")
    congelacion = configuracion.get("segundos_congelacion")
    if (not isinstance(modo, str) or modo not in {"tiempo", "puntos"}
            or type(minutos) is not int or not 1 <= minutos <= 60
            or type(puntos) is not int or not 1 <= puntos <= 10000
            or type(congelacion) is not int or not 1 <= congelacion <= 30):
        raise ValueError("Los valores de configuración de la partida no son válidos.")
    with _GAME_LOCK:
        estado = _leer_estado_juego()
        partida = estado["partida"]
        if partida.get("estado") != "esperando":
            raise ValueError("La partida ya comenzó: no se puede cambiar la configuración.")
        if not any(j["id_usuario"] == user_id for j in partida["jugadores"]):
            raise PermissionError("Únete a la sala para cambiar su configuración.")
        partida["configuracion"] = {
            "modo_fin": modo,
            "minutos_fin": minutos,
            "puntos_fin": puntos,
            "segundos_congelacion": congelacion,
        }
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.post("/api/game/start")
@requiere_sesion
def iniciar_partida_juego(claims):
    """Inicia una arena autoritativa con dos jugadores ya registrados en la sala."""
    user_id, _, _ = _validar_jugador(claims)
    with _GAME_LOCK:
        estado = _leer_estado_juego()
        partida = estado["partida"]
        if not any(j["id_usuario"] == user_id for j in partida["jugadores"]):
            raise PermissionError("Únete a la sala antes de iniciar la partida.")
        if partida.get("estado") != "esperando":
            raise ValueError("La partida ya comenzó.")
        if len(partida["jugadores"]) != 2:
            raise ValueError("Esperando jugador...")
        _iniciar_arena(partida)
        partida["estado"] = "jugando"
        partida["iniciada_en"] = time.time()
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.post("/api/game/move")
@requiere_sesion
def mover_jugador_juego(claims):
    """Valida y aplica un paso de movimiento en el servidor y solo allí suma puntos."""
    _, player_id, _ = _validar_jugador(claims)
    movimiento = request.get_json(silent=True)
    direccion = movimiento.get("direction") if isinstance(movimiento, dict) else None
    direcciones = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
    }
    if not isinstance(direccion, str) or direccion not in direcciones:
        raise ValueError("La dirección de movimiento no es válida.")
    with _GAME_LOCK:
        if _GAME_ARENA is None:
            raise ValueError("La partida todavía no ha comenzado.")
        estado = _GAME_ARENA.snapshot()
        jugador = next((j for j in estado["players"] if j["player_id"] == player_id), None)
        if jugador is None or not jugador["connected"]:
            raise PermissionError("No perteneces a esta partida.")
        if not estado["active"]:
            raise ValueError("La partida está en pausa o ya terminó.")
        ahora = time.monotonic()
        ultimo_movimiento = _MOVE_TIMES.get(player_id)
        if ultimo_movimiento is not None and ahora - ultimo_movimiento < 0.12:
            return {"ok": False, "state": _estado_arena()}
        dx, dy = direcciones[direccion]
        x, y = int(jugador["x"]) + dx, int(jugador["y"]) + dy
        if not ARENA_PREDETERMINADA.es_transitable(x, y):
            return {"ok": False, "state": _estado_arena()}
        if any(p["player_id"] != player_id and p["x"] == x and p["y"] == y
               for p in estado["players"]):
            return {"ok": False, "state": _estado_arena()}
        _GAME_ARENA.confirm_movement(player_id, x, y)
        _MOVE_TIMES[player_id] = ahora
        return {"ok": True, "state": _estado_arena()}

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
