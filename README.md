# Battle Arena Challenge

Videojuego multijugador de escritorio hecho con Python y Pygame (CE-1105 Principios de Modelado en Ingeniería, TEC).

**Estado actual:** registro e inicio de sesión con Firebase y partida online para dos jugadores. El servidor valida los movimientos, mantiene los puntajes y determina el resultado; los clientes consultan el estado por HTTP.

---

## 1. Cómo funciona (en 30 segundos)

```text
Jugador ── Pygame (main.py, Escenas.py)
              │
              └─ ServicioAuth (SistemaUsuario.py)      <- casos de uso
                    ├─ FirebaseAuth ────────► Firebase Authentication
                    │   (ClientesHttp.py)       cuentas, contraseñas y correos de
                    │                           verificación / recuperación
                    └─ ClienteServidor ─────► Servidor (servidor.py, en Docker)
                        (ClientesHttp.py)       ├─ verifica la sesión con Firebase Admin
                                                ├─ guarda perfiles en SQLite (/data/juego.db)
                                                └─ controla sala, movimientos, puntajes y resultado
                                                    (us10.py, us15.py, us16.py)
                                                    └─ devuelve estados por HTTP; el cliente
                                                       muestra la arena y la celebración (us17.py)
```

- **Firebase Authentication** guarda las contraseñas y envía los correos de verificación y recuperación. Nuestro código nunca guarda contraseñas.
- **El servidor** corre en Docker y guarda lo propio del juego (nombre de usuario único, récord, historial, logros) en una base de datos **SQLite**.
- **El cliente** (Pygame) se ejecuta directamente en tu computadora, sin Docker.
- Para la partida, el cliente envía acciones HTTP (unirse, iniciar o moverse); no puede enviar el puntaje ni reemplazar el estado completo. El servidor valida cada paso y los dos clientes consultan el mismo estado.

Hay dos roles, y puedes cumplir los dos a la vez:

| Rol | Qué necesita |
|---|---|
| **Quien levanta el servidor** (una persona del equipo) | Docker, `.env` y `firebase-admin.json` |
| **Quien ejecuta el juego** (todos) | Python, `.env` y la dirección del servidor |

---

## 2. Requisitos

| | Windows 10/11 | Linux Mint |
|---|---|---|
| **Python 3.10 o superior** (se probó con 3.12) | [python.org](https://www.python.org/downloads/). Marca **"Add python.exe to PATH"** al instalar | `sudo apt update && sudo apt install -y python3 python3-venv python3-pip` |
| **Git** | [git-scm.com](https://git-scm.com/download/win) | `sudo apt install -y git` |
| **Docker** (solo si levantas el servidor) | [Docker Desktop](https://www.docker.com/products/docker-desktop/). Debe estar abierto y en estado "running" | [Guía oficial para Ubuntu](https://docs.docker.com/engine/install/ubuntu/) (Mint está basado en Ubuntu) |

Comprueba que todo quedó instalado:

```text
python --version        (en Linux: python3 --version)
git --version
docker --version
docker compose version
```

---

## 3. Archivos secretos (se entregan en persona)

Estos archivos **no están en el repositorio** y **nunca** deben subirse a Git ni pegarse en chats, issues o capturas de pantalla. Te los entrega en persona el integrante encargado del proyecto de Firebase.

**`.env`** (todos lo necesitan). Va en la carpeta raíz del proyecto, junto a `main.py`. Puedes copiar `.env.example` como base, pero necesitas los valores reales:

```dotenv
FIREBASE_API_KEY=pega_aqui_la_clave_que_te_dieron
BATTLE_ARENA_SERVER=http://127.0.0.1:8000
```

- `BATTLE_ARENA_SERVER` es la dirección del servidor. Si el servidor corre en **tu misma computadora**, déjalo como está. Si corre en **otra**, pon la IP de esa computadora (ver sección 6).

**`firebase-admin.json`** (solo quien levanta el servidor). También va en la raíz del proyecto, con ese nombre exacto.

Antes de hacer cualquier commit, revisa con `git status` que `.env` y `firebase-admin.json` **no** aparezcan. Si aparecen, agrégalos al `.gitignore`.

---

## 4. Preparar el proyecto (una sola vez)

Abre una terminal en la carpeta donde quieras guardar el proyecto.

### Windows (PowerShell)

```powershell
git clone https://github.com/jocsanncj/BattleArenaChallenge/tree/Prueba-revisar
cd ProyectoModelado

py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Después copia tu `.env` (y `firebase-admin.json` si levantas el servidor) a esta carpeta.

> Se llama a `.venv\Scripts\python.exe` directamente para evitar el error de "la ejecución de scripts está deshabilitada" de PowerShell. No hace falta activar el entorno virtual.

### Linux Mint

```bash
git clone <URL-DEL-REPOSITORIO>
cd ProyectoModelado

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Después copia tu `.env` (y `firebase-admin.json` si levantas el servidor) a esta carpeta.

---

## 5. Levantar el servidor (solo una persona del equipo)

Necesitas Docker abierto y, en la raíz del proyecto, `.env` y `firebase-admin.json`.

### Windows (PowerShell)

```powershell
docker compose up --build -d
docker compose ps
```

### Linux Mint

```bash
sudo docker compose up --build -d
sudo docker compose ps
```

Espera unos 15 segundos. En `ps` el estado debe decir **healthy**. Luego abre en el navegador:

**http://localhost:8000/health**

Debe responder `{"status": "ok"}`.

Notas:

- Usa siempre `--build` después de cambiar código del servidor, porque el código se copia dentro de la imagen.
- Si algo falla, mira el motivo con `docker compose logs servidor` (en Linux, con `sudo` delante).
- Que `/health` responda no garantiza que Firebase esté bien configurado; eso se comprueba al registrar un usuario.

Para apagarlo:

```text
docker compose down            (en Linux: sudo docker compose down)
```

> **Cuidado:** `docker compose down -v` borra también la base de datos con todos los perfiles. Úsalo solo cuando quieras empezar de cero.

---

## 6. Ejecutar el juego (cada integrante)

Con el servidor ya levantado (en tu computadora o en otra de la red). Desde la raíz del proyecto:

### Windows (PowerShell)

```powershell
.venv\Scripts\python.exe main.py
```

### Linux Mint

```bash
.venv/bin/python main.py
```

### Si el servidor está en otra computadora

No necesitas Docker en la tuya.

1. En la computadora del servidor, averigua su IP local:

   | Windows | Linux Mint |
   |---|---|
   | `ipconfig` (busca "Dirección IPv4") | `hostname -I` |

2. En el `.env` de cada cliente, cambia la dirección. Ejemplo:

   ```dotenv
   BATTLE_ARENA_SERVER=http://192.168.1.50:8000
   ```

3. En la computadora del servidor, permite el puerto 8000 en el firewall:

   - **Windows:** acepta el aviso del firewall para redes privadas, o ejecuta en PowerShell como administrador:
     ```powershell
     netsh advfirewall firewall add rule name="Battle Arena" dir=in action=allow protocol=TCP localport=8000
     ```
   - **Linux Mint** (solo si el firewall está activo): `sudo ufw allow 8000/tcp`

4. Las computadoras deben estar en la misma red, y todas necesitan Internet porque Firebase corre en la nube.

---

## 7. Qué puedes probar

1. **Crear cuenta:** nombre de usuario, correo, contraseña (mínimo 8 caracteres, con letras y números) y confirmación. No se permiten nombres ni correos repetidos.
2. **Verificar el correo:** te llega un enlace de Firebase (revisa también spam). Hasta que lo abras no puedes entrar al área de juego.
3. **Iniciar sesión** con el **nombre de usuario o con el correo**.
4. **Recuperar contraseña:** pide el enlace, abre la página de Firebase y define la nueva contraseña. El enlace expira.
5. **Perfil:** nombre, estado del correo, estadísticas, logros, ranking e historial.
6. **Partida online:** inicia sesión en dos computadoras, elige avatares distintos, entra a la sala e inicia cuando aparezcan ambos jugadores. En la arena, mueve tu personaje con **WASD** o las **flechas**. Cada movimiento válido suma un punto; el servidor comparte posiciones y puntajes. Al concluir, cada cliente abre su ventana de victoria.

La partida se actualiza mediante consultas HTTP periódicas, por lo que no requiere WebSockets ni abrir otro puerto. La sala y su configuración se conservan en el servidor; el estado activo de los movimientos y el temporizador reside en memoria del proceso servidor. Si se reinicia el contenedor durante una partida, esa partida activa se pierde y la sala se reinicia al siguiente acceso.

**Para repetir pruebas de registro** sin borrar nada, usa correos distintos. Con Gmail, `tucorreo+1@gmail.com`, `tucorreo+2@gmail.com`, etc. llegan a la misma bandeja.

---

## 8. Dónde viven los datos

| Dato | Dónde está | Cómo borrarlo |
|---|---|---|
| Correo, contraseña y estado "verificado" | **Firebase** (en la nube, compartido por todo el equipo) | Firebase Console → Authentication → Users → *Delete account* |
| Perfil, récord, historial | **SQLite** (`juego.db`) en el volumen de Docker `battle-arena-data` | `docker compose down -v` (borra todos los perfiles) |
| Avatar y sala de espera/configuración | Archivo `partida_online.json` dentro de `/data` en el servidor | No lo borres manualmente mientras haya usuarios conectados |
| Posiciones y puntajes de la partida activa | Memoria del proceso servidor | Se reinicia al detener/reiniciar el contenedor |

Si un correo ya existe en Firebase, el registro dirá que ya tiene una cuenta aunque hayas borrado la base de datos del servidor. Para repetir un registro con el mismo correo hay que borrar **ambos** lugares.

---

## 9. Pruebas automáticas

Las pruebas no usan Firebase ni envían correos reales. Se corren desde la raíz del proyecto:

```text
Windows:     .venv\Scripts\python.exe -m unittest discover -s tests -v
Linux Mint:  .venv/bin/python -m unittest discover -s tests -v
```

---

## 10. Estructura del proyecto

| Archivo o carpeta | Para qué sirve |
|---|---|
| `main.py`, `Window.py`, `Boton.py` | Arranque y base de la interfaz Pygame |
| `Escenas.py` | Pantallas del juego (bienvenida, registro, login, perfil...) |
| `SistemaUsuario.py` | Casos de uso de cuenta (`ServicioAuth`) |
| `ClientesHttp.py` | Conexión con Firebase y con el servidor |
| `servidor.py` | API del servidor |
| `us10.py`, `us15.py`, `us16.py` | Estado de arena, puntaje y reglas ejecutadas por el servidor |
| `us17.py` | Ventana de resultado que se abre en el cliente |
| `backend/repository.py` | Base de datos SQLite (tablas `jugadores`, `partidas`, `logros`) |
| `backend/jugador.py` | Clase `Jugador` (datos y estadísticas del jugador) |
| `tests/` | Pruebas automáticas |
| `Dockerfile`, `compose.yaml` | Contenedor del servidor |
| `Doxyfile` | Configuración de la documentación del código |

---

## 11. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `docker: command not found` o "Cannot connect to the Docker daemon" | Docker no está instalado o no está corriendo. En Windows abre Docker Desktop y espera a que diga "running". En Linux usa `sudo` |
| `docker compose ps` muestra `Restarting` | El servidor se cae al arrancar. Mira `docker compose logs servidor` |
| `ImportError` en los logs después de actualizar el código | La imagen quedó vieja. Reconstruye con `docker compose up --build -d` |
| `firebase-admin.json` aparece como **carpeta** | Docker la creó porque el archivo no existía cuando levantaste el servidor. Borra la carpeta, copia el archivo real y vuelve a levantar |
| El puerto 8000 ya está en uso | Otro programa lo ocupa. Apágalo, o apaga un servidor anterior con `docker compose down` |
| "Configura FIREBASE_API_KEY en el archivo .env" | Falta el `.env`, no está en la raíz o la variable está vacía |
| "No se pudo conectar con el servicio..." | El servidor no está levantado, `BATTLE_ARENA_SERVER` tiene una IP o puerto incorrecto, o el firewall bloquea el 8000 |
| "Ese correo ya tiene una cuenta" | Ese correo ya está registrado en Firebase. Bórralo en Firebase Console o usa otro |
| No llega el correo de verificación | Revisa spam. Usa "Reenviar enlace" en la pantalla de verificación |
| `No module named pygame` (o `dotenv`) | Las dependencias no se instalaron en el entorno virtual. Repite el `pip install` con el Python de `.venv` |
| Windows: `py` no se reconoce | Reinstala Python marcando "Add python.exe to PATH", o usa `python` en vez de `py` |
| Linux: `ensurepip is not available` | Falta `python3-venv`: `sudo apt install python3-venv` |

---

## 12. Flujo de trabajo con Git

- Ramas: `main` (estable) ← `develop` (integración) ← `feature/<nombre>` (cada tarea).
- Trabaja en tu rama `feature/...`, haz commits pequeños y abre un **Pull Request** hacia `develop`.
- Antes de abrir el Pull Request, corre las pruebas (sección 9).
- No hagas commit de `.env`, `firebase-admin.json` ni de la carpeta `data/`.

---

## 13. Documentación del código (opcional)

```text
Windows:     instala Doxygen desde doxygen.nl y ejecuta:  doxygen Doxyfile
Linux Mint:  sudo apt install doxygen  &&  doxygen Doxyfile
```

Abre `html/index.html` en el navegador. La carpeta `html/` no se sube a Git.

---

## Seguridad

- No subas `.env` ni `firebase-admin.json` a Git, a la imagen de Docker ni a un chat.
- La clave `FIREBASE_API_KEY` identifica el proyecto, pero no la compartas fuera del equipo.
- Si un archivo secreto se filtra, avisa de inmediato para generar una clave nueva en Firebase Console.