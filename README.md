# Battle Arena Challenge

Interfaz de escritorio hecha con Pygame. Firebase Authentication administra el registro, inicio de sesión, verificación del correo y recuperación de contraseña. Un servidor pequeño en Docker verifica los tokens de Firebase y guarda los perfiles del juego en un archivo JSON.

Esta entrega todavía no implementa creación/búsqueda de partidas ni una partida multijugador.

## Cómo se conecta cada parte

```text
Pygame (SistemaUsuario.py)
  ├─ Firebase Auth REST: registro, inicio de sesión, verificación y recuperación
  └─ servidor Docker (servidor.py): solicita/consulta el perfil JSON
       ├─ Firebase Admin: verifica el token antes de aceptar el perfil
       └─ JSONRepository: guarda el nombre, correo, récord y datos del juego
```

- **Firebase Auth** administra identidades y envía los correos de verificación y recuperación. No se usa Resend para esos correos.
- **`SistemaUsuario.py`** llama a la API REST de Firebase desde el cliente. La API key web es una clave pública de identificación del proyecto; no es la clave Admin.
- **`servidor.py`** ya no registra cuentas, comprueba contraseñas ni crea enlaces de correo. Solo ofrece `/health` y las operaciones de perfil.
- **`backend/repository.py`** persiste los perfiles de juego en `/data/usuarios.json`. No guarda ni valida las contraseñas de Firebase.
- **La clave JSON de Firebase Admin** es privada y solo se monta dentro del contenedor, en modo de solo lectura. Nunca debe incluirse en el cliente Pygame, `.env`, GitHub o la imagen Docker.

El inicio de sesión ahora requiere **correo electrónico y contraseña**; el nombre elegido durante el registro es el nombre público del perfil. Las cuentas guardadas anteriormente en el JSON propio no se convierten automáticamente en cuentas Firebase: los jugadores deberán registrarse en Firebase de nuevo. El archivo antiguo no se elimina.

## Preparar Firebase

1. En [Firebase Console](https://console.firebase.google.com/), abre el proyecto de la clave Admin.
2. En **Authentication > Sign-in method**, activa **Email/Password**.
3. En **Project settings > General**, copia el valor de **Web API Key**. Es el dato público que usa el cliente.
4. Mantén el archivo de cuenta de servicio que descargaste en la raíz del proyecto, con este nombre:

   ```text
   proyecto-modelado-dee24-firebase-adminsdk-fbsvc-1806a6701a.json
   ```

   Si el nombre del archivo es diferente, ajusta el lado izquierdo de la ruta montada en `compose.yaml`. No abras, pegues ni compartas el contenido de esa clave. El archivo está excluido de Git y del contexto Docker.
5. Crea o edita `.env` en la raíz y agrega estas variables. Si ya contiene otras claves, no las borres: añade o actualiza solo estas líneas.

   ```dotenv
   FIREBASE_API_KEY=pega_aqui_la_web_api_key
   BATTLE_ARENA_SERVER=http://127.0.0.1:8000
   ```

   La API key web no es una contraseña. No agregues la clave Admin ni `RESEND_API_KEY` al cliente ni a este ejemplo. El cliente carga `.env` al iniciar.

## Ejecutar en Linux Mint

Desde una terminal abierta en la carpeta del proyecto:

1. Comprueba que Docker y Compose estén instalados:

   ```bash
   docker --version
   docker compose version
   ```

   Si tu usuario necesita permisos para Docker, usa `sudo` delante de los comandos Docker.

2. Instala las dependencias de Python del proyecto:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

3. Construye e inicia el servidor:

   ```bash
   sudo docker compose up --build -d
   sudo docker compose ps
   ```

4. Comprueba el estado del servidor en el navegador, en `http://localhost:8000/health`. Debe responder `{"status": "ok"}`. Si algo falla:

   ```bash
   sudo docker compose logs servidor
   ```

5. En otra terminal, inicia Pygame:

   ```bash
   .venv/bin/python main.py
   ```

   Regístrate con correo y contraseña, abre el mensaje de Firebase y pulsa el enlace de verificación. Después vuelve al programa e inicia sesión usando el correo.

6. Al terminar, cierra Pygame y detén el servidor:

   ```bash
   sudo docker compose down
   ```

   Esto conserva `usuarios.json` en el volumen Docker. No uses `sudo docker compose down -v` salvo que quieras borrar también los datos del perfil.

El chequeo `/health` puede responder aunque Firebase Admin todavía no esté configurado. Para guardar o consultar un perfil, el contenedor necesita encontrar el archivo de cuenta de servicio y que corresponda al mismo proyecto Firebase que la API key web.

## Probar desde otra computadora de la red

El servidor Docker corre en una computadora y Pygame puede ejecutarse en esa y en otra computadora. En la computadora servidor, obtén su dirección local con:

```bash
hostname -I
```

En `.env` de cada cliente, cambia `BATTLE_ARENA_SERVER` por la IP local del servidor, por ejemplo:

```dotenv
BATTLE_ARENA_SERVER=http://192.168.1.50:8000
```

Recrea el contenedor si cambiaste su configuración:

```bash
sudo docker compose up -d --force-recreate
```

Permite el puerto 8000 en el firewall si está activo. Firebase Auth requiere Internet. Aunque las cuentas y perfiles se comparten, este proyecto todavía no coordina partidas entre jugadores.

## Pruebas

Las pruebas no acceden a Firebase ni envían correos reales; simulan las respuestas externas:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Documentación Doxygen

El archivo `Doxyfile` documenta el cliente, la interfaz, el servidor, el backend y las pruebas. En Linux Mint:

```bash
sudo apt install doxygen
doxygen Doxyfile
```

Abre `html/index.html` en el navegador. La carpeta `html/` está excluida de Git.
