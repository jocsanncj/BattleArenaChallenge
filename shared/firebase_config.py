"""Configuración pública de Firebase para los clientes del juego."""

import os


def configuracion_firebase_web() -> dict[str, str]:
    # /movil y la ventana de acceso de Pygame leen estos datos en el navegador.
    # El archivo de Firebase Admin se carga por separado en el servidor para validar los tokens.
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", "").strip(),
        "projectId": "proyecto-modelado-dee24",
        "authDomain": "proyecto-modelado-dee24.firebaseapp.com",
        "appId": "1:81412643021:web:ec67ac35f919ca462c7184",
    }
