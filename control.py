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