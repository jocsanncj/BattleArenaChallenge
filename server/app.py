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
from shared.domain import ARENA_PREDETERMINADA
from shared.game.arena import MultiplayerArena
from shared.game.rules import GameRules
from shared.game.obstacles import GestorObstaculos
from shared.game.guardians import GestorGuardianes
from shared.game.events import GestorEventosPartida

app = Flask(__name__)


class ForbiddenOperation(PermissionError):
    """Operación denegada a una sesión válida sin el permiso requerido."""


datos = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
datos.mkdir(parents=True, exist_ok=True)
repo = SQLiteRepository(datos / "juego.db")
_lock = threading.Lock()
_GAME_FIREBASE_UIDS = {}


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
@app.errorhandler(ForbiddenOperation)
def _403(e): return jsonify(error=str(e)), 403

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

@app.get("/api/ranking")
def obtener_ranking():
    return jsonify(ranking=repo.obtener_ranking())

# CAMBIO ONLINE: estado compartido de juego en el volumen Docker (/data).
_GAME_FILE = datos / "partida_online.json"
_GAME_LOCK = threading.RLock()
_GAME_ARENA = None
_GAME_OBSTACULOS = None
_GAME_GUARDIANES = None
_GAME_EVENTOS = None
_GAME_USERS = {}
_GAME_PLAYER_IDS = {}
_MOVE_TIMES = {}
_REACTOR = {"available_at": 0.0,"active": None,"events": set(),}

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

def _actualizar_reactor(estado, ahora):
    interaccion = _REACTOR["active"]
    if interaccion is None:
        return
    jugador = next(
        (
            p for p in estado.get("players", [])
            if p["player_id"] == interaccion["player_id"]
        ),
        None,
    )
    estado_temporal = (
        _GAME_OBSTACULOS.estado_jugador(interaccion["player_id"], ahora)
        if _GAME_OBSTACULOS is not None else {"estado": "normal"}
    )
    if (
        (_GAME_EVENTOS is not None and _GAME_EVENTOS.sobrecarga_activa(ahora))
        or estado.get("status") not in {"running", "overtime"}
        or not estado.get("active")
        or jugador is None
        or not jugador.get("connected")
        or estado_temporal.get("estado") in {"congelado", "inmovilizado"}
        or not ARENA_PREDETERMINADA.junto_al_reactor(
            int(jugador["x"]), int(jugador["y"])
        )
    ):
        _REACTOR["active"] = None
        return
    if ahora - interaccion["started_at"] < 1.5:
        return
    _GAME_ARENA.scoreboard.award_extraction(interaccion["player_id"])
    _REACTOR["active"] = None
    _REACTOR["available_at"] = ahora + 4.0

def _estado_reactor(ahora):
    if _GAME_EVENTOS is not None and _GAME_EVENTOS.sobrecarga_activa(ahora):
        return {"status": "sobrecargado", "remaining_seconds": 0.0}
    interaccion = _REACTOR["active"]
    if interaccion is not None:
        restante = max(0.0, 1.5 - (ahora - interaccion["started_at"]))
        return {
            "status": "ocupado",
            "remaining_seconds": round(restante, 2),
        }
    restante = max(0.0, _REACTOR["available_at"] - ahora)
    if restante > 0:
        return {
            "status": "recargando",
            "remaining_seconds": round(restante, 2),
        }
    return {"status": "disponible", "remaining_seconds": 0.0}

def _persistir_resultado_partida(estado):
    if estado.get("status") != "finished":
        return
    if _GAME_EVENTOS is not None:
        _GAME_EVENTOS.finalizar()
    participantes = []
    for jugador in estado.get("players", []):
        player_id = jugador["player_id"]
        uid = _GAME_FIREBASE_UIDS.get(player_id)
        if uid is None:
            raise RuntimeError("No se encontró la cuenta de un participante.")
        participantes.append({
            "uid": uid,
            "score": jugador["score"],
            "result": "victoria" if player_id == estado.get("winner_id") else "derrota",
        })
    repo.registrar_resultado_partida(
        estado["match_id"],
        participantes,
        duracion_segundos=int(estado.get("elapsed_seconds", 0)),
    )
    marcas = repo.obtener_marcas_partida(estado["match_id"])
    if len(marcas) != len(participantes):
        raise RuntimeError("No se consolidaron los resultados de todos los participantes.")
    for jugador in estado["players"]:
        uid = _GAME_FIREBASE_UIDS[jugador["player_id"]]
        jugador.update(marcas[uid])
    estado["duration_seconds"] = int(estado.get("elapsed_seconds", 0))
    estado["results_persisted"] = True

def _estado_arena():
    if _GAME_ARENA is None:
        return None
    ahora = time.monotonic()
    estado = _GAME_ARENA.tick(ahora)
    if estado.get("status") != "finished":
        if _GAME_EVENTOS is not None:
            if estado.get("paused"):
                _GAME_EVENTOS.pausar(ahora)
            else:
                _GAME_EVENTOS.reanudar(ahora)
                _GAME_EVENTOS.actualizar(
                    estado.get("players", []), ahora,
                    prorroga=estado.get("status") == "overtime",
                )
        if _GAME_OBSTACULOS is not None:
            if (
                _GAME_GUARDIANES is not None
                and estado.get("status") in {"running", "overtime"}
                and estado.get("active")
                and not estado.get("paused")
            ):
                estados_anteriores = {
                    j["player_id"]: _GAME_OBSTACULOS.estado_jugador(j["player_id"], ahora)
                    for j in estado.get("players", [])
                }
                _GAME_GUARDIANES.actualizar(estado.get("players", []), ahora)
                if _GAME_EVENTOS is not None:
                    for jugador in estado.get("players", []):
                        anterior = estados_anteriores.get(jugador["player_id"], {})
                        actual = _GAME_OBSTACULOS.estado_jugador(
                            jugador["player_id"], ahora
                        )
                        _GAME_EVENTOS.penalizar_por_guardian(
                            jugador["player_id"], anterior, actual,
                            _GAME_ARENA.scoreboard, ahora,
                        )
                estado = _GAME_ARENA.snapshot()
        _actualizar_reactor(estado, ahora)
        estado = _GAME_ARENA.tick(ahora)
    elif _GAME_EVENTOS is not None:
        _GAME_EVENTOS.finalizar()
    if _GAME_OBSTACULOS is not None:
        estado["obstaculos"] = _GAME_OBSTACULOS.estado_publico(ahora)
        estado["guardianes"] = (
            _GAME_GUARDIANES.estado_publico(estado.get("players", []), ahora)
            if _GAME_GUARDIANES is not None else []
        )
        for jugador in estado.get("players", []):
            estado_jugador = _GAME_OBSTACULOS.estado_jugador(jugador["player_id"], ahora)
            jugador["estado_temporal"] = estado_jugador["estado"]
            jugador["efecto_trampa"] = estado_jugador["efecto"]
            jugador["segundos_inmovilizado"] = estado_jugador["segundos_restantes"]
            jugador["segundos_inmunidad"] = estado_jugador["segundos_inmunidad"]
            jugador["inmune"] = estado_jugador["segundos_inmunidad"] > 0
            jugador["mensaje_obstaculo"] = estado_jugador["mensaje"]
    if _GAME_EVENTOS is not None:
        estado.update(_GAME_EVENTOS.estado_publico(ahora))
    estado["reactor"] = _estado_reactor(ahora)
    _persistir_resultado_partida(estado)
    jugadores = []
    for jugador in estado.get("players", []):
        jugador["user_id"] = _GAME_PLAYER_IDS[jugador["player_id"]]
        jugadores.append(jugador)
    estado["players"] = jugadores
    if estado.get("winner_id") is not None:
        estado["winner_user_id"] = _GAME_PLAYER_IDS.get(estado["winner_id"])
    return estado

def _iniciar_arena(partida):
    global _GAME_ARENA, _GAME_OBSTACULOS, _GAME_GUARDIANES, _GAME_EVENTOS, _GAME_USERS, _GAME_PLAYER_IDS, _MOVE_TIMES, _REACTOR
    jugadores = partida.get("jugadores", [])
    if not 2 <= len(jugadores) <= 3:
        raise ValueError("La partida requiere dos o tres jugadores.")
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
    _GAME_OBSTACULOS = GestorObstaculos(
        ARENA_PREDETERMINADA, ARENA_PREDETERMINADA.puntos_inicio()[:len(jugadores)],
        segundos_inmovilizacion=configuracion.get("segundos_congelacion", 3),
    )
    _GAME_GUARDIANES = GestorGuardianes(
        ARENA_PREDETERMINADA, _GAME_OBSTACULOS,
        segundos_congelacion=configuracion.get("segundos_congelacion", 3),
    )
    _GAME_EVENTOS = GestorEventosPartida(
        ARENA_PREDETERMINADA, _GAME_OBSTACULOS, _GAME_GUARDIANES
    )
    _REACTOR = {"available_at": 0.0,"active": None,"events": set(),}
    posiciones = ARENA_PREDETERMINADA.puntos_inicio()[:3]
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
    _GAME_EVENTOS.iniciar(
        time.monotonic(), reglas.duration_seconds,
        modo="puntos" if modo == "puntos" else "tiempo",
    )

@app.post("/api/game/reactor")
@requiere_sesion
def interactuar_con_reactor(claims):
    _, player_id, _ = _validar_jugador(claims)
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError("La solicitud de interacción no es válida.")
    accion = datos.get("action")
    event_id = datos.get("event_id")
    if accion not in {"start", "stop"}:
        raise ValueError("La acción del reactor no es válida.")
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 100:
        raise ValueError("El identificador de interacción no es válido.")
    event_id = event_id.strip()
    with _GAME_LOCK:
        if _GAME_ARENA is None:
            raise ValueError("La partida todavía no ha comenzado.")
        estado = _estado_arena()
        if accion == "stop":
            activa = _REACTOR["active"]
            if (
                activa is not None
                and activa["player_id"] == player_id
                and activa["event_id"] == event_id
            ):
                _REACTOR["active"] = None
            return {"ok": True, "state": estado}
        if estado is None or estado.get("status") not in {"running", "overtime"}:
            raise ValueError("La partida no está activa.")
        if _GAME_EVENTOS is not None and _GAME_EVENTOS.sobrecarga_activa():
            raise ValueError("El reactor está desactivado por una sobrecarga.")
        jugador = next((p for p in estado.get("players", [])if p["player_id"] == player_id and p.get("connected")),None,)
        if jugador is None:
            raise PermissionError("No perteneces a esta partida.")
        if accion == "start" and _GAME_OBSTACULOS is not None:
            estado_temporal = _GAME_OBSTACULOS.estado_jugador(player_id, time.monotonic())
            if estado_temporal.get("estado") in {"congelado", "inmovilizado"}:
                raise ValueError(
                    "No puedes extraer energía mientras estás "
                    + ("congelado." if estado_temporal["estado"] == "congelado" else "inmovilizado.")
                )
        clave_evento = (player_id, event_id)
        if clave_evento in _REACTOR["events"]:
            return {"ok": True, "duplicate": True, "state": estado}
        if not ARENA_PREDETERMINADA.junto_al_reactor(int(jugador["x"]), int(jugador["y"])):
            raise ValueError("Acércate a una casilla junto al reactor.")
        if _REACTOR["active"] is not None:
            raise ValueError("Otro jugador está extrayendo energía del reactor.")
        ahora = time.monotonic()
        if ahora < _REACTOR["available_at"]:
            restante = round(_REACTOR["available_at"] - ahora, 1)
            raise ValueError(f"El reactor está recargando. Inténtalo en {restante} s.")
        _REACTOR["events"].add(clave_evento)
        _REACTOR["active"] = {
            "player_id": player_id,
            "event_id": event_id,
            "started_at": ahora,
        }
        return {"ok": True, "state": _estado_arena()}

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
        _GAME_FIREBASE_UIDS[player_id] = claims["uid"]
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
                    if _GAME_EVENTOS is not None:
                        _GAME_EVENTOS.reanudar()
                return {"ok": True}
            raise ValueError("La partida ya comenzó y no admite nuevos jugadores.")
        existente = next((j for j in partida["jugadores"] if j["id_usuario"] == user_id), None)
        if existente:
            return {"ok": True}
        if partida.get("estado") != "esperando":
            raise ValueError("La partida ya comenzó. Espere a que termine.")
        if len(partida["jugadores"]) >= 3:
            raise ValueError("La sala está llena; solo admite tres jugadores.")
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
            if _GAME_EVENTOS is not None:
                _GAME_EVENTOS.pausar()
            snapshot = _GAME_ARENA.snapshot()
            _persistir_resultado_partida(snapshot)
            jugadores = snapshot["players"]
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
        jugadores = partida.get("jugadores", [])
        if not any(j["id_usuario"] == user_id for j in partida["jugadores"]):
            raise PermissionError("Únete a la sala para cambiar su configuración.")
        if jugadores[0]["id_usuario"] != user_id:
            raise ForbiddenOperation("Solo el creador de la sala puede cambiar la configuración.")
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
        if len(partida["jugadores"]) < 2:
            raise ValueError("Esperando al menos dos jugadores...")
        if len(partida["jugadores"]) > 3:
            raise ValueError("La partida admite como máximo tres jugadores.")
        _iniciar_arena(partida)
        partida["estado"] = "jugando"
        partida["iniciada_en"] = time.time()
        _guardar_estado_juego(estado)
    return {"ok": True}

@app.post("/api/game/move")
@requiere_sesion
def mover_jugador_juego(claims):
    """Valida y aplica un paso de movimiento sin otorgar puntos por caminar."""
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
        if _GAME_OBSTACULOS is not None and _GAME_OBSTACULOS.jugador_inmovil(player_id, ahora):
            detalle = _GAME_OBSTACULOS.estado_jugador(player_id, ahora)
            return {"ok": False, "error": detalle["mensaje"], "state": _estado_arena()}
        ultimo_movimiento = _MOVE_TIMES.get(player_id)
        if ultimo_movimiento is not None and ahora - ultimo_movimiento < 0.12:
            return {"ok": False, "state": _estado_arena()}
        dx, dy = direcciones[direccion]
        x, y = int(jugador["x"]) + dx, int(jugador["y"]) + dy
        if _GAME_OBSTACULOS is not None:
            movimiento_valido, motivo = _GAME_OBSTACULOS.validar_movimiento(player_id, x, y, ahora)
            if not movimiento_valido:
                return {"ok": False, "error": motivo, "state": _estado_arena()}
        elif not ARENA_PREDETERMINADA.es_transitable(x, y):
            return {"ok": False, "error": "No puedes atravesar esa barrera.", "state": _estado_arena()}
        if any(p["player_id"] != player_id and p["x"] == x and p["y"] == y
               for p in estado["players"]):
            return {"ok": False, "error": "Otro jugador ocupa esa casilla.", "state": _estado_arena()}
        if _GAME_GUARDIANES is not None and (x, y) in _GAME_GUARDIANES.posiciones():
            return {"ok": False, "error": "Un guardián ocupa esa casilla.", "state": _estado_arena()}
        _GAME_ARENA.confirm_movement(player_id, x, y)
        if _GAME_OBSTACULOS is not None:
            ubicaciones_ocupadas = {
                (int(jugador_actual["x"]), int(jugador_actual["y"]))
                for jugador_actual in estado["players"]
                if jugador_actual["player_id"] != player_id
            }
            ubicaciones_ocupadas.add((x, y))
            _GAME_OBSTACULOS.activar_trampa(
                player_id, x, y, ahora, ubicaciones_ocupadas
            )
        if _GAME_EVENTOS is not None:
            jugador_actual = next(
                (p for p in _GAME_ARENA.snapshot()["players"]
                 if p["player_id"] == player_id), None
            )
            if jugador_actual is not None:
                puntos_extra = _GAME_EVENTOS.recoger_energia(jugador_actual, ahora)
                if puntos_extra:
                    _GAME_ARENA.scoreboard.add_points(player_id, puntos_extra)
        _MOVE_TIMES[player_id] = ahora
        return {"ok": True, "state": _estado_arena()}

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
