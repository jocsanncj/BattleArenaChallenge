"""API de perfiles de Battle Arena (Flask + SQLite + Firebase Auth)."""
import os
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


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))