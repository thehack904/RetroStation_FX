"""Original, transparent seasonal corner illustrations for Holiday Broadcast.

The drawing is cached per holiday, corner and program variant. No filesystem
decoding, network calls, or frame-by-frame randomness occurs in the hot path.
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from math import cos, sin, pi
from random import Random

from PIL import Image, ImageDraw


SIZE = (360, 240)
# Draw against a larger internal surface so leaves, fir needles, fireworks
# and pumpkins can extend naturally beyond the old 360×240 source boundary.
# Then fit the *entire* illustration into the established, upload-compatible
# 360×240 transparent artwork contract. This is geometry, not opacity fading.
SOURCE_MARGIN = (90, 90)
ART_MARGIN = (12, 10)


class _TranslatedDraw:
    """Translate drawing primitives onto the overscan source surface.

    The historic holiday artwork coordinates target a 360×240 canvas and
    sometimes extend beyond it. Translating before drawing retains those
    clipped-off shapes without changing their original composition.
    """

    def __init__(self, draw, dx, dy):
        self.draw = draw
        self.dx = dx
        self.dy = dy

    def _points(self, xy):
        # Pillow accepts either an (x0, y0, x1, y1) bounding rectangle or
        # a sequence of (x, y) coordinates for freeform paths.
        if len(xy) == 4 and all(isinstance(v, (int, float)) for v in xy):
            x0, y0, x1, y1 = xy
            return (x0 + self.dx, y0 + self.dy,
                    x1 + self.dx, y1 + self.dy)
        return [(x + self.dx, y + self.dy) for x, y in xy]

    def line(self, xy, **kwargs):
        return self.draw.line(self._points(xy), **kwargs)

    def polygon(self, xy, **kwargs):
        return self.draw.polygon(self._points(xy), **kwargs)

    def ellipse(self, xy, **kwargs):
        return self.draw.ellipse(self._points(xy), **kwargs)

    def pieslice(self, xy, start, end, **kwargs):
        return self.draw.pieslice(self._points(xy), start, end, **kwargs)

    def arc(self, xy, start, end, **kwargs):
        return self.draw.arc(self._points(xy), start, end, **kwargs)

    def rectangle(self, xy, **kwargs):
        return self.draw.rectangle(self._points(xy), **kwargs)


def _fit_complete_artwork(source):
    """Fit all drawn pixels inside a padded, transparent 360×240 source."""
    bounds = source.getchannel("A").getbbox()
    if not bounds:
        return Image.new("RGBA", SIZE, (0, 0, 0, 0))
    art = source.crop(bounds)
    usable_w = SIZE[0] - ART_MARGIN[0] * 2
    usable_h = SIZE[1] - ART_MARGIN[1] * 2
    scale = min(usable_w / art.width, usable_h / art.height)
    dims = (max(1, round(art.width * scale)),
            max(1, round(art.height * scale)))
    art = art.resize(dims, Image.Resampling.LANCZOS)
    output = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    # Keep the bottom decoration against the lower edge of the illustrated
    # panel, but preserve transparent bleed on *every* side.
    x = (SIZE[0] - art.width) // 2
    y = SIZE[1] - ART_MARGIN[1] - art.height
    output.alpha_composite(art, (x, y))
    return output



def _point(x, y, angle, radius):
    return (x + cos(angle) * radius, y + sin(angle) * radius)


def _stroke(draw, points, fill, width=2):
    draw.line(points, fill=fill, width=width, joint="curve")


def _maple(draw, x, y, radius, angle, palette):
    """Multi-lobed serrated maple leaf with a gold central vein."""
    radial = (
        (0.00, 1.0), (0.18, .40), (.42, .66), (.38, .24),
        (.70, .40), (.56, .10), (.90, .14), (.60, -.09),
        (.67, -.39), (.35, -.22), (.36, -.69), (.13, -.40),
        (0, -.80), (-.13, -.40), (-.36, -.69), (-.35, -.22),
        (-.67, -.39), (-.60, -.09), (-.90, .14), (-.56, .10),
        (-.70, .40), (-.38, .24), (-.42, .66), (-.18, .40),
    )
    points = []
    for xx, yy in radial:
        dx, dy = xx * radius, yy * radius
        points.append((round(x + cos(angle) * dx - sin(angle) * dy),
                       round(y + sin(angle) * dx + cos(angle) * dy)))
    draw.polygon(points, fill=palette[0], outline=palette[1], width=2)
    tip = (x + sin(angle) * radius * .8,
           y - cos(angle) * radius * .8)
    _stroke(draw, [(x, y + radius * .5), tip], palette[2], 2)
    for side in (-1, 1):
        for t in (.26, .53):
            xx = x + sin(angle) * radius * (.5-t)
            yy = y - cos(angle) * radius * (.5-t)
            _stroke(draw, [(xx, yy), (xx + side * radius*.3,
                                     yy - radius*.16)], palette[2], 1)


def _pumpkin(draw, x, y, width, height, warm=True):
    for i in (2, 1, 0, -1, -2):
        offset = i * width * .145
        box = (x + offset-width*.31, y-height*.53,
               x + offset+width*.31, y+height*.47)
        palette = (
            (237, 116, 34, 255), (213, 89, 25, 255), (255, 164, 50, 255),
            (223, 100, 26, 255), (176, 67, 23, 255)
        )
        draw.ellipse(box, fill=palette[abs(i)], outline=(116, 48, 20, 215), width=2)
    _stroke(draw, [(x, y-height*.47), (x+width*.02, y-height*.78),
                   (x+width*.12, y-height*.84)], (95, 88, 45, 255), max(3,round(width*.07)))
    draw.ellipse((x-width*.2,y-height*.37,x-width*.11,y-height*.22),
                 fill=(255, 207, 113, 190))


def _acorn(draw,x,y,scale):
    draw.ellipse((x-scale*.45,y-scale*.15,x+scale*.45,y+scale*.72),
                 fill=(163,87,45,255),outline=(90,55,33,255),width=2)
    draw.pieslice((x-scale*.55,y-scale*.35,x+scale*.55,y+scale*.24),
                  180,360,fill=(101,62,33,255))
    for k in range(5):
        _stroke(draw,[(x-scale*.43+k*scale*.22,y-scale*.16),
                      (x-scale*.22+k*scale*.18,y+scale*.11)],
                (190,129,65,175),1)
    _stroke(draw,[(x,y-scale*.3),(x+scale*.14,y-scale*.52)],(97,74,45,255),3)


def _pine(draw, x, y, x2, y2, color, seed):
    rnd = Random(seed)
    _stroke(draw,[(x,y),(x2,y2)],(104,77,48,255),4)
    dx,dy=x2-x,y2-y
    length=(dx*dx+dy*dy)**.5
    if length < 2: return
    ux,uy=dx/length,dy/length
    nx,ny=-uy,ux
    for i in range(7,round(length),6):
        t=i/length
        sx=x+dx*t
        sy=y+dy*t
        spread=min(28, 7+length*.13) * (1-t*.6)
        for side in (-1,1):
            jitter=rnd.uniform(-.22,.22)
            ex=sx + ux*spread*.65 + nx*spread*(side+jitter)
            ey=sy + uy*spread*.65 + ny*spread*(side+jitter)
            mix=rnd.choice(color)
            _stroke(draw,[(sx,sy),(ex,ey)],mix,rnd.choice((1,2,2)))


def _holly_leaf(draw,x,y,angle,scale):
    points=[]
    for i in range(12):
        a=2*pi*i/12
        rr=(1 if i%2==0 else .67)*scale
        vx=cos(a)*rr*.43
        vy=sin(a)*rr
        points.append((round(x+vx*cos(angle)-vy*sin(angle)),
                       round(y+vx*sin(angle)+vy*cos(angle))))
    draw.polygon(points,fill=(18,110,57,255),outline=(146,176,86,255),width=2)
    _stroke(draw,[(x,y),(x-scale*.28*sin(angle),y-scale*.6*cos(angle))],
            (176,194,92,255),2)


def _poinsettia(draw,x,y,scale):
    for j in range(8):
        a=2*pi*j/8
        tip=_point(x,y,a,scale)
        left=_point(x,y,a-.30,scale*.63)
        right=_point(x,y,a+.30,scale*.63)
        draw.polygon([(x,y),left,tip,right],fill=(181+12*(j%2),25,44,255),
                     outline=(244,90,86,250),width=2)
        _stroke(draw,[(x,y),tip],(248,125,105,180),2)
    for j in range(7):
        xx,yy=_point(x,y,j*2*pi/7,scale*.14)
        draw.ellipse((xx-3,yy-3,xx+3,yy+3),fill=(247,206,89,255))


def _ornament(draw,x,y,r,red=True):
    col=(193,28,50,255) if red else (225,177,70,255)
    outline=(231,191,110,255)
    draw.ellipse((x-r,y-r,x+r,y+r),fill=col,outline=outline,width=3)
    draw.ellipse((x-r*.60,y-r*.75,x-r*.12,y-r*.16),
                 fill=(255,235,181,110))
    draw.arc((x-r*.7,y-r*.3,x+r*.6,y+r*.8),15,180,
             fill=outline,width=2)
    draw.rectangle((x-r*.16,y-r*1.15,x+r*.16,y-r*.87),fill=outline)
    draw.arc((x-r*.12,y-r*1.38,x+r*.12,y-r*1.04),180,360,
             fill=outline,width=2)


def _burst(draw,x,y,r,seed):
    rnd=Random(seed)
    for j in range(36):
        a=2*pi*j/36 + rnd.uniform(-.08,.08)
        dist=r*rnd.uniform(.70,1.06)
        sx,sy=_point(x,y,a,r*.12)
        ex,ey=_point(x,y,a,dist)
        gold=rnd.choice(((252,214,109,255),(240,170,69,245),
                          (255,244,186,255),(152,191,246,210)))
        _stroke(draw,[(sx,sy),(ex,ey)],gold,rnd.choice((1,2,3)))
        draw.ellipse((ex-2,ey-2,ex+2,ey+2),fill=gold)


def _ribbon(draw,x,y,scale,seed):
    rnd=Random(seed)
    for k in range(3):
        points=[]
        for i in range(40):
            t=i/39
            points.append((x+scale*(t*1.1),
                           y+scale*(k*.13+.10*sin(t*pi*5+k))))
        _stroke(draw,points,rnd.choice(((235,182,76,240),
                                        (255,228,148,235),
                                        (188,115,48,245))),3)


def _clock(draw,x,y,r):
    draw.ellipse((x-r,y-r,x+r,y+r),fill=(215,168,82,255),
                 outline=(255,230,158,255),width=4)
    draw.ellipse((x-r*.85,y-r*.85,x+r*.85,y+r*.85),
                 fill=(20,35,61,255),outline=(246,210,129,255),width=3)
    for i in range(12):
        a=i*pi/6-pi/2
        p=_point(x,y,a,r*.74)
        q=_point(x,y,a,r*.87)
        _stroke(draw,[p,q],(248,216,142,255),3)
    _stroke(draw,[(x,y),(x,y-r*.60)],(252,222,151,255),4)
    _stroke(draw,[(x,y),(x-r*.17,y-r*.34)],(252,222,151,255),3)
    draw.ellipse((x-4,y-4,x+4,y+4),fill=(254,223,149,255))


def _sparkles(draw,rnd,width,height,season):
    colors=([(246,209,117,220),(255,238,189,200)]
            if season=="new-year" else
            [(248,221,151,200),(255,235,185,170)])
    for _ in range(58):
        x=rnd.randint(12,width-12)
        y=rnd.randint(7,height-7)
        r=rnd.choice((1,1,2,3))
        fill=rnd.choice(colors)
        if r==3:
            _stroke(draw,[(x-5,y),(x+5,y)],fill,1)
            _stroke(draw,[(x,y-5),(x,y+5)],fill,1)
        else:
            draw.ellipse((x-r,y-r,x+r,y+r),fill=fill)


@lru_cache(maxsize=36)
def corner_art(season: str, variant: int, side: str):
    """360×240 RGBA corner artwork with rich transparent edges.

    Seasonal decoration is confined to edge / lower regions by the renderer,
    never placed over the title columns. Variant is the per-program asset index.
    """
    if season not in ("thanksgiving","christmas","new-year"):
        raise ValueError("unsupported seasonal corner")
    if side not in ("left","right") or not 0<=variant<4:
        raise ValueError("invalid artwork variant")
    # Overscan artwork source: preserve full seasonal shapes that otherwise
    # get cut off at the old 360×240 drawing boundary.
    overscan_size = (
        SIZE[0] + 2 * SOURCE_MARGIN[0],
        SIZE[1] + 2 * SOURCE_MARGIN[1],
    )
    im = Image.new("RGBA", overscan_size, (0, 0, 0, 0))
    draw = _TranslatedDraw(ImageDraw.Draw(im, "RGBA"), *SOURCE_MARGIN)
    rnd=Random(int.from_bytes(sha256(f"{season}:{variant}".encode()).digest()[:8],"big"))
    _sparkles(draw,rnd,*SIZE,season)

    if season=="thanksgiving":
        # Layered autumn leaf sprays, two pumpkins, acorns and berries.
        _stroke(draw,[(4,183),(90,143),(193,216),(312,227)],
                (111,76,43,240),6)
        for i in range(17):
            x=rnd.randint(3,320)
            y=rnd.choice((rnd.randint(130,185),rnd.randint(195,239)))
            radius=rnd.randint(15,40)
            _maple(draw,x,y,radius,rnd.uniform(-1.0,1.0),
                   rnd.choice((
                       ((232,111,36,255),(144,66,27,250),(250,185,96,205)),
                       ((183,55,41,255),(111,38,30,255),(245,141,72,210)),
                       ((245,164,43,255),(169,92,32,255),(255,214,109,220)),
                   )))
        _pumpkin(draw,65,183,125,106)
        _pumpkin(draw,143,198,72,65)
        _acorn(draw,209,207,35)
        _acorn(draw,246,220,27)
        for i in range(18):
            bx=rnd.randint(3,270);by=rnd.randint(193,238)
            draw.ellipse((bx-5,by-5,bx+5,by+5),
                         fill=rnd.choice(((167,35,45,255),
                                          (202,51,47,255),(126,37,41,255))))
    elif season=="christmas":
        # Interwoven evergreen sprays with red holly, poinsettia and ornaments.
        for i in range(11):
            x0=rnd.randint(-22,75);y0=rnd.randint(95,238)
            x1=rnd.randint(115,320);y1=rnd.randint(130,239)
            _pine(draw,x0,y0,x1,y1,
                  ((32,114,65,255),(14,77,49,255),
                   (55,145,79,255),(137,168,103,240)),variant*37+i)
        _poinsettia(draw,90,182,61)
        _ornament(draw,228,195,31,red=True)
        _ornament(draw,285,213,21,red=False)
        for i in range(7):
            x=rnd.randint(17,290);y=rnd.randint(165,228)
            _holly_leaf(draw,x,y,rnd.uniform(-pi,pi),rnd.randint(18,34))
        for x,y in ((175,190),(194,203),(171,214),(309,205),(300,222)):
            draw.ellipse((x-8,y-8,x+8,y+8),
                         fill=(170,27,43,255),
                         outline=(240,115,96,200),width=2)
        for j in range(17):
            x=rnd.randint(7,310);y=rnd.randint(126,238)
            draw.ellipse((x-2,y-2,x+2,y+2),fill=(249,249,235,225))
    else:
        # Navy-and-champagne champagne-ribbon flourish with fireworks and
        # midnight motif, composed as the left/right border rather than text.
        _burst(draw,105,124,74,variant*14+1)
        _burst(draw,230,64,47,variant*19+7)
        _burst(draw,303,169,29,variant*23+11)
        _ribbon(draw,6,212,275,variant*7)
        _clock(draw,94,182,50)
        for i in range(18):
            x=rnd.randint(6,326);y=rnd.randint(139,235)
            angle=rnd.uniform(0,2*pi)
            r=rnd.randint(4,11)
            pts=[_point(x,y,angle+k*pi/5,
                        r if k%2==0 else r*.43) for k in range(10)]
            draw.polygon(pts,fill=rnd.choice(((253,220,135,255),
                                             (208,155,66,245))))
    im = _fit_complete_artwork(im)
    if side == "right":
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return im


@lru_cache(maxsize=128)
def scaled_corner_art(season: str, variant: int, side: str,
                      width: int, height: int, opacity: int):
    """Cache the expensive LANCZOS resize for every frame of one program.

    Bounded cache keys prevent unbounded allocations from renderer dimensions.
    Returned images must be treated as immutable.
    """
    width = max(8, min(360, int(width)))
    height = max(8, min(240, int(height)))
    opacity = max(0, min(255, int(opacity)))
    image = corner_art(season, variant, side).resize(
        (width, height), Image.Resampling.LANCZOS
    )
    # No horizontal alpha feather: the full illustration is already fitted
    # into the transparent source canvas without any cropped-off silhouettes.
    # Preserve its natural opacity, subject only to the requested frame fade.
    if opacity < 255:
        image.putalpha(image.getchannel("A").point(
            lambda value: value * opacity // 255
        ))
    return image
