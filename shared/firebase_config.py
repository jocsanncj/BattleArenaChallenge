"""Configuración pública de Firebase para los clientes del juego."""

import os


def configuracion_firebase_web() -> dict[str, str]:
    # Las plantillas de /movil y del acceso de escritorio pasan este diccionario al navegador para inicializar
    # el SDK de Firebase en el mismo proyecto. apiKey se lee del entorno al preparar cada página.
    # El servidor verifica los tokens con su propia cuenta de servicio, que se carga en _firebase_app().
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", "").strip(),
        "projectId": "proyecto-modelado-dee24",
        "authDomain": "proyecto-modelado-dee24.firebaseapp.com",
        "appId": "1:81412643021:web:ec67ac35f919ca462c7184",
    }
