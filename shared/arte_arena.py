"""Arte de la arena compartido por Pygame y por las imágenes del cliente web."""
from functools import lru_cache
import math
import random
import pygame

INK = (10, 16, 30)
# Piso, juntas, cara superior, cara sombreada, emisión.
PALETAS = (
    ((19, 40, 58), (28, 57, 75), (84, 153, 177), (37, 83, 111), (104, 242, 224)),
    ((51, 33, 40), (69, 44, 49), (166, 107, 80), (94, 53, 53), (255, 169, 85)),
    ((35, 30, 59), (51, 44, 78), (139, 105, 177), (75, 61, 113), (204, 161, 255)),
)
PERIODO = 20


def fase(inicial, segundos):
    return (inicial + int(max(0, segundos) // PERIODO)) % len(PALETAS)


def cristal(s, x, y, r, h, claro, sombra, luz):
    a, b, c, d = (x, y-h), (x+r, y-h//3), (x, y), (x-r, y-h//3)
    pygame.draw.polygon(s, sombra, [a, b, c, d])
    pygame.draw.polygon(s, claro, [a, c, d])
    pygame.draw.line(s, luz, a, d, 2)


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
    # En la imagen web, Canvas anima los arcos sobre el mismo tablero y cristal.
    if segundos is not None:
        for i in range(8):
            a = segundos*.7+i*math.pi/4
            pygame.draw.arc(s,luz,(x-r+5,y-r+5,2*r-10,2*r-10),a,a+.48,3)
    cristal(s,x,y+lado//2,lado//2, lado+4,claro,sombra,luz)
