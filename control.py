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

def main():
    pygame.init()
    pygame.joystick.init()

    controles = {}

    def registrar(indice):
        joy = pygame.joystick.Joystick(indice)
        joy.init()
        controles[joy.get_instance_id()] = joy
        print(f"\n[+] Control conectado: {joy.get_name()}")
        info_control(joy)

    cantidad = pygame.joystick.get_count()
    if cantidad == 0:
        print("No se detectó ningún control.")
        print("Revisa: cable USB (que sea de datos), otro puerto USB,")
        print("y que el control esté encendido / en el modo correcto.")
        print("Esperando a que conectes uno... (Ctrl+C para salir)\n")
    else:
        print(f"Controles detectados: {cantidad}")
        for i in range(cantidad):
            registrar(i)

    print("\nMueve sticks y presiona botones para probar. Ctrl+C para salir.\n")

    ultimo = {}
    try:
        while True:
            for evento in pygame.event.get():
                if evento.type == pygame.JOYDEVICEADDED:
                    registrar(evento.device_index)
                elif evento.type == pygame.JOYDEVICEREMOVED:
                    joy = controles.pop(evento.instance_id, None)
                    nombre = joy.get_name() if joy else "desconocido"
                    ultimo.pop(evento.instance_id, None)
                    print(f"\n[-] Control desconectado: {nombre}")

            for iid, joy in controles.items():
                estado = leer_estado(joy)
                if estado != ultimo.get(iid):
                    ultimo[iid] = estado
                    print(f"[{joy.get_name()}] {estado}")

            time.sleep(0.02)  # ~50 lecturas por segundo
    except KeyboardInterrupt:
        print("\nPrueba finalizada.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()