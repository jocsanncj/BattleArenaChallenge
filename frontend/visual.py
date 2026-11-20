"""Arte vectorial de Battle Arena. Las superficies estáticas se dibujan una sola vez."""
from functools import lru_cache
import math
import random
import pygame

INK = (10, 16, 30)
PANEL = (21, 33, 51)
TEXT = (239, 246, 246)
MUTED = (166, 186, 198)
MINT = (101, 245, 204)
NOMBRES = ("Órbita polar", "Caldera solar", "Jardín prisma")
# Piso, juntas, cara superior, cara sombreada, emisión.
PALETAS = (
    ((19, 40, 58), (28, 57, 75), (84, 153, 177), (37, 83, 111), (104, 242, 224)),
    ((51, 33, 40), (69, 44, 49), (166, 107, 80), (94, 53, 53), (255, 169, 85)),
    ((35, 30, 59), (51, 44, 78), (139, 105, 177), (75, 61, 113), (204, 161, 255)),
)
PERIODO = 20


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


def fase(inicial, segundos):
    return (inicial + int(max(0, segundos) // PERIODO)) % len(PALETAS)


def cristal(s, x, y, r, h, claro, sombra, luz):
    a, b, c, d = (x, y-h), (x+r, y-h//3), (x, y), (x-r, y-h//3)
    pygame.draw.polygon(s, sombra, [a, b, c, d])
    pygame.draw.polygon(s, claro, [a, c, d])
    pygame.draw.line(s, luz, a, d, 2)


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


@lru_cache(maxsize=12)
def tablero(mapa, tema, lado):
    piso, junta, claro, sombra, luz = PALETAS[tema]
    s = pygame.Surface((mapa.columnas*lado, mapa.filas*lado))
    s.fill(piso)
    rng = random.Random(tema+23)
    # Relieves a bajo contraste debajo de la cuadrícula jugable.
    w,h = s.get_size()
    for i in range(25):
        curva = []
        for x in range(-12,w+15,10):
            onda = 20*math.sin(x/97 + i*.15) + 9*math.cos(x/46+i*.2)
            y = i*29 - 90 + onda + (x*.15 if tema==0 else -x*.14)
            curva.append((x, int(y)))
        color = tuple(min(255, k+4+(i%3)*2) for k in piso)
        if tema==0:
            pygame.draw.lines(s,color,False,curva, 4 if i%4==0 else 1)
        elif tema==1:
            falla = [(x,y+rng.randrange(-7,8)) for x,y in curva]
            pygame.draw.lines(s,(74,44,46),False,falla,3)
            pygame.draw.lines(s,(95,54,47),False,falla,1)
        else:
            pygame.draw.lines(s,color,False,curva,2)
            for x,y in curva[2::7]:
                pygame.draw.polygon(s,(49,45,74), [(x,y),(x+5,y-9),(x+11,y-12),(x+8,y-4)])
    for f in range(mapa.filas):
        for c in range(mapa.columnas):
            x,y = c*lado,f*lado
            r = pygame.Rect(x,y,lado,lado)
            tipo = mapa.casilla_en(c,f).value
            pygame.draw.rect(s,junta,r,1)
            if tipo == "#":
                pygame.draw.rect(s,sombra,r.inflate(-2,-2),border_radius=4)
                pygame.draw.line(s,claro,(x+5,y+4),(x+lado-6,y+4),2)
                pygame.draw.line(s,piso,(x+6,y+lado-6),(x+lado-6,y+lado-6),3)
            elif tipo == "X":
                mid = lado//2
                if tema == 0:
                    cristal(s,x+mid,y+lado-2,mid-2,lado-4,claro,sombra,luz)
                elif tema == 1:
                    pygame.draw.rect(s,sombra,r.inflate(-3,-3),border_radius=6)
                    for i in (8,15,22):
                        pygame.draw.line(s,luz,(x+7,y+i+3),(x+lado-7,y+i-2),2)
                else:
                    for dx,dy,rad in [(10,17,8),(23,19,9),(16,10,8)]:
                        cristal(s,x+dx,y+dy+7,rad,rad*2,claro,sombra,luz)
            elif tipo == "R":
                pygame.draw.rect(s,sombra,r.inflate(-2,-2))
            elif rng.randrange(4)==0:
                px,py=x+8,y+lado-8
                if tema==1:
                    pygame.draw.lines(s,junta,False,[(px,py),(px+6,py-4),(px+10,py-3)])
                else:
                    pygame.draw.circle(s,junta,(px,py),2)
    for i,(c,f) in enumerate(mapa.puntos_inicio()):
        pygame.draw.circle(s, [(89,172,246),(241,158,107),(138,207,157),(205,157,231)][i%4],
                           (c*lado+lado//2,f*lado+lado//2),lado//2-5,2)
    return s


def reactor(s, mapa, tema, lado, segundos):
    cx,cy = mapa.centro_reactor()
    x,y = int((cx+.5)*lado),int((cy+.5)*lado)
    _,_,claro,sombra,luz = PALETAS[tema]
    r = int(lado*1.34)
    pygame.draw.circle(s,INK,(x,y),r)
    pygame.draw.circle(s,claro,(x,y),r,2)
    for i in range(8):
        a = segundos*.7+i*math.pi/4
        pygame.draw.arc(s,luz,(x-r+5,y-r+5,2*r-10,2*r-10),a,a+.48,3)
    cristal(s,x,y+lado//2,lado//2, lado+4,claro,sombra,luz)


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
