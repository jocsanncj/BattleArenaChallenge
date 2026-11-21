"""Arte vectorial de Battle Arena. Las superficies estáticas se dibujan una sola vez."""
from functools import lru_cache
import random
import pygame

from shared.arte_arena import INK, PALETAS, PERIODO, cristal, fase, reactor, tablero

PANEL = (21, 33, 51)
TEXT = (239, 246, 246)
MUTED = (166, 186, 198)
MINT = (101, 245, 204)
NOMBRES = ("Órbita polar", "Caldera solar", "Jardín prisma")


@lru_cache(maxsize=48)
def fuente(tam, negrita=False):
    return pygame.font.SysFont("Segoe UI,DejaVu Sans", tam, bold=negrita)


def rotulo(s, texto, xy, tam=14, color=TEXT, negrita=False, ancho=None):
    font = fuente(tam, negrita)
    texto = str(texto)
    if ancho and font.size(texto)[0] > ancho:
        while texto and font.size(texto + "…")[0] > ancho:
            texto = texto[:-1]
        texto += "…"
    s.blit(font.render(texto, True, color), xy)


@lru_cache(maxsize=8)
def fondo(size, portada=False):
    w,h = size
    s = pygame.Surface(size)
    for y in range(h):
        t = y/h
        pygame.draw.line(s, (int(13+7*t), int(22+16*t), int(39+12*t)), (0,y), (w,y))
    rng = random.Random(1105)
    for _ in range(160):
        x,y = rng.randrange(w), rng.randrange(h)
        pygame.draw.circle(s, rng.choice([(37,61,78),(57,86,101),(86,120,129)]), (x,y), 1)
    if portada:
        x,y = int(w*.75), int(h*.53)
        # Estación suspendida sobre un horizonte de montañas.
        for r in [158, 163, 202]:
            pygame.draw.circle(s, (34,61,78), (x,y-42), r, 1)
        for k in range(3):
            ridge = [(i,h-105+36*k-rng.randrange(25,100)) for i in range(-40,w+65,45)]
            pygame.draw.polygon(s, [(33,58,71),(25,45,60),(15,29,45)][k], ridge+[(w,h),(0,h)])
        for level,r in enumerate([155,137,124]):
            yy = y+38-level*14
            pts=[(x,yy-r//2),(x+r,yy),(x,yy+r//2),(x-r,yy)]
            pygame.draw.polygon(s,(26,54+level*8,70+level*8),pts)
            pygame.draw.lines(s,(63,114,126),True,pts,2)
        for dx,dy,scale in [(-73,4,16),(71,4,18),(2,37,13),(3,-29,12)]:
            cristal(s,x+dx,y+dy,scale,scale*2,(60,113,128),(40,74,101),MINT)
        pygame.draw.ellipse(s,(72,135,143),(x-52,y-18,104,38),3)
        cristal(s,x,y-22,36,102,(79,216,188),(39,125,150),(197,255,235))
        pygame.draw.ellipse(s,MINT,(x-54,y-90,108,23),2)
    return s


def boton(s, rect, texto, font, primario=False, mouse=None):
    hovered = rect.collidepoint(pygame.mouse.get_pos() if mouse is None else mouse)
    color = ((155,255,220) if hovered else MINT) if primario else ((45,68,84) if hovered else PANEL)
    pygame.draw.rect(s,color,rect,border_radius=8)
    if not primario:
        pygame.draw.rect(s,(73,104,120),rect,1,border_radius=8)
    if font.size(texto)[0] > rect.width-12:
        font = fuente(14)
    t = font.render(texto,True,INK if primario else TEXT)
    s.blit(t,t.get_rect(center=rect.center))


def lineas(s, texto, rect, color, tam=13):
    """Ajusta avisos a su área sin cubrir los controles ni la arena."""
    words = str(texto).split()
    lines = []
    for word in words:
        if lines and fuente(tam).size(lines[-1]+" "+word)[0] <= rect.width:
            lines[-1] += " "+word
        else:
            lines.append(word)
    alto = fuente(tam).get_linesize()
    limite = max(1,rect.height//alto)
    for i, line in enumerate(lines[:limite]):
        if i == limite-1 and len(lines)>limite:
            line += "…"
        rotulo(s,line,(rect.x,rect.y+i*alto),tam,color,ancho=rect.width)


@lru_cache(maxsize=12)
def guardian(tipo, tam):
    from pathlib import Path
    nombre = "perseguidor" if tipo == "perseguidor" else "vigilante"
    ruta = Path(__file__).resolve().parents[1] / "Media" / "guardianes" / (nombre+".png")
    return pygame.transform.smoothscale(pygame.image.load(str(ruta)), (tam, tam))


def barra_salud(superficie, entidad, x, y, ancho):
    actual, maxima = entidad.get("salud"), entidad.get("salud_maxima")
    pygame.draw.rect(superficie, (71,79,93), (x,y,ancho,4))
    if isinstance(actual,(int,float)) and isinstance(maxima,(int,float)) and maxima>0:
        largo = round(ancho * max(0,min(1,actual/maxima)))
        pygame.draw.rect(superficie,(102,226,159),(x,y,largo,4))
    else:
        for i in range(0,ancho-2,7):
            pygame.draw.line(superficie, (126,134,146), (x+i,y+3),(x+i+2,y))
