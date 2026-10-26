# Battle Arena Challenge

Videojuego multijugador de escritorio hecho con Python y Pygame (CE-1105 Principios de Modelado en Ingeniería, TEC).

**Estado actual:** registro e inicio de sesión con Firebase y partida online para dos jugadores. El servidor valida los movimientos, mantiene los puntajes y determina el resultado; los clientes consultan el estado por HTTP. En la arena, el botón de acción del gamepad reproduce `Media/Efecto.mp3` como demostración de entrada física.

La documentación de arquitectura y los diagramas compatibles con Azure DevOps Wiki están en [docs/Arquitectura-Azure-Wiki.md](docs/Arquitectura-Azure-Wiki.md).

---

## 1. Cómo funciona (en 30 segundos)

```text
Jugador
  ├─ Teclado o gamepad opcional
  │    └─ Pygame/SDL (acciones.py) ──► Cliente Pygame
  └─ Cliente Pygame (main.py, Escenas.py, interfaz.py)
       ├─ ServicioAuth (SistemaUsuario.py)
       │    └─ FirebaseAuth (ClientesHttp.py) ──HTTPS──► Firebase Authentication
       └─ ClienteServidor (ClientesHttp.py) ──HTTP──► Servidor Flask en Docker
            ├─ valida tokens con Firebase Admin
            ├─ guarda perfiles en SQLite (/data/juego.db)
            └─ gestiona sala, movimientos, puntajes y resultado
                 (servidor.py, us10.py, us15.py, us16.py)
                 └─ devuelve el estado para que el cliente dibuje la partida
```

- **Firebase Authentication** guarda las contraseñas y envía los correos de verificación y recuperación. Nuestro código nunca guarda contraseñas.
- **El mando es opcional** y se conecta a la computadora del jugador, no al servidor. En la arena se puede alternar entre teclado y gamepad; el MSI FORCE GC30 V2 es el modelo de referencia y se leen la cruceta y la palanca izquierda.
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

La aplicación tiene dos partes: el **servidor**, que normalmente inicia una persona del equipo, y el **juego**, que abre cada jugador. El servidor debe estar encendido antes de crear una cuenta, iniciar sesión o jugar online.

| | Windows 10/11 | Linux Mint |
|---|---|---|
| **Python 3.10 o superior** (probado con 3.12) | [Descarga Python](https://www.python.org/downloads/) y marca **Add python.exe to PATH** durante la instalación. | `sudo apt update && sudo apt install -y python3 python3-venv python3-pip git` |
| **Git** | [Descarga Git](https://git-scm.com/download/win). | Incluido en el comando de instalación anterior. |
| **Docker** (solo en la computadora servidor) | [Docker Desktop](https://www.docker.com/products/docker-desktop/). Ábrelo y espera a que indique que está en funcionamiento. | Sigue la [guía oficial de Docker para Ubuntu](https://docs.docker.com/engine/install/ubuntu/). |
| **Mando** (opcional) | Conecta un gamepad compatible con Pygame/SDL. El MSI FORCE GC30 V2 se usa como referencia de prueba. | Igual; el sistema debe detectarlo como joystick/gamepad. |

Si Docker Desktop solicita instalar WSL, sigue las instrucciones de Docker y reinicia Windows si lo pide.

---

## 3. Preparar los archivos de configuración

El integrante encargado de Firebase debe entregar los valores y credenciales necesarios. **No publiques estos datos en GitHub, la wiki, capturas de pantalla ni chats.**

### `.env` (cada computadora que ejecuta el juego)

En la carpeta del proyecto —la misma que contiene `main.py`— crea un archivo llamado exactamente `.env`. En Windows, al guardarlo con el Bloc de notas selecciona **Tipo: Todos los archivos**, para que no termine llamándose `.env.txt`.

```dotenv
FIREBASE_API_KEY=PEGA_AQUI_LA_CLAVE_ENTREGADA
BATTLE_ARENA_SERVER=http://127.0.0.1:8000
```

Reemplaza `PEGA_AQUI_LA_CLAVE_ENTREGADA` por la API key que proporcionó el equipo de Firebase; no escribas el texto de ejemplo literalmente.

Si el servidor corre en otra computadora, cambia `127.0.0.1` por la IPv4 local del servidor. La dirección debe iniciar con `http://`, no `https://`.

### `firebase-admin.json` (solo computadora servidor)

La persona que inicia Docker debe copiar el archivo `firebase-admin.json` a la carpeta del proyecto, junto a `compose.yaml`. El archivo debe pertenecer al mismo proyecto Firebase que la API key de los clientes.

---

## 4. Descargar el proyecto (una vez en cada computadora)

### Windows (PowerShell)

1. Instala Python y Git usando los enlaces de la sección 2.
2. Busca **PowerShell** en el menú Inicio y ábrelo.
3. Escribe o copia estos comandos, uno por uno, pulsando Enter al final de cada línea:

```powershell
cd $HOME
git clone https://github.com/jocsanncj/BattleArenaChallenge.git
cd BattleArenaChallenge
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si `py` no se reconoce, instala Python de nuevo, asegúrate de marcar **Add python.exe to PATH** y abre otra ventana de PowerShell.

### Linux Mint

1. Abre la aplicación **Terminal**.
2. Ejecuta los comandos siguientes, uno por uno:

```bash
cd ~
git clone https://github.com/jocsanncj/BattleArenaChallenge.git
cd BattleArenaChallenge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

La instalación de dependencias requiere Internet y puede tardar unos minutos. Al terminar, copia el archivo `.env` a esta carpeta. Si este equipo ejecutará el servidor, copia también `firebase-admin.json`.

---

## 5. Iniciar el servidor (solo una persona)

Haz esta sección en la computadora que alojará la partida. Debe tener Docker y el archivo `firebase-admin.json` junto a `compose.yaml`.

### Windows

1. Abre **Docker Desktop** y espera a que indique que está funcionando.
2. Abre PowerShell.
3. Entra a la carpeta del proyecto. Si seguiste los pasos anteriores, ejecuta:

   ```powershell
   cd $HOME\BattleArenaChallenge
   ```

4. Inicia el servidor:

   ```powershell
   docker compose up --build -d
   ```

   La primera vez puede tardar varios minutos.

5. Comprueba que se inició:

   ```powershell
   docker compose ps
   ```

6. Abre el navegador en la computadora del servidor y visita `http://localhost:8000/health`. Debe aparecer `{"status":"ok"}`.

### Linux Mint

1. Abre Terminal y entra a la carpeta del proyecto:

   ```bash
   cd ~/BattleArenaChallenge
   ```

2. Inicia y comprueba el servidor:

   ```bash
   sudo docker compose up --build -d
   sudo docker compose ps
   ```

3. En un navegador visita `http://localhost:8000/health`. Debe aparecer `{"status":"ok"}`.

### Mientras juegan y al terminar

Deja encendida la computadora servidor y no detengas Docker mientras los demás estén jugando. Para revisar los registros:

```bash
docker compose logs servidor
```

En Linux Mint puede ser necesario escribir `sudo docker compose logs servidor`.

Para apagar el servidor al terminar:

```bash
docker compose down
```

En Linux Mint: `sudo docker compose down`.

No agregues `-v` al comando de apagado normal: `docker compose down -v` borra los datos persistentes.

---

## 6. Conectar computadoras de la misma red

Si el juego y el servidor están en la misma computadora, deja `BATTLE_ARENA_SERVER=http://127.0.0.1:8000`.

Si el servidor está en otra computadora:

1. Conecta ambas computadoras a la misma red local.
2. En la computadora del servidor, averigua su IPv4:
   - Windows: abre PowerShell, escribe `ipconfig` y busca **Dirección IPv4** del adaptador Ethernet o Wi-Fi conectado a la red. No uses `vEthernet`, WSL ni la IP interna de Docker.
   - Linux Mint: en Terminal ejecuta `hostname -I`.
3. En el `.env` del cliente, escribe la IP real del servidor, por ejemplo:

   ```dotenv
   BATTLE_ARENA_SERVER=http://192.168.1.50:8000
   ```

   `192.168.1.50` es solo un ejemplo. Usa la IP que encontraste y conserva `http://`.
4. En el navegador del cliente abre `http://IP-DEL-SERVIDOR:8000/health`, reemplazando el texto por la IP. Debe aparecer `{"status":"ok"}`.
5. Si no abre, permite el puerto TCP 8000 en el firewall privado del servidor. En Windows, una persona administradora puede abrir PowerShell como administrador y ejecutar:

   ```powershell
   netsh advfirewall firewall add rule name="Battle Arena" dir=in action=allow protocol=TCP localport=8000 profile=private
   ```

   En Linux Mint, si UFW está activo, ejecuta `sudo ufw allow 8000/tcp`.
6. Guarda `.env`. Cierra y vuelve a abrir el juego después de cambiar la dirección.

---

## 7. Abrir el juego, crear una cuenta e iniciar sesión

### Abrir el juego

Antes de abrirlo, confirma que el servidor está encendido.

- Windows: abre PowerShell, entra a la carpeta del proyecto y ejecuta:

  ```powershell
  cd $HOME\BattleArenaChallenge
  .venv\Scripts\python.exe main.py
  ```

- Linux Mint: abre Terminal y ejecuta:

  ```bash
  cd ~/BattleArenaChallenge
  .venv/bin/python main.py
  ```

Se abrirá la ventana del juego con las opciones **Iniciar sesión** y **Crear cuenta**.

### Crear una cuenta por primera vez

1. Selecciona **Crear cuenta**.
2. Escribe un nombre de usuario, tu correo y una contraseña de al menos 8 caracteres que incluya letras y números.
3. Escribe la contraseña otra vez en el campo de confirmación y pulsa **Crear cuenta**.
4. Abre el correo enviado por Firebase y pulsa el enlace de verificación. Revisa correo no deseado si no aparece.
5. Vuelve al juego e inicia sesión.

El correo y el nombre de usuario deben ser únicos.

### Iniciar sesión

1. En la pantalla inicial, selecciona **Iniciar sesión**.
2. Escribe el nombre de usuario o correo y la contraseña.
3. Pulsa **Entrar**. Si la cuenta está verificada, aparecerá el menú del juego.
4. Si el correo aún no está verificado, abre el enlace que llegó por correo o usa **Reenviar enlace**.
5. Si olvidaste la contraseña, selecciona **Recuperar contraseña**, escribe tu correo y sigue el enlace recibido.

Para ver la información de la cuenta, selecciona **Ver perfil**. Para salir de la cuenta, elige **Cerrar sesión**.

---

## 8. Jugar con teclado o mando

Para una partida online se necesitan dos jugadores, cada uno en una computadora conectada al mismo servidor.

1. En cada computadora, abre el juego e inicia sesión con una cuenta cuyo correo esté verificado.
2. Selecciona **Jugar online** y elige un avatar.
3. Espera a que ambos jugadores aparezcan en la sala.
4. Cuando estén listos, inicia la partida.
5. Al entrar en la arena, el **teclado** se usa de forma predeterminada:
   - Arriba: `W` o flecha arriba.
   - Abajo: `S` o flecha abajo.
   - Izquierda: `A` o flecha izquierda.
   - Derecha: `D` o flecha derecha.
6. Para usar un mando, conéctalo a la computadora donde está abierto el juego **antes de seleccionarlo**. En el panel de la arena, pulsa **Usar gamepad**. Usa la cruceta o la palanca izquierda para moverte.
7. Con el modo gamepad seleccionado, pulsa el botón de acción (índice SDL `0`, normalmente **A**) para reproducir `Media/Efecto.mp3`. Es una demostración de que el juego recibe una acción física; por ahora no activa una mecánica de juego.
8. El mensaje de confirmación muestra el nombre del mando detectado. Si el juego dice que no detecta un gamepad, vuelve a conectar el mando y pulsa **Usar gamepad** otra vez. El MSI FORCE GC30 V2 es el modelo de referencia; otros mandos pueden funcionar si el sistema los reconoce como gamepad.
9. Para regresar al teclado, pulsa **Usar teclado**. Si el mando se desconecta durante la partida, el juego vuelve automáticamente al teclado.

Cada movimiento válido lo procesa el servidor y puede sumar un punto. Los clientes comparten posiciones y puntajes; al terminar se muestra el resultado.

La partida se actualiza mediante consultas HTTP periódicas, por lo que no requiere WebSockets ni abrir otro puerto. La sala y su configuración se conservan en el servidor; el estado activo de los movimientos y el temporizador reside en memoria del proceso servidor. Si se reinicia el contenedor durante una partida, esa partida activa se pierde y la sala se reinicia al siguiente acceso.

**Para repetir pruebas de registro** sin borrar nada, usa correos distintos. Con Gmail, `tucorreo+1@gmail.com`, `tucorreo+2@gmail.com`, etc. llegan a la misma bandeja.

---

## 9. Dónde viven los datos

| Dato | Dónde está | Cómo borrarlo |
|---|---|---|
| Correo, contraseña y estado "verificado" | **Firebase** (en la nube, compartido por todo el equipo) | Firebase Console → Authentication → Users → *Delete account* |
| Perfil, récord, historial | **SQLite** (`juego.db`) en el volumen de Docker `battle-arena-data` | `docker compose down -v` (borra todos los perfiles) |
| Avatar y sala de espera/configuración | Archivo `partida_online.json` dentro de `/data` en el servidor | No lo borres manualmente mientras haya usuarios conectados |
| Posiciones y puntajes de la partida activa | Memoria del proceso servidor | Se reinicia al detener/reiniciar el contenedor |

Si un correo ya existe en Firebase, el registro dirá que ya tiene una cuenta aunque hayas borrado la base de datos del servidor. Para repetir un registro con el mismo correo hay que borrar **ambos** lugares.

---

## 10. Pruebas automáticas

Las pruebas no usan Firebase ni envían correos reales. Se corren desde la raíz del proyecto:

```text
Windows:     .venv\Scripts\python.exe -m unittest discover -s tests -v
Linux Mint:  .venv/bin/python -m unittest discover -s tests -v
```

---

## 11. Estructura del proyecto

| Archivo o carpeta | Para qué sirve |
|---|---|
| `main.py`, `Window.py`, `Boton.py` | Arranque y base de la interfaz Pygame |
| `Escenas.py` | Pantallas del juego (bienvenida, registro, login, perfil...) |
| `SistemaUsuario.py` | Casos de uso de cuenta (`ServicioAuth`) |
| `ClientesHttp.py` | Conexión con Firebase y con el servidor |
| `acciones.py` | Lectura de controles del teclado y gamepad |
| `Media/Efecto.mp3` | Sonido reproducido al pulsar el botón de acción del gamepad o la tecla `E` |
| `servidor.py` | API del servidor |
| `us10.py`, `us15.py`, `us16.py` | Estado de arena, puntaje y reglas ejecutadas por el servidor |
| `us17.py` | Ventana de resultado que se abre en el cliente |
| `backend/repository.py` | Base de datos SQLite (tablas `jugadores`, `partidas`, `logros`) |
| `backend/jugador.py` | Clase `Jugador` (datos y estadísticas del jugador) |
| `tests/` | Pruebas automáticas |
| `tests/test_gamepad_input.py` | Pruebas del teclado y la entrada del gamepad |
| `Dockerfile`, `compose.yaml` | Contenedor del servidor |
| `Doxyfile` | Configuración de la documentación del código |

---

## 12. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `docker: command not found` o "Cannot connect to the Docker daemon" | Docker no está instalado o no está corriendo. En Windows abre Docker Desktop y espera a que diga "running". En Linux usa `sudo` |
| `docker compose ps` muestra `Restarting` | El servidor se cae al arrancar. Mira `docker compose logs servidor` |
| `ImportError` en los logs después de actualizar el código | La imagen quedó vieja. Reconstruye con `docker compose up --build -d` |
| `firebase-admin.json` aparece como **carpeta** | Docker la creó porque el archivo no existía cuando levantaste el servidor. Borra la carpeta, copia el archivo real y vuelve a levantar |
| El puerto 8000 ya está en uso | Otro programa lo ocupa. Apágalo, o apaga un servidor anterior con `docker compose down` |
| "Configura FIREBASE_API_KEY en el archivo .env" | Falta el `.env`, no está en la raíz o la variable está vacía |
| "No se pudo conectar con el servicio..." | El servidor no está levantado, `BATTLE_ARENA_SERVER` tiene una IP o puerto incorrecto, o el firewall bloquea el 8000 |
| "No se detectó un gamepad" | Conecta el mando a la computadora donde está abierto el juego, comprueba que el sistema lo detecte y pulsa otra vez **Usar gamepad** dentro de la arena. Mientras tanto puedes usar el teclado |
| El mando se desconectó durante la partida | El juego vuelve al teclado; reconecta el mando y pulsa **Usar gamepad** para seleccionarlo de nuevo |
| "Ese correo ya tiene una cuenta" | Ese correo ya está registrado en Firebase. Bórralo en Firebase Console o usa otro |
| No llega el correo de verificación | Revisa spam. Usa "Reenviar enlace" en la pantalla de verificación |
| `No module named pygame` (o `dotenv`) | Las dependencias no se instalaron en el entorno virtual. Repite el `pip install` con el Python de `.venv` |
| Windows: `py` no se reconoce | Reinstala Python marcando "Add python.exe to PATH", o usa `python` en vez de `py` |
| Linux: `ensurepip is not available` | Falta `python3-venv`: `sudo apt install python3-venv` |

---

## 13. Flujo de trabajo con Git

- Ramas: `main` (estable) ← `develop` (integración) ← `feature/<nombre>` (cada tarea).
- Trabaja en tu rama `feature/...`, haz commits pequeños y abre un **Pull Request** hacia `develop`.
- Antes de abrir el Pull Request, corre las pruebas (sección 9).
- No hagas commit de `.env`, `firebase-admin.json` ni de la carpeta `data/`.

---

## 14. Documentación del código (opcional)

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