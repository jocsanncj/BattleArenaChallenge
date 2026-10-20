# Battle Arena Challenge — alcance US-01 a US-05

Esta entrega implementa solamente las historias de cuenta US-01 a US-05 del enunciado:

1. Registro persistente con usuario y correo únicos, validación de los campos y contraseña de al menos 8 caracteres.
2. Verificación de correo con enlace de un solo uso y expiración de 24 horas. Una cuenta sin verificar no puede iniciar sesión.
3. Inicio de sesión con nombre de usuario o correo y contraseña.
4. Perfil con nombre, avatar no configurado (`null`), estado del correo, récord, estadísticas, logros, ranking e historial.
5. Recuperación con enlace de un solo uso que permite establecer una contraseña nueva y expira en 20 minutos.

No se implementan creación/búsqueda de partidas, arena, movimiento, hardware, ranking competitivo ni mecánicas posteriores. El perfil puede mostrar estadísticas e historial guardados, pero las cuentas nuevas muestran valores vacíos porque este alcance no registra resultados de partidas.

## Arquitectura y responsabilidades

- **Presentación:** `main.py`, `Window.py`, `Escenas.py` y `Boton.py`. Pygame maneja pantallas y entrada del jugador.
- **Cliente HTTP:** `SistemaUsuario.py`. Convierte acciones de la interfaz en solicitudes JSON a la API. El cliente no lee la base de datos ni valida por sí mismo la identidad.
- **API/servidor:** `servidor.py`. Despacha las rutas HTTP, serializa respuestas y protege el perfil con un token de sesión.
- **Servicios de aplicación:** `backend/services.py`. Implementa validaciones de registro y contraseña, autenticación, verificación y recuperación.
- **Persistencia:** `backend/repository.py`. Encapsula SQLite y la migración opcional de `DatosUser.json`.
- **Modelo de perfil:** `backend/models.py`. Define los datos que la API devuelve para cada jugador.
- **Despliegue:** `Dockerfile` y `compose.yaml`. El servidor se ejecuta en el contenedor; SQLite vive en un volumen persistente.

## Modelo de datos

La base de datos `usuarios.sqlite3` se guarda en `DATA_DIR` (en Docker, `/data`).

- `usuarios`: nombre único sin distinguir mayúsculas, correo único sin distinguir mayúsculas, sal y hash de contraseña, verificación, avatar y récord.
- `enlaces`: hash del token (no el token original), usuario, propósito y vencimiento. Se usa para enlaces de verificación y recuperación; cada enlace puede utilizarse una sola vez.
- `logros`: títulos asociados a jugadores.
- `historial_partidas`: oponente, resultado, puntuación y fecha para las partidas históricas mostradas en el perfil.

Las claves foráneas mantienen logros e historial asociados a una cuenta. La API calcula estadísticas y ranking a partir de los datos persistidos. Este alcance solo consulta los registros de partidas; la lógica de juego futura deberá añadir resultados al historial.

## Ejecutarlo paso a paso (una sola computadora)

**No necesitas dos computadoras para empezar.** La misma computadora puede ejecutar el servidor dentro de Docker y abrir el juego Pygame como cliente. Son dos programas diferentes: deja Docker ejecutando el servidor y abre el juego desde otra terminal. Una segunda computadora solo sirve para probar que otro equipo de la misma red puede conectarse al servidor. Esta entrega no incluye partidas multijugador.

Los pasos siguientes son para Windows 10/11 y PowerShell. Para macOS o Linux, consulta las notas al final.

### 1. Descargar el proyecto

Si ya tienes el proyecto abierto en VS Code, pasa al siguiente paso. Si no, descarga o clona el repositorio y abre la carpeta `BattleArenaChallenge` en VS Code. Comprueba que dentro de esa carpeta se vean `Dockerfile`, `compose.yaml`, `main.py` y `requirements.txt`. Los comandos de más abajo deben ejecutarse desde esa carpeta.

### 2. Instalar Docker Desktop

1. Descarga Docker Desktop desde la [página oficial de Docker](https://www.docker.com/products/docker-desktop/).
2. Ejecuta el instalador. En Windows, acepta la opción de usar WSL 2 si el instalador la ofrece. Si el instalador pide reiniciar, reinicia la computadora.
3. Abre Docker Desktop desde el menú Inicio y espera a que indique que Docker está iniciado.
4. Abre PowerShell o la terminal de VS Code y comprueba que estos comandos respondan:

   ```powershell
   docker --version
   docker compose version
   ```

   Si Windows dice que `docker` no se reconoce, abre Docker Desktop, espera a que termine de iniciar y vuelve a abrir la terminal. Si aún falla, reinicia Windows y consulta la instalación oficial.

Docker Compose ya viene incluido en Docker Desktop; no hace falta instalarlo por separado.

### 3. Instalar Python para el cliente Pygame

1. Instala Python 3.10 o posterior desde [python.org](https://www.python.org/downloads/). Durante la instalación en Windows, activa **Add Python to PATH** si aparece esa casilla.
2. Abre una terminal nueva y verifica:

   ```powershell
   py --version
   ```

   Debe mostrar Python 3.10 o una versión posterior. Si `py` no existe, intenta `python --version`.
3. En VS Code, abre **Terminal > New Terminal**. Comprueba que la terminal esté en la carpeta del proyecto. Si no, usa `cd` seguido de la ruta de la carpeta. Por ejemplo:

   ```powershell
   cd C:\Users\TuNombre\Documents\BattleArenaChallenge
   ```

4. Instala Pygame, que es la dependencia del cliente:

   ```powershell
   py -m pip install -r requirements.txt
   ```

   Si tu equipo usa `python` en vez de `py`, ejecuta `python -m pip install -r requirements.txt`.

### 4. Configurar el correo para verificar cuentas

El servidor puede arrancar sin configurar el correo, pero **no podrás completar el registro y el inicio de sesión de una cuenta nueva**: las cuentas necesitan verificar su correo y el servidor envía esa verificación por Gmail.

Para que se envíen los correos necesitas una cuenta Gmail y una **contraseña de aplicación** de Google (no es la contraseña normal de Gmail). Google requiere tener activada la verificación en dos pasos para crear una. Sigue las instrucciones oficiales de [contraseñas de aplicación de Google](https://support.google.com/accounts/answer/185833).

En VS Code, crea un archivo llamado exactamente `.env` en la carpeta del proyecto, al mismo nivel que `compose.yaml`. Puedes hacerlo con **File > New Text File**, pegar lo siguiente y guardarlo como `.env`:

```dotenv
GMAIL_ADDRESS=tu-cuenta@gmail.com
GMAIL_APP_PASSWORD=tu-contraseña-de-aplicacion
PUBLIC_BASE_URL=http://localhost:8000
```

Reemplaza los dos primeros valores por tu dirección y contraseña de aplicación. No agregues comillas. No compartas este archivo ni publiques sus valores. Para una prueba en la misma computadora, deja `PUBLIC_BASE_URL` como `http://localhost:8000`.

### 5. Iniciar el servidor

En la terminal de VS Code, todavía desde la carpeta del proyecto, ejecuta:

```powershell
docker compose up --build -d
```

La primera vez puede tardar varios minutos porque Docker descarga la imagen base y construye el servidor. Cuando termine, confirma que está en ejecución:

```powershell
docker compose ps
```

Debe aparecer un servicio llamado `servidor`. Después abre esta dirección en el navegador:

```text
http://localhost:8000/health
```

Debe aparecer `{"status": "ok"}`. Si no aparece, mira los mensajes del servidor con:

```powershell
docker compose logs servidor
```

Deja el contenedor ejecutándose mientras uses el cliente. El primer arranque puede importar cuentas antiguas desde `DatosUser.json` a la base persistente de Docker. No borres ese archivo hasta comprobar la migración.

### 6. Abrir el juego (cliente)

Abre una **segunda terminal** en VS Code. No cierres ni detengas el servidor. En PowerShell, desde la carpeta del proyecto, ejecuta:

```powershell
$env:BATTLE_ARENA_SERVER = "http://127.0.0.1:8000"
py main.py
```

Debe abrirse la ventana del juego. `127.0.0.1` significa “esta misma computadora”; por eso esta dirección sirve cuando el juego y Docker corren en el mismo equipo.

En la ventana puedes crear una cuenta, abrir el enlace que llegó al correo para verificarla y luego iniciar sesión. Si el mensaje no llega, revisa la carpeta de spam y los registros del servidor (`docker compose logs servidor`). También comprueba que `.env` tenga la dirección Gmail y la contraseña de aplicación correctas; después de cambiar `.env`, reinicia el servicio:

```powershell
docker compose up -d --force-recreate
```

Si intentaste crear la cuenta antes de configurar Gmail, puede que la cuenta ya se haya guardado pero permanezca sin verificar. Después de configurar el correo y reiniciar el servidor, usa **Reenviar enlace** en la ventana del juego; no intentes registrar de nuevo el mismo nombre o correo.

### 7. Apagarlo y volver a iniciarlo

Cuando termines, cierra la ventana del juego. En una terminal ejecuta:

```powershell
docker compose down
```

Esto detiene el servidor pero conserva las cuentas y los perfiles. La próxima vez inicia Docker Desktop y ejecuta desde la carpeta del proyecto:

```powershell
docker compose up -d
```

No ejecutes `docker compose down -v`: la opción `-v` elimina también el volumen donde se guardan las cuentas.

### Si luego quieres probar desde una segunda computadora

El servidor debe seguir ejecutándose en la computadora que lo aloja. Averigua su dirección IP local ejecutando `ipconfig` en PowerShell y buscando la dirección IPv4 del adaptador conectado a tu red (a menudo empieza por `192.168.`). En el `.env` del servidor cambia la URL a esa dirección, por ejemplo:

```dotenv
PUBLIC_BASE_URL=http://192.168.1.50:8000
```

Usa la IP real de tu computadora, no la del ejemplo, y reinicia el servidor con `docker compose up -d --force-recreate`. Si Windows Firewall pregunta si permites conexiones para Docker/Python en una red privada, permite el acceso en esa red. En la segunda computadora instala Python y las dependencias del paso 3, abre una terminal en la carpeta del proyecto y ejecuta:

```powershell
$env:BATTLE_ARENA_SERVER = "http://192.168.1.50:8000"
py main.py
```

De nuevo, sustituye la IP de ejemplo por la dirección real del servidor. Ambos equipos deben estar en la misma red local. No hace falta configurar el router para estas pruebas. El enlace de verificación del correo también debe usar la IP real para que se pueda abrir desde la otra computadora.

### Instrucciones para Linux Mint

Estos pasos son para Linux Mint con entorno gráfico. Puedes ejecutar servidor y juego en la misma computadora. En Linux Mint, ejecuta los comandos en la aplicación **Terminal**. Cuando un comando empiece por `sudo`, Linux te pedirá la contraseña de tu usuario; al escribirla no verás caracteres en pantalla, lo cual es normal.

#### 1. Identificar la base Ubuntu de Mint

Abre Terminal y ejecuta:

```bash
grep -E '^(VERSION_CODENAME|UBUNTU_CODENAME)=' /etc/os-release
```

Mint usa una base de Ubuntu. Docker necesita el nombre de esa base, que aparece en `UBUNTU_CODENAME` (por ejemplo, `noble`); no uses el nombre propio de Mint que aparece en `VERSION_CODENAME`.

#### 2. Instalar Docker Engine y Docker Compose

Los siguientes comandos configuran el repositorio oficial de Docker para Ubuntu y usan automáticamente `UBUNTU_CODENAME` de Linux Mint. No instales un paquete que use `VERSION_CODENAME` de Mint como suite del repositorio.

```bash
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Añade el repositorio y actualiza la lista de paquetes:

```bash
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
```

Instala Docker Engine, Compose y los complementos necesarios:

```bash
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Comprueba que Docker está activo y que Compose está instalado:

```bash
sudo systemctl status docker
sudo docker run hello-world
sudo docker compose version
```

El primer comando debe mostrar que el servicio está activo; `hello-world` debe terminar mostrando un mensaje de instalación correcta. Para salir de la vista de `systemctl status`, pulsa `q`.

En los siguientes pasos usaremos `sudo docker ...`. Así no necesitas cambiar los permisos de tu usuario. Existe la opción de agregarlo al grupo `docker`, pero Docker advierte que ese grupo da permisos equivalentes a administrador/root; no es necesario para seguir esta guía.

#### 3. Instalar Python y Pygame

Instala Python, el soporte para crear entornos virtuales y las herramientas necesarias:

```bash
sudo apt install python3 python3-venv python3-pip
```

En Terminal, ve a la carpeta del proyecto. Una forma fácil es abrir esa carpeta en el administrador de archivos, hacer clic derecho en un espacio vacío y elegir **Open in Terminal** (el texto puede variar). Comprueba que estás en la carpeta correcta:

```bash
ls
```

Debes ver `main.py`, `requirements.txt`, `Dockerfile` y `compose.yaml`. Crea un entorno aislado e instala Pygame:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

#### 4. Configurar el correo

El servidor puede iniciarse sin correo, pero no podrás verificar una cuenta nueva ni iniciar sesión con ella. Para probar el registro necesitas una cuenta Gmail y una contraseña de aplicación de Google (no la contraseña normal); consulta la [guía oficial de Google](https://support.google.com/accounts/answer/185833).

Crea en la carpeta del proyecto un archivo llamado `.env`, al mismo nivel que `compose.yaml`, con estos valores:

```dotenv
GMAIL_ADDRESS=tu-cuenta@gmail.com
GMAIL_APP_PASSWORD=tu-contraseña-de-aplicacion
PUBLIC_BASE_URL=http://localhost:8000
```

Reemplaza los dos primeros valores por los tuyos, sin comillas. No compartas ni publiques `.env`.

#### 5. Arrancar el servidor

Desde Terminal, dentro de la carpeta del proyecto, ejecuta:

```bash
sudo docker compose up --build -d
sudo docker compose ps
```

La primera vez puede tardar porque Docker debe descargar y construir la imagen. Comprueba el servidor en el navegador, abriendo `http://localhost:8000/health`. Debe responder `{"status": "ok"}`. Si no, mira los registros:

```bash
sudo docker compose logs servidor
```

Deja el servidor encendido mientras juegas.

#### 6. Arrancar el juego

Abre otra ventana de Terminal en la carpeta del proyecto y ejecuta:

```bash
BATTLE_ARENA_SERVER=http://127.0.0.1:8000 .venv/bin/python main.py
```

Debe abrirse la ventana de Pygame. En Linux, `127.0.0.1` se refiere a esta misma computadora. Usa una Terminal dentro de la sesión gráfica; Pygame necesita abrir una ventana y no funcionará en una consola sin escritorio gráfico.

#### 7. Apagar los programas

Cierra la ventana del juego. Luego detén el servidor:

```bash
sudo docker compose down
```

Esto conserva las cuentas guardadas. No uses `sudo docker compose down -v`, porque `-v` elimina también el volumen de datos.

La próxima vez, abre Docker (si no inició automáticamente) y ejecuta desde la carpeta del proyecto:

```bash
sudo docker compose up -d
BATTLE_ARENA_SERVER=http://127.0.0.1:8000 .venv/bin/python main.py
```

#### Si el puerto 8000 ya está ocupado

Si Docker informa que el puerto `8000` ya está en uso, otro programa está usando ese puerto. Cierra ese programa antes de volver a iniciar el servidor. Para detener un contenedor de este proyecto usa `sudo docker compose down`.

#### Si más adelante conectas otra computadora

Ambos equipos deben estar conectados a la misma red local. En la computadora servidor averigua su IP con:

```bash
hostname -I
```

Usa la dirección local que corresponda a tu red (por ejemplo, `192.168.1.50`). En `.env`, cambia `PUBLIC_BASE_URL` por `http://IP_DEL_SERVIDOR:8000`, reinicia con `sudo docker compose up -d --force-recreate` y permite el puerto 8000 en el firewall si está activo. En la segunda computadora instala Python, crea el entorno virtual e instala Pygame como arriba; luego abre el juego con:

```bash
BATTLE_ARENA_SERVER=http://IP_DEL_SERVIDOR:8000 .venv/bin/python main.py
```

Reemplaza `IP_DEL_SERVIDOR` por la IP real en ambos lugares. Para abrir el enlace de verificación desde el otro equipo, también debe usarse esa IP en `PUBLIC_BASE_URL`. No hace falta una segunda computadora para la prueba local, y esta entrega no implementa partidas multijugador.

Para otros derivados de Ubuntu o Debian, consulta las [instrucciones oficiales de Docker Engine](https://docs.docker.com/engine/install/). Para macOS, instala [Docker Desktop](https://www.docker.com/products/docker-desktop/); en Terminal instala Python 3 y usa `python3 -m pip install -r requirements.txt`, inicia el servidor con Docker Compose y ejecuta `BATTLE_ARENA_SERVER=http://127.0.0.1:8000 python3 main.py`.

## Pruebas y CI

Ejecuta las pruebas de US-01 a US-05 desde la raíz:

```bash
python -m unittest discover -s tests -v
```

Las pruebas usan una base SQLite temporal y sustituyen el envío SMTP, por lo que no mandan correos reales. `.github/workflows/ci.yml` ejecuta las pruebas y construye la imagen Docker al subir cambios o abrir un pull request hacia `main`.

## DoD y límites deliberados del alcance

La documentación del modelo, persistencia, pruebas positivas/negativas de cuenta y CI cubren los aspectos del DoD pertinentes a US-01–US-05. El DoD general del documento también incluye hardware físico, arena, dos avatares en juego y sincronización multijugador. No se implementan aquí porque pertenecen a funcionalidades posteriores y exceden el límite solicitado de US-01 a US-05; por tanto, esta entrega no afirma que el DoD global del videojuego esté completo.

El servidor de ejemplo usa HTTP sin cifrar y sesiones en memoria. Está destinado a pruebas en una red local de confianza, no a exponerlo a Internet. Un reinicio del contenedor invalida las sesiones activas, pero conserva cuentas, enlaces y datos de perfil.
