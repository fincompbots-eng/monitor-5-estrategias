"""Bat Pattern (Carney) - port de 'Bat Pattern Pro V1' (Pine) a velas DIARIAS.

Reproduce la maquina de estados del indicador:
    0 = sin patron | 1 = esperando que el precio llegue a D | 2 = D tocado, esperando RSI
La maquina es determinista, asi que en cada ejecucion se recorre el historial vela a vela
y se avisa solo si la senal ocurre en la ULTIMA vela cerrada. No se guarda la maquina entre
ejecuciones: solo las claves de alertas ya enviadas (state/bat.json).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import Senal, pivotes, px, rsi

NAME = "Bat"
MIN_BARS = 120

# --- Parametros (iguales a los inputs del Pine) ---
PIV_LEN = 5          # barras a cada lado del pivote
TOL = 0.05           # tolerancia en ratios Fibonacci
MAX_ESPERA = 50      # barras maximas para llegar a D
USAR_RSI = True
RSI_LEN = 14
RSI_UMBRAL = 40      # compra: RSI <= umbral | venta: RSI >= 100 - umbral
N_CONF = 3           # barras para esperar la confirmacion tras tocar D
SL_EXTRA = 0.10      # holgura del stop mas alla de X (fraccion de XA)
TP1_FIB = 0.382
TP2_FIB = 0.618


@dataclass
class _Estado:
    st: int = 0
    x: float = np.nan
    a: float = np.nan
    b: float = np.nan
    c: float = np.nan
    d: float = np.nan
    t0: int = 0
    cnt: int = 0


def _add_pivot(pivs: list, price: float, bar: int, typ: int) -> bool:
    """Agrega un pivote forzando la alternancia maximo/minimo (typ: 1 = maximo, -1 = minimo)."""
    cambio = False
    if pivs and pivs[-1][2] == typ:
        mejor = price > pivs[-1][0] if typ == 1 else price < pivs[-1][0]
        if mejor:
            pivs[-1] = (price, bar, typ)
            cambio = True
    else:
        pivs.append((price, bar, typ))
        cambio = True
        if len(pivs) > 40:
            pivs.pop(0)
    return cambio


def _check_bat(x: float, a: float, b: float, c: float, bull: bool):
    """Reglas del Bat: B 0.382-0.50 de XA | C 0.382-0.886 de AB | CD/BC 1.618-2.618 | D en 0.886 de XA."""
    xa, ab, bc = abs(a - x), abs(a - b), abs(c - b)
    d = a - 0.886 * xa if bull else a + 0.886 * xa
    cd = abs(c - d)
    ok = False
    if xa > 0 and ab > 0 and bc > 0:
        r_b, r_c, r_bc = ab / xa, bc / ab, cd / bc
        if bull:
            geom = a > x and b < a and b > x and c > b and c < a
        else:
            geom = a < x and b > a and b < x and c < b and c > a
        ok = (geom
              and 0.382 - TOL <= r_b <= 0.50 + TOL
              and 0.382 - TOL <= r_c <= 0.886 + TOL
              and 1.618 - TOL <= r_bc <= 2.618 + TOL)
    return ok, d


def _procesar(s: _Estado, bull: bool, i: int, h, l, c, rsi_v, fecha: str):
    """Maquina de estados de un patron (alcista o bajista) en la vela cerrada i."""
    senal = None
    if s.st == 1:
        invalido = (l[i] < s.x or h[i] > s.c) if bull else (h[i] > s.x or l[i] < s.c)
        if invalido or i - s.t0 > MAX_ESPERA:
            s.st = 0
        else:
            toque = l[i] <= s.d if bull else h[i] >= s.d
            if toque:
                s.st = 2
                s.cnt = 0
    if s.st == 2:
        rsi_ok = (not USAR_RSI) or ((rsi_v[i] <= RSI_UMBRAL) if bull else (rsi_v[i] >= 100 - RSI_UMBRAL))
        if rsi_ok:
            dirv = 1.0 if bull else -1.0
            xa = abs(s.a - s.x)
            entry = float(c[i])
            sl = s.x - dirv * SL_EXTRA * xa
            tp1 = s.d + TP1_FIB * (s.a - s.d)
            tp2 = s.d + TP2_FIB * (s.a - s.d)
            valido = (sl < entry < tp1) if bull else (tp1 < entry < sl)
            if valido:
                senal = Senal(idx=i, fecha=fecha, tipo="COMPRA" if bull else "VENTA",
                              entrada=entry, stop=float(sl), tp1=float(tp1), tp2=float(tp2),
                              detalle=(f"Bat {'alcista' if bull else 'bajista'} | RSI(14): {rsi_v[i]:.1f}\n"
                                       f"X {px(s.x)} | A {px(s.a)} | B {px(s.b)} | C {px(s.c)} | D {px(s.d)}"))
            s.st = 0
        else:
            s.cnt += 1
            if s.cnt > N_CONF:
                s.st = 0
    return senal


def senales(df: pd.DataFrame) -> list:
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    rsi_v = rsi(df["Close"], RSI_LEN).to_numpy()
    ph, pl = pivotes(h, l, PIV_LEN, PIV_LEN)
    fechas = [str(pd.Timestamp(x).date()) for x in df.index]

    pivs: list = []                    # (precio, barra, tipo)
    bull_s, bear_s = _Estado(), _Estado()
    out = []
    for i in range(len(df)):
        # --- Deteccion del patron (seccion 5 del Pine) ---
        nuevo = False
        if not np.isnan(ph[i]):
            nuevo = _add_pivot(pivs, float(ph[i]), i - PIV_LEN, 1) or nuevo
        if not np.isnan(pl[i]):
            nuevo = _add_pivot(pivs, float(pl[i]), i - PIV_LEN, -1) or nuevo
        if nuevo and len(pivs) >= 4:
            bull = pivs[-1][2] == 1
            px, pa, pb, pc = (pivs[k][0] for k in (-4, -3, -2, -1))
            ok, nivel_d = _check_bat(px, pa, pb, pc, bull)
            s = bull_s if bull else bear_s
            # El precio aun no debe haber llegado a D desde que se formo C
            lo_rec = l[max(0, i - PIV_LEN):i + 1].min()
            hi_rec = h[max(0, i - PIV_LEN):i + 1].max()
            aun_no_d = lo_rec > nivel_d if bull else hi_rec < nivel_d
            if ok and aun_no_d and s.st != 2:
                s.st, s.x, s.a, s.b, s.c, s.d = 1, px, pa, pb, pc, nivel_d
                s.t0, s.cnt = i, 0

        # --- Condiciones de compra y venta (seccion 6 del Pine) ---
        for s, bull in ((bull_s, True), (bear_s, False)):
            sig = _procesar(s, bull, i, h, l, c, rsi_v, fechas[i])
            if sig:
                out.append(sig)
    return out
