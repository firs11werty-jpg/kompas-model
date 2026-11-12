# -*- coding: utf-8 -*-
"""
3D-модель «Корпус редуктора вала Kusters» (чертёж 00.000СБ) для КОМПАС-3D v24.

Работает через COM API КОМПАС (API5, ProgID "Kompas.Application.5").
Запуск:  python build_korpus.py [--output путь.m3d] [--dry-run]

Система координат модели:
  * плоскость XOY  - наружный торец передней стенки (вид спереди на чертеже);
  * ось Z          - вдоль оси валов, в сторону открытого фланца Ø860;
  * (0, 0)         - ось главного вала, (0, -495) - ось нижнего вала.
"""
import argparse
import math
import os
import sys

# ----------------------------------------------------------------------------
# Размеры с чертежа, мм
# ----------------------------------------------------------------------------
R_BODY = 905 / 2          # наружный Ø905 обечайки (452,5 от оси до верха)
R_SHELL_IN = 830 / 2      # Ø830 внутренний обечайки
AXIS_DIST = 495.0         # 495±0,125 межосевое
Y_BOTTOM = -(1100 - 452.5)  # габарит 1100 -> низ корпуса на -647,5
R_LOWER = math.hypot(216 / 2, Y_BOTTOM + AXIS_DIST)  # дуга низа: хорда 216 на -647,5
WALL = 10.0               # стенки нижней части корпуса

T_FRONT = 28.0            # толщина передней стенки (поз. 1)
L_TOTAL = 250.0           # общая длина по оси
L_LOWER = 117.0           # вылет нижней части от передней стенки
T_COVER = 10.0            # задняя стенка нижней части (поз. 2)
T_HUB = 55.0              # бобышка нижнего вала (стенка + прилив)
R_HUB = 180.0

D_MAIN_BORE = 465.0       # Ø465H9
D_RECESS, RECESS_DEPTH = 665.0, 6.0      # Ø665H11 глубина 6
D_FLANGE_BORE, FLANGE_BORE_DEPTH = 860.0, 25.0  # Ø860H9 глубина 25
D_LOWER_BORE = 260.0      # Ø260H9 (передняя стенка, см. вид сбоку)
D_COVER_BORE = 140.0      # Ø140 (задняя стенка нижней части)

# Отверстия: (кол-во, Ø окружности, Ø сверла, нач. угол от оси X, шаг, глубина)
HOLES_FRONT = [
    (12, 640.0, 10.2, 15.0, 30.0, T_FRONT),   # 12 отв. M12-7H
    (8, 500.0, 18.0, 22.5, 45.0, T_FRONT),    # 8 отв. Ø18 (К-К)
    (6, 720.0, 49.0, 0.0, 60.0, T_FRONT),     # 6 отв. Ø49 / G1 1/4 (Л-Л)
]
# 8 отв. M16-7H на Ø320, гл. 32 (В-В); шаг неравномерный: нижняя пара разнесена на 160
HOLES_LOWER_HUB = (320.0, 14.0, (22.5, 67.5, 112.5, 157.5, 202.5, 240.0, 300.0, 337.5), 32.0)
HOLES_FLANGE = (20, 880.0, 8.5, 90.0 - 7.5, 18.0, 20.0)  # 20 отв. M10-7H на Ø880


# ----------------------------------------------------------------------------
# Геометрия контуров (сегменты: ('line', p1, p2) / ('arc', c, r, p1, p2, ccw))
# ----------------------------------------------------------------------------
def _pt(c, r, ang):
    return (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))


def hull_points(r_top, r_bot, y_bottom):
    """Касательные к окружностям r_top в (0,0) и r_bot в (0,-AXIS_DIST), срез низа y_bottom."""
    s = -(r_top - r_bot) / AXIS_DIST
    c = math.sqrt(1 - s * s)
    c2 = (0.0, -AXIS_DIST)
    t1r, t1l = (r_top * c, r_top * s), (-r_top * c, r_top * s)
    t2r, t2l = (c2[0] + r_bot * c, c2[1] + r_bot * s), (-r_bot * c, c2[1] + r_bot * s)
    xb = math.sqrt(r_bot ** 2 - (y_bottom - c2[1]) ** 2)
    return t1r, t1l, t2r, t2l, (xb, y_bottom), (-xb, y_bottom)


def hull_contour(r_top, r_bot, y_bottom):
    """Полный контур боковины: верх по большой окружности, касательные, низ."""
    t1r, t1l, t2r, t2l, br, bl = hull_points(r_top, r_bot, y_bottom)
    c2 = (0.0, -AXIS_DIST)
    return [
        ("arc", (0.0, 0.0), r_top, t1r, t1l, True),
        ("line", t1l, t2l),
        ("arc", c2, r_bot, t2l, bl, True),
        ("line", bl, br),
        ("arc", c2, r_bot, br, t2r, True),
        ("line", t2r, t1r),
    ]


def lower_region_contour():
    """Нижняя часть корпуса - контур боковины минус круг обечайки Ø905."""
    seg = hull_contour(R_BODY, R_LOWER, Y_BOTTOM)
    t1r, t1l = seg[0][3], seg[0][4]
    return seg[1:] + [("arc", (0.0, 0.0), R_BODY, t1r, t1l, False)]


def hub_contour():
    """Прилив нижнего вала, срезанный внутренней плоскостью дна."""
    c2 = (0.0, -AXIS_DIST)
    y = Y_BOTTOM + WALL
    x = math.sqrt(R_HUB ** 2 - (y - c2[1]) ** 2)
    return [("arc", c2, R_HUB, (x, y), (-x, y), True), ("line", (-x, y), (x, y))]


def circle_pattern(n, d_pcd, d_hole, start_deg, step_deg, center=(0.0, 0.0)):
    return [("circle", _pt(center, d_pcd / 2, math.radians(start_deg + i * step_deg)), d_hole / 2)
            for i in range(n)]


def check_closed(contour, tol=1e-6):
    pts = []
    for s in contour:
        if s[0] == "line":
            pts.append((s[1], s[2]))
        elif s[0] == "arc":
            pts.append((s[3], s[4]))
    for (_, end), (start, _) in zip(pts, pts[1:] + pts[:1]):
        if math.dist(end, start) > tol:
            raise ValueError(f"Контур не замкнут: {end} -> {start}")


# ----------------------------------------------------------------------------
# Построение (backend-независимое)
# ----------------------------------------------------------------------------
def build(m):
    # 1. Передняя стенка (поз. 1)
    m.extrude("base", 0.0, [hull_contour(R_BODY, R_LOWER, Y_BOTTOM)], T_FRONT, name="Передняя стенка")

    # 2. Обечайка Ø905/Ø830 до фланца
    m.extrude("boss", T_FRONT,
              [[("circle", (0.0, 0.0), R_BODY)], [("circle", (0.0, 0.0), R_SHELL_IN)]],
              L_TOTAL - T_FRONT, name="Обечайка")

    # 3. Нижняя часть корпуса (сплошной объём, далее выбирается карманом)
    m.extrude("boss", T_FRONT, [lower_region_contour()], L_LOWER, name="Нижняя часть")

    # 4. Внутренняя полость нижней части, соединённая с полостью обечайки
    m.extrude("cut", T_FRONT, [hull_contour(R_SHELL_IN, R_LOWER - WALL, Y_BOTTOM + WALL)],
              L_LOWER - T_COVER, name="Полость нижней части")

    # 5. Прилив нижнего вала
    m.extrude("boss", T_FRONT, [hub_contour()], T_HUB - T_FRONT, name="Прилив нижнего вала")

    # 6. Отверстия передней стенки
    m.extrude("cut", 0.0, [[("circle", (0.0, 0.0), D_MAIN_BORE / 2)]], T_FRONT, name="Расточка Ø465H9")
    m.extrude("cut", T_FRONT, [[("circle", (0.0, 0.0), D_RECESS / 2)]], RECESS_DEPTH,
              reverse=True, name="Выточка Ø665H11")
    m.extrude("cut", 0.0, [[("circle", (0.0, -AXIS_DIST), D_LOWER_BORE / 2)]], T_HUB,
              name="Расточка Ø260H9")
    for n, pcd, d, a0, step, depth in HOLES_FRONT:
        m.extrude("cut", 0.0, [[c] for c in circle_pattern(n, pcd, d, a0, step)], depth,
                  name=f"{n} отв. Ø{d:g} на Ø{pcd:g}")
    pcd, d, angles, depth = HOLES_LOWER_HUB
    holes = [[("circle", _pt((0.0, -AXIS_DIST), pcd / 2, math.radians(a)), d / 2)] for a in angles]
    m.extrude("cut", 0.0, holes, depth, name="8 отв. M16 на Ø320")

    # 7. Задняя стенка нижней части
    m.extrude("cut", T_FRONT + L_LOWER, [[("circle", (0.0, -AXIS_DIST), D_COVER_BORE / 2)]],
              T_COVER, reverse=True, name="Отверстие Ø140")

    # 8. Фланец Ø860H9 и 20 отв. M10
    m.extrude("cut", L_TOTAL, [[("circle", (0.0, 0.0), D_FLANGE_BORE / 2)]], FLANGE_BORE_DEPTH,
              reverse=True, name="Расточка Ø860H9")
    n, pcd, d, a0, step, depth = HOLES_FLANGE
    m.extrude("cut", L_TOTAL, [[c] for c in circle_pattern(n, pcd, d, a0, step)], depth,
              reverse=True, name="20 отв. M10 на Ø880")


class DryRun:
    """Проверка контуров без КОМПАС."""

    def __init__(self):
        self.ops = []

    def extrude(self, op, z, contours, depth, reverse=False, name=""):
        for c in contours:
            check_closed(c)
        self.ops.append((op, z, contours, depth, reverse, name))
        sign = "-" if reverse else "+"
        print(f"{op:5s} z={z:6.1f} {sign}{depth:6.1f}  контуров: {len(contours):2d}  {name}")


# ----------------------------------------------------------------------------
# КОМПАС-3D (API5 через COM)
# ----------------------------------------------------------------------------
_CONST_FALLBACK = {
    "pTop_Part": -1, "o3d_planeXOY": 1, "o3d_sketch": 5, "o3d_planeOffset": 14,
    "o3d_baseExtrusion": 24, "o3d_bossExtrusion": 25, "o3d_cutExtrusion": 26,
    "dtNormal": 0, "dtReverse": 1, "etBlind": 0,
}
CUT_FLIP = True


def _load_constants():
    """Константы из библиотеки типов КОМПАС; при неудаче - известные значения."""
    from win32com.client import gencache
    consts = dict(_CONST_FALLBACK)
    try:
        c3d = gencache.EnsureModule("{2CAF168C-7961-4B90-9DA2-701419BEEFE3}", 0, 1, 0).constants
        for k in consts:
            consts[k] = getattr(c3d, k, consts[k])
    except Exception as exc:  # noqa: BLE001
        print(f"[!] ksConstants3D недоступны ({exc}), используются встроенные значения")
    return consts


class Kompas:
    def __init__(self):
        from win32com.client import Dispatch
        self.k = _load_constants()
        try:
            self.app = Dispatch("Kompas.Application.5")
        except Exception as exc:
            raise SystemExit(
                "Не удалось подключиться к КОМПАС-3D (Kompas.Application.5).\n"
                "Запустите run_kompas.ps1 - он проверит регистрацию COM.\n" + str(exc))
        self.app.Visible = True
        self.doc = self.app.Document3D()
        if not self.doc.Create(False, True):  # видимый документ, деталь
            raise SystemExit("КОМПАС не создал документ детали")
        self.part = self.doc.GetPart(self.k["pTop_Part"])
        self.part.name = "Корпус редуктора вала Kusters"
        self.part.marking = "00.000СБ"
        self.part.Update()
        self.xoy = self.part.GetDefaultEntity(self.k["o3d_planeXOY"])
        self._planes = {0.0: self.xoy}

    def _plane(self, z):
        if z not in self._planes:
            ent = self.part.NewEntity(self.k["o3d_planeOffset"])
            d = ent.GetDefinition()
            d.SetPlane(self.xoy)
            d.offset = z
            d.direction = True
            ent.hidden = True
            ent.Create()
            self._planes[z] = ent
        return self._planes[z]

    def _sketch(self, z, contours, name):
        sk = self.part.NewEntity(self.k["o3d_sketch"])
        d = sk.GetDefinition()
        d.SetPlane(self._plane(z))
        sk.name = "Эскиз: " + name
        sk.Create()
        doc2d = d.BeginEdit()
        for contour in contours:
            for s in contour:
                if s[0] == "line":
                    (x1, y1), (x2, y2) = s[1], s[2]
                    doc2d.ksLineSeg(x1, y1, x2, y2, 1)
                elif s[0] == "arc":
                    (xc, yc), r, (x1, y1), (x2, y2), ccw = s[1:]
                    doc2d.ksArcByPoint(xc, yc, r, x1, y1, x2, y2, 1 if ccw else -1, 1)
                else:
                    (xc, yc), r = s[1], s[2]
                    doc2d.ksCircle(xc, yc, r, 1)
        d.EndEdit()
        return sk

    def extrude(self, op, z, contours, depth, reverse=False, name=""):
        k = self.k
        sk = self._sketch(z, contours, name)
        kind = {"base": "o3d_baseExtrusion", "boss": "o3d_bossExtrusion", "cut": "o3d_cutExtrusion"}[op]
        ent = self.part.NewEntity(k[kind])
        d = ent.GetDefinition()
        if op == "cut":
            d.cut = True
            # В КОМПАС прямое направление выреза противоположно нормали эскиза
            # (на v24 без инверсии полость прорезала переднюю стенку).
            if CUT_FLIP:
                reverse = not reverse
        d.directionType = k["dtReverse"] if reverse else k["dtNormal"]
        d.SetSideParam(not reverse, k["etBlind"], depth, 0, False)
        d.SetThinParam(False, 0, 0, 0)
        d.SetSketch(sk)
        ent.name = name
        if not ent.Create():
            print(f"[!] Операция не построена: {name}")
        else:
            print(f"[ok] {name}")

    def save(self, path):
        path = os.path.abspath(path)
        self.doc.SaveAs(path)
        print("Сохранено:", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "Корпус_редуктора_00.000СБ.m3d"))
    ap.add_argument("--dry-run", action="store_true", help="проверить геометрию без КОМПАС")
    ap.add_argument("--no-cut-flip", action="store_true",
                    help="не инвертировать направление вырезов (если отверстия уходят наружу)")
    args = ap.parse_args()
    global CUT_FLIP
    CUT_FLIP = not args.no_cut_flip

    if args.dry_run:
        build(DryRun())
        print("Геометрия корректна.")
        return
    if sys.platform != "win32":
        raise SystemExit("Построение в КОМПАС возможно только в Windows (используйте --dry-run)")
    m = Kompas()
    build(m)
    m.part.Update()
    m.save(args.output)


if __name__ == "__main__":
    main()
