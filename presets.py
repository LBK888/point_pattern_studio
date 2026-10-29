"""Built-in line-art presets for tab ③ and `cli.py optimize <preset>`.
Everything is drawn with OpenCV on a 720×720 white canvas, black 3 px strokes;
no external images or fonts are needed.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SIZE = 720
INK = 0
PAPER = 255
LINE = 3


# ---------------------------------------------------------------- helpers
def _blank():
    return np.full((SIZE, SIZE), PAPER, np.uint8)


def _pts(points):
    return np.round(np.asarray(points, float)).astype(np.int32).reshape(-1, 1, 2)


def _poly(img, points, closed=False, t=LINE):
    cv2.polylines(img, [_pts(points)], closed, INK, t, cv2.LINE_AA)


def _fill(mask, points, value=1):
    cv2.fillPoly(mask, [_pts(points)], value)


def _outline(img, mask, t=LINE):
    """Draw the outer silhouette of a filled mask (union of shapes)."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(img, contours, -1, INK, t, cv2.LINE_AA)


def _erase_inside(layer, mask):
    """Hide strokes of `layer` that fall inside `mask` (painter's occlusion)."""
    layer[mask.astype(bool)] = PAPER
    return layer


def _bezier(p0, p1, p2, p3=None, m=80):
    t = np.linspace(0, 1, m)[:, None]
    p0, p1, p2 = (np.asarray(p, float) for p in (p0, p1, p2))
    if p3 is None:
        return (1-t)**2*p0 + 2*(1-t)*t*p1 + t**2*p2
    p3 = np.asarray(p3, float)
    return (1-t)**3*p0 + 3*(1-t)**2*t*p1 + 3*(1-t)*t**2*p2 + t**3*p3


def _heart(cx, cy, scale, m=600):
    t = np.linspace(0, 2*np.pi, m, endpoint=False)
    x = 16*np.sin(t)**3
    y = 13*np.cos(t) - 5*np.cos(2*t) - 2*np.cos(3*t) - np.cos(4*t)
    return np.column_stack((cx + scale*x, cy - scale*y))


def _star(cx, cy, r_out, r_in, k=5, rot=-90):
    pts = []
    for i in range(2*k):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i*180/k)
        pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return pts


def _leaf(base, tip, width):
    base, tip = np.asarray(base, float), np.asarray(tip, float)
    d = tip - base
    normal = np.array([-d[1], d[0]]) / max(1e-9, np.hypot(*d))
    mid = base + d*.5
    side_a = _bezier(base, mid + normal*width, tip)
    side_b = _bezier(tip, mid - normal*width, base)
    return np.vstack((side_a, side_b))


# ---------------------------------------------------------------- v1.0 presets (unchanged)
def fish():
    img = _blank()
    body = np.array([(105,373),(175,310),(300,265),(420,270),(515,330),(560,365),
                     (515,400),(420,450),(290,470),(170,430)],np.int32)
    cv2.polylines(img,[body],True,0,3,cv2.LINE_AA)
    cv2.polylines(img,[np.array([(105,373),(40,288),(40,456),(105,373)],np.int32)],False,0,3,cv2.LINE_AA)
    cv2.polylines(img,[np.array([(290,265),(355,180),(398,274)],np.int32)],False,0,3,cv2.LINE_AA)
    cv2.polylines(img,[np.array([(300,469),(370,530),(435,448)],np.int32)],False,0,3,cv2.LINE_AA)
    cv2.circle(img,(465,344),12,0,2,cv2.LINE_AA)
    cv2.ellipse(img,(425,370),(40,65),0,100,260,0,2,cv2.LINE_AA)
    for x in [180,245,315,390]:
        cv2.ellipse(img,(x,367),(23,38),0,65,290,0,1,cv2.LINE_AA)
    return img


def face():
    img = _blank()
    cv2.ellipse(img,(360,356),(208,268),0,0,360,0,3,cv2.LINE_AA)
    cv2.ellipse(img,(270,330),(58,28),0,0,360,0,3,cv2.LINE_AA)
    cv2.ellipse(img,(450,330),(58,28),0,0,360,0,3,cv2.LINE_AA)
    cv2.circle(img,(270,330),12,0,-1,cv2.LINE_AA)
    cv2.circle(img,(450,330),12,0,-1,cv2.LINE_AA)
    cv2.polylines(img,[np.array([(353,340),(318,450),(375,456)],np.int32)],False,0,3,cv2.LINE_AA)
    cv2.ellipse(img,(364,510),(88,29),0,0,180,0,3,cv2.LINE_AA)
    cv2.ellipse(img,(360,220),(192,130),0,195,355,0,4,cv2.LINE_AA)
    cv2.ellipse(img,(147,366),(26,62),0,210,480,0,3,cv2.LINE_AA)
    cv2.ellipse(img,(573,366),(26,62),0,-30,240,0,3,cv2.LINE_AA)
    return img


def circles():
    img = _blank()
    for r in (80,145,210):cv2.circle(img,(360,360),r,0,3,cv2.LINE_AA)
    for angle in range(0,360,45):
        q=np.deg2rad(angle)
        cv2.line(img,(int(360+40*np.cos(q)),int(360+40*np.sin(q))),
                 (int(360+250*np.cos(q)),int(360+250*np.sin(q))),0,2,cv2.LINE_AA)
    return img


# ---------------------------------------------------------------- v1.1 presets
def heart():
    img = _blank()
    _poly(img, _heart(360, 318, 18.5), closed=True)
    return img


def heart_arrow():
    """一箭穿心: the shaft is hidden while it passes behind the heart."""
    outline = _blank()
    shape = _heart(375, 330, 15)
    _poly(outline, shape, closed=True)
    inside = np.zeros((SIZE, SIZE), np.uint8)
    _fill(inside, shape)
    arrow = _blank()
    tail, tip = np.array([95., 590.]), np.array([640., 150.])
    d = (tip - tail) / np.linalg.norm(tip - tail)
    n = np.array([-d[1], d[0]])
    _poly(arrow, [tail, tip])
    # Arrowhead: a closed triangle at the tip.
    _poly(arrow, [tip + d*8, tip - d*48 + n*26, tip - d*48 - n*26], closed=True)
    # Fletching: three feather pairs near the tail.
    for k in range(3):
        base = tail + d*(18 + 26*k)
        for s in (1, -1):
            _poly(arrow, [base, base - d*32 + n*s*28])
    _erase_inside(arrow, inside)
    return np.minimum(outline, arrow)


def cat():
    img = _blank()
    head = np.zeros((SIZE, SIZE), np.uint8)
    cv2.ellipse(head, (360, 410), (235, 190), 0, 0, 360, 1, -1)
    _fill(head, [(150, 330), (170, 110), (300, 225)])
    _fill(head, [(570, 330), (550, 110), (420, 225)])
    _outline(img, head)
    _poly(img, [(185, 290), (195, 170), (265, 232)])          # inner ears
    _poly(img, [(535, 290), (525, 170), (455, 232)])
    for ex in (275, 445):                                       # eyes with slit pupils
        cv2.ellipse(img, (ex, 385), (40, 34), 0, 0, 360, INK, LINE, cv2.LINE_AA)
        cv2.ellipse(img, (ex, 385), (8, 26), 0, 0, 360, INK, -1, cv2.LINE_AA)
    _poly(img, [(340, 455), (380, 455), (360, 476)], closed=True)   # nose
    _poly(img, [(360, 476), (360, 492)])
    cv2.ellipse(img, (337, 492), (23, 18), 0, 0, 180, INK, LINE, cv2.LINE_AA)  # ω mouth
    cv2.ellipse(img, (383, 492), (23, 18), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    for dy, ty in ((-12, -40), (6, 6), (24, 52)):              # whiskers
        _poly(img, [(250, 470 + dy), (85, 470 + ty)])
        _poly(img, [(470, 470 + dy), (635, 470 + ty)])
    return img


def dog():
    img = _blank()
    cv2.ellipse(img, (360, 395), (185, 200), 0, 0, 360, INK, LINE, cv2.LINE_AA)
    for cx, ang in ((178, 18), (542, -18)):                     # floppy ears over the head
        cv2.ellipse(img, (cx, 375), (62, 150), ang, 0, 360, PAPER, -1, cv2.LINE_AA)
        cv2.ellipse(img, (cx, 375), (62, 150), ang, 0, 360, INK, LINE, cv2.LINE_AA)
    for ex in (295, 425):
        cv2.circle(img, (ex, 355), 15, INK, -1, cv2.LINE_AA)
        cv2.ellipse(img, (ex, 312), (26, 10), 0, 200, 340, INK, LINE, cv2.LINE_AA)  # brows
    cv2.ellipse(img, (360, 475), (88, 66), 0, 0, 360, INK, LINE, cv2.LINE_AA)       # muzzle
    cv2.ellipse(img, (360, 440), (30, 20), 0, 0, 360, INK, -1, cv2.LINE_AA)         # nose
    _poly(img, [(360, 458), (360, 490)])
    cv2.ellipse(img, (336, 490), (24, 16), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (384, 490), (24, 16), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (360, 520), (17, 24), 0, 0, 180, INK, LINE, cv2.LINE_AA)       # tongue
    return img


def bear():
    img = _blank()
    head = np.zeros((SIZE, SIZE), np.uint8)
    cv2.circle(head, (360, 410), 205, 1, -1)
    cv2.circle(head, (195, 230), 72, 1, -1)
    cv2.circle(head, (525, 230), 72, 1, -1)
    _outline(img, head)
    cv2.ellipse(img, (205, 240), (36, 36), 0, 120, 405, INK, LINE, cv2.LINE_AA)    # inner ears
    cv2.ellipse(img, (515, 240), (36, 36), 0, 135, 420, INK, LINE, cv2.LINE_AA)
    for ex in (285, 435):
        cv2.circle(img, (ex, 375), 15, INK, -1, cv2.LINE_AA)
    cv2.ellipse(img, (360, 480), (92, 70), 0, 0, 360, INK, LINE, cv2.LINE_AA)       # muzzle
    cv2.ellipse(img, (360, 448), (32, 21), 0, 0, 360, INK, -1, cv2.LINE_AA)
    _poly(img, [(360, 468), (360, 500)])
    cv2.ellipse(img, (336, 500), (24, 16), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (384, 500), (24, 16), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    return img


def rabbit():
    img = _blank()
    head = np.zeros((SIZE, SIZE), np.uint8)
    cv2.ellipse(head, (360, 475), (195, 170), 0, 0, 360, 1, -1)
    cv2.ellipse(head, (285, 215), (55, 160), -10, 0, 360, 1, -1)
    cv2.ellipse(head, (435, 215), (55, 160), 10, 0, 360, 1, -1)
    _outline(img, head)
    cv2.ellipse(img, (287, 225), (24, 112), -10, 0, 360, INK, LINE, cv2.LINE_AA)    # inner ears
    cv2.ellipse(img, (433, 225), (24, 112), 10, 0, 360, INK, LINE, cv2.LINE_AA)
    for ex in (290, 430):
        cv2.circle(img, (ex, 455), 14, INK, -1, cv2.LINE_AA)
    _poly(img, [(345, 510), (375, 510), (360, 526)], closed=True)
    _poly(img, [(360, 526), (360, 542)])
    cv2.ellipse(img, (340, 542), (20, 15), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (380, 542), (20, 15), 0, 0, 180, INK, LINE, cv2.LINE_AA)
    for cx in (245, 475):                                        # blush
        cv2.ellipse(img, (cx, 515), (28, 14), 0, 0, 360, INK, 2, cv2.LINE_AA)
    return img


def smiley():
    img = _blank()
    cv2.circle(img, (360, 360), 265, INK, LINE, cv2.LINE_AA)
    for ex in (270, 450):
        cv2.ellipse(img, (ex, 285), (24, 42), 0, 0, 360, INK, LINE, cv2.LINE_AA)
        cv2.ellipse(img, (ex, 297), (11, 22), 0, 0, 360, INK, -1, cv2.LINE_AA)
    cv2.ellipse(img, (360, 395), (160, 125), 0, 18, 162, INK, LINE, cv2.LINE_AA)
    _poly(img, [(198, 425), (222, 438)])                          # smile dimples
    _poly(img, [(522, 425), (498, 438)])
    return img


def star():
    img = _blank()
    _poly(img, _star(360, 385, 315, 125), closed=True)
    return img


def house():
    img = _blank()
    _poly(img, [(190, 370), (190, 620), (530, 620), (530, 370)])          # walls
    _poly(img, [(140, 380), (360, 150), (580, 380)])                      # roof
    roof_y = lambda x: 150 + (x - 360) * (230 / 220)
    _poly(img, [(450, roof_y(450)), (450, 175), (500, 175), (500, roof_y(500))])  # chimney
    _poly(img, [(318, 620), (318, 480), (402, 480), (402, 620)])          # door
    cv2.circle(img, (388, 555), 6, INK, -1, cv2.LINE_AA)
    for x0 in (222, 428):                                                 # windows
        _poly(img, [(x0, 415), (x0 + 70, 415), (x0 + 70, 480), (x0, 480)], closed=True)
        _poly(img, [(x0 + 35, 415), (x0 + 35, 480)])
        _poly(img, [(x0, 447), (x0 + 70, 447)])
    _poly(img, [(80, 620), (640, 620)])                                   # ground
    return img


def flower():
    img = _blank()
    cx, cy = 360, 265
    petals = np.zeros((SIZE, SIZE), np.uint8)
    for k in range(8):
        a = k * 45
        px = cx + 108*math.cos(math.radians(a))
        py = cy + 108*math.sin(math.radians(a))
        cv2.ellipse(petals, (int(px), int(py)), (72, 44), a, 0, 360, 1, -1)
    _outline(img, petals)
    cv2.circle(img, (cx, cy), 58, PAPER, -1)
    cv2.circle(img, (cx, cy), 58, INK, LINE, cv2.LINE_AA)
    stem = _bezier((cx, cy + 178), (cx - 30, 470), (cx + 30, 560), (cx, 680))
    _poly(img, stem)
    _poly(img, _leaf((cx - 6, 520), (215, 455), 42), closed=True)
    _poly(img, _leaf((cx + 8, 600), (505, 540), 40), closed=True)
    return img


def tree():
    img = _blank()
    canopy = np.zeros((SIZE, SIZE), np.uint8)
    for x, y, r in ((360, 185, 115), (245, 265, 100), (475, 265, 100),
                    (290, 360, 95), (430, 360, 95), (360, 300, 110)):
        cv2.circle(canopy, (x, y), r, 1, -1)
    _outline(img, canopy)
    trunk = _blank()
    _poly(trunk, [(330, 380), (318, 625)])
    _poly(trunk, [(392, 380), (404, 625)])
    _erase_inside(trunk, canopy)
    # Small branch on the left: two edges meeting the trunk, trunk line between them hidden.
    _poly(trunk, [(324, 530), (268, 476)])
    _poly(trunk, [(326, 498), (282, 460)])
    _poly(trunk, [(268, 476), (282, 460)])
    gap = np.zeros((SIZE, SIZE), np.uint8)
    _fill(gap, [(322, 528), (330, 528), (331, 500), (323, 500)])
    _erase_inside(trunk, gap)
    img = np.minimum(img, trunk)
    _poly(img, [(170, 628), (550, 628)])
    return img


def sun():
    img = _blank()
    cv2.circle(img, (360, 360), 128, INK, LINE, cv2.LINE_AA)
    for k in range(12):
        a = math.radians(k * 30)
        r1, r2 = 168, (268 if k % 2 == 0 else 228)
        _poly(img, [(360 + r1*math.cos(a), 360 + r1*math.sin(a)),
                    (360 + r2*math.cos(a), 360 + r2*math.sin(a))])
    for ex in (318, 402):
        cv2.circle(img, (ex, 335), 11, INK, -1, cv2.LINE_AA)
    cv2.ellipse(img, (360, 375), (55, 40), 0, 20, 160, INK, LINE, cv2.LINE_AA)
    return img


def snowflake():
    img = _blank()
    c = np.array([360., 360.])
    for k in range(6):
        a = math.radians(90 + k*60)
        d = np.array([math.cos(a), math.sin(a)])
        _poly(img, [c + d*42, c + d*295])
        for at, length in ((.42, 72), (.68, 54), (.88, 34)):
            base = c + d*295*at
            for s in (1, -1):
                b = math.radians(math.degrees(a) + s*45)
                _poly(img, [base, base + np.array([math.cos(b), math.sin(b)])*length])
    hexagon = [c + 42*np.array([math.cos(math.radians(90 + k*60)), math.sin(math.radians(90 + k*60))])
               for k in range(6)]
    _poly(img, hexagon, closed=True)
    return img


def butterfly():
    img = _blank()
    wings = np.zeros((SIZE, SIZE), np.uint8)
    for s in (1, -1):
        cv2.ellipse(wings, (int(360 + s*130), 290), (125, 92), s*-32, 0, 360, 1, -1)
        cv2.ellipse(wings, (int(360 + s*105), 470), (88, 72), s*35, 0, 360, 1, -1)
    _outline(img, wings)
    for s in (1, -1):                                               # wing spots
        cv2.circle(img, (int(360 + s*150), 270), 32, INK, LINE, cv2.LINE_AA)
        cv2.circle(img, (int(360 + s*115), 480), 22, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (360, 390), (20, 150), 0, 0, 360, PAPER, -1)   # body over wings
    cv2.ellipse(img, (360, 390), (20, 150), 0, 0, 360, INK, LINE, cv2.LINE_AA)
    cv2.circle(img, (360, 220), 24, PAPER, -1)
    cv2.circle(img, (360, 220), 24, INK, LINE, cv2.LINE_AA)
    for s in (1, -1):                                               # antennae
        _poly(img, _bezier((360 + s*8, 198), (360 + s*20, 130), (360 + s*70, 95)))
        cv2.circle(img, (int(360 + s*74), 92), 9, INK, -1, cv2.LINE_AA)
    return img


def moon():
    img = _blank()
    crescent = np.zeros((SIZE, SIZE), np.uint8)
    cv2.circle(crescent, (330, 375), 245, 1, -1)
    cv2.circle(crescent, (440, 300), 215, 0, -1)
    _outline(img, crescent)
    for x, y, r in ((495, 255, 55), (612, 150, 30), (622, 420, 34)):
        _poly(img, _star(x, y, r, r*.42), closed=True)
    return img


def umbrella():
    img = _blank()
    cx, top, rim, half = 360, 130, 340, 270
    cv2.ellipse(img, (cx, rim), (half, rim - top), 0, 180, 360, INK, LINE, cv2.LINE_AA)
    w = 2*half/4
    for k in range(4):                                               # scalloped rim
        x = cx - half + w*(k + .5)
        cv2.ellipse(img, (int(x), rim), (int(w/2), 32), 0, 180, 360, INK, LINE, cv2.LINE_AA)
    cv2.ellipse(img, (cx, rim), (int(w), rim - top), 0, 180, 360, INK, LINE, cv2.LINE_AA)  # ribs
    _poly(img, [(cx, top - 28), (cx, top)])                          # tip
    _poly(img, [(cx, rim - 32), (cx, 600)])                          # shaft
    cv2.ellipse(img, (cx - 42, 600), (42, 42), 0, 0, 180, INK, LINE, cv2.LINE_AA)  # J handle
    return img


# label -> (file key, drawing function); order is the GUI menu order.
PRESETS = {
    '魚': ('fish', fish),
    '人臉': ('face', face),
    '同心圓': ('circles', circles),
    '愛心': ('heart', heart),
    '一箭穿心': ('heart_arrow', heart_arrow),
    '小貓臉': ('cat', cat),
    '小狗臉': ('dog', dog),
    '小熊臉': ('bear', bear),
    '兔子臉': ('rabbit', rabbit),
    '笑臉': ('smiley', smiley),
    '星星': ('star', star),
    '房子': ('house', house),
    '花朵': ('flower', flower),
    '樹': ('tree', tree),
    '太陽': ('sun', sun),
    '雪花': ('snowflake', snowflake),
    '蝴蝶': ('butterfly', butterfly),
    '月亮星星': ('moon', moon),
    '雨傘': ('umbrella', umbrella),
}


def preset_label(name: str) -> str | None:
    """Accept a Chinese label or English key (e.g. '小貓臉' or 'cat')."""
    if name in PRESETS:
        return name
    for label, (key, _) in PRESETS.items():
        if key == str(name).lower():
            return label
    return None


def preset_filename(name: str) -> str:
    label = preset_label(name)
    if label is None:
        raise KeyError(name)
    return f'example_{PRESETS[label][0]}.png'


def make_preset(name: str, path) -> Path:
    label = preset_label(name)
    if label is None:
        raise KeyError(f'未知的內建圖形：{name}（可用：{", ".join(PRESETS)}）')
    img = PRESETS[label][1]()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(path)
    return path
