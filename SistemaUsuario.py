import smtplib
import json
import secrets
import hashlib
import getpass
import os
import hmac
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from usuario import Usuario
load_dotenv(Path(__file__).resolve().parent / ".env")
ARCHIVO_USUARIOS = Path(__file__).resolve().parent / "DatosUser.json"

def enviar_correo_smtp(correo_destino: str):
    remitente = "proyectomodelado4@gmail.com"
    password_aplicacion = os.getenv("GMAIL_APP_PASSWORD")
    if not password_aplicacion:
        print("Configura GMAIL_APP_PASSWORD en el archivo .env del proyecto.")
        return False
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = correo_destino
    msg['Subject'] = "Código de Verificación"
    codigo = f"{secrets.randbelow(1_000_000):06}"
    cuerpo = f"Hola, tu código de verificación es: {codigo}"
    msg.attach(MIMEText(cuerpo, 'plain'))
    etapa = "conectando por SMTP seguro"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as server:
            etapa = "autenticando la cuenta de Gmail"
            server.login(remitente, password_aplicacion)
            etapa = "enviando el correo"
            server.send_message(msg)
            etapa = "cerrando la conexión SMTP"
    except (smtplib.SMTPException, OSError) as e:
        print(f"Error al {etapa} ({type(e).__name__}): {e}")
        return False
    print(f"Correo enviado con éxito a {correo_destino}")
    while True:
        verificacion = input("Escribe el código que se envió: ").strip()
        if verificacion == codigo:
            return True
        print("Código incorrecto. Inténtalo de nuevo.")

def creacion_usuario():
    print("Bienvenido :D")
    while True:
        eleccion = int(input("Elige 1 para crear usuario o 2 para iniciar sesión: ").strip())
        if eleccion == 1:
            try:
                with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as archivo:
                    datos = json.load(archivo)
            except FileNotFoundError:
                datos = {"usuarios": {}}
            usuarios = datos.setdefault("usuarios", {})
            while True:
                nombre_user = input("Escribe tu nombre dentro del juego: ").strip()
                if not nombre_user:
                    print("El nombre no puede estar vacío.")
                    continue
                if nombre_user in usuarios:
                    print("Ese nombre ya existe. Elige otro.")
                    continue
                break
            while True:
                password = getpass.getpass("Escribe tu contraseña: ")
                confirmacion = getpass.getpass("Confirma tu contraseña: ")
                if password == confirmacion:
                    break
                print("Las contraseñas no coinciden. Inténtalo de nuevo.")
            salt = secrets.token_bytes(16)
            hash_password = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                600_000,
            ).hex()
            while True:
                correo_user = input("Escribe tu correo electrónico: ").strip()
                if not correo_user:
                    print("El correo no puede estar vacío.")
                    continue
                correo_normalizado = correo_user.casefold()
                correo_existe = any(
                    isinstance(registro, dict)
                    and isinstance(registro.get("email"), str)
                    and registro["email"].strip().casefold() == correo_normalizado
                    for registro in usuarios.values()
                )
                if correo_existe:
                    print("Ese correo ya está registrado. Escribe otro.")
                    continue
                break
            usuario = Usuario(nombre_user, salt.hex(), hash_password, correo_user)
            usuarios[usuario.name] = usuario.como_diccionario()
            with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as archivo:
                json.dump(datos, archivo, ensure_ascii=False, indent=4)
            print(f"Usuario {usuario.name} creado.")
            print("Para jugar debes verificar el correo")
            while True:
                ver_correo = input("¿Quieres verificarlo ahora? Escribe S o N: ").strip().upper()
                if ver_correo in ("S", "N"):
                    break
                print("Respuesta inválida. Escribe S o N.")
            if ver_correo == "S":
                if enviar_correo_smtp(usuario.email):
                    usuario.verificacion()
                    usuarios[usuario.name] = usuario.como_diccionario()
                    with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as archivo:
                        json.dump(datos, archivo, ensure_ascii=False, indent=4)
                    print("Correo verificado.")
                else:
                    print("No se pudo verificar el correo.")
            break
        elif eleccion == 2:
            inicio_sesion()
            return
        else:
            print("Número incorrecto")
            continue

def inicio_sesion():
    try:
        with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except FileNotFoundError:
        print("Todavía no hay usuarios registrados.")
        return
    usuarios = datos.get("usuarios", {})
    while True:
        nombre_login = input(
            "Escribe tu nombre de usuario (o deja vacío para volver): "
        ).strip()
        if not nombre_login:
            return
        registro = usuarios.get(nombre_login)
        if isinstance(registro, dict):
            break
        print("Usuario no encontrado. Inténtalo de nuevo.")
    while True:
        contador = 0
        while contador < 3:
            password = getpass.getpass("Escribe la contraseña: ")
            salt = bytes.fromhex(registro["salt"])
            hash_ingresado = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                600_000,
            ).hex()
            if hmac.compare_digest(hash_ingresado, registro["hash_password"]):
                print("Inicio de sesión correcto.")
                return
            contador += 1
            print(f"Contraseña incorrecta. Intentos: {contador}/3")
        while True:
            eleccion_password = input(
                "¿Quieres recuperar tu contraseña por correo? Escribe S o N: "
            ).strip().upper()
            if eleccion_password in ("S", "N"):
                break
            print("Opción inválida. Escribe S o N.")
        if eleccion_password == "N":
            print("Puedes volver a intentar la contraseña.")
            continue
        correo = registro.get("email")
        if not isinstance(correo, str) or not correo:
            print("La cuenta no tiene un correo válido para recuperación.")
            return
        if not enviar_correo_smtp(correo):
            print("No se pudo verificar el correo; la contraseña no fue modificada.")
            return
        while True:
            nueva_password = getpass.getpass("Escribe la nueva contraseña: ")
            confirmacion = getpass.getpass("Confirma la nueva contraseña: ")
            if nueva_password == confirmacion:
                break
            print("Las contraseñas no coinciden. Inténtalo de nuevo.")
        nuevo_salt = secrets.token_bytes(16)
        nuevo_hash = hashlib.pbkdf2_hmac(
            "sha256",
            nueva_password.encode("utf-8"),
            nuevo_salt,
            600_000,
        ).hex()
        registro["salt"] = nuevo_salt.hex()
        registro["hash_password"] = nuevo_hash
        with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=4)
        print("Contraseña restablecida. Ya puedes iniciar sesión con la nueva contraseña.")

if __name__ == "__main__":
    creacion_usuario()
