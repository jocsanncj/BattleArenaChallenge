import os    #Para configurar variables de entorno antes de cargar pygame
import sys   #Para poder terminar el programa con un código de salida
import time  #Para hacer pausas pequeñas entre lecturas del control

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
 
#Le decimos a SDL (la librería que usa pygame por dentro) que NO abra una ventana de video.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
 
#Permite que el control siga enviando eventos aunque la ventana no tenga el foco.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
 
try:
    import pygame
except ImportError:
    print("Falta pygame. Instálalo con:  pip install pygame")
    sys.exit(1)  #Salimos con código 1 (indica que hubo un error)

ZONA_MUERTA = 0.10  # ignora ruido pequeño de los sticks


def info_control(joy):
    """Imprime la información básica de un control."""
    print("-" * 60)
    print(f"Nombre   : {joy.get_name()}")
    print(f"ID       : {joy.get_instance_id()}")
    try:
        print(f"GUID     : {joy.get_guid()}")
    except Exception:
        pass
    print(f"Ejes     : {joy.get_numaxes()}")
    print(f"Botones  : {joy.get_numbuttons()}")
    print(f"Cruceta  : {joy.get_numhats()}")
    try:
        nivel = joy.get_power_level()
        print(f"Energía  : {nivel}")
    except Exception:
        pass
    print("-" * 60)

def leer_estado(joy):
    """Devuelve una línea de texto con lo que está activo en el control."""
    partes = []

    botones = [i for i in range(joy.get_numbuttons()) if joy.get_button(i)]
    if botones:
        partes.append("Botones: " + ",".join(str(b) for b in botones))

    for i in range(joy.get_numaxes()):
        valor = joy.get_axis(i)
        if abs(valor) > ZONA_MUERTA:
            partes.append(f"Eje{i}={valor:+.2f}")

    for i in range(joy.get_numhats()):
        hat = joy.get_hat(i)
        if hat != (0, 0):
            partes.append(f"Hat{i}={hat}")

    return " | ".join(partes) if partes else "(sin actividad)"

