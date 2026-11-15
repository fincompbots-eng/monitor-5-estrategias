"""Doble Suelo / Doble Techo - port de 'Double Top Bottom Pro V1' (Pine) a velas DIARIAS.

Doble suelo: dos minimos casi iguales; el cuello es el maximo entre ambos.
Doble techo: dos maximos casi iguales; el cuello es el minimo entre ambos.
Senal: cierre mas alla del cuello (maquina de estados: 0 = sin patron | 1 = esperando ruptura).
El historial se recorre vela a vela en cada ejecucion (igual que en bat.py).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import Senal, atr, pivotes, px, rsi

NAME = "Doble Suelo/Techo"
MIN_BARS = 120

# --- Parametros (iguales a los inputs del Pine) ---
PIV_LEN = 5          # barras a cada lado del pivote
TOL_ATR = 0.5        # tolerancia entre los dos extremos (multiplo del ATR)
SEP_MIN = 8          # separacion minima entre extremos (barras)
SEP_MAX = 80         # separacion maxima entre extremos (barras)
ALTO_MIN = 1.0       # altura minima del patron (multiplo del ATR)
MAX_ESPERA = 30      # barras maximas para la ruptura del cuello
USAR_RSI = True
RSI_LEN = 14
RSI_UMBRAL = 50      # compra: RSI >= umbral | venta: RSI <= 100 - umbral
ATR_LEN = 14
SL_HOLGURA = 0.10    # multiplo del ATR
TP1_MOV = 0.5        # fraccion de la altura, medida desde el cuello
TP2_MOV = 1.0


@dataclass
class _Estado:
    st: int = 0
    e1: float = np.nan
    e2: float = np.nan
    neck: float = np.nan
    t0: int = 0


def _procesar(s: _Estado, bull: bool, i: int, c, rsi_v, atr_i: float, fecha: str):
    """Maquina de estados de un patron (doble suelo o doble techo) en la vela cerrada i."""
    senal = None
    if s.st == 1:
        extremo = min(s.e1, s.e2) if bull else max(s.e1, s.e2)
        invalido = c[i] < extremo - TOL_ATR * atr_i if bull else c[i] > extremo + TOL_ATR * atr_i
        if invalido or i - s.t0 > MAX_ESPERA:
            s.st = 0
        else:
            rompe = c[i] > s.neck if bull else c[i] < s.neck
            if rompe:
                rsi_ok = (not USAR_RSI) or (rsi_v[i] >= RSI_UMBRAL if bull else rsi_v[i] <= 100 - RSI_UMBRAL)
                if rsi_ok:
                    dirv = 1.0 if bull else -1.0
                    entry = float(c[i])
                    sl = extremo - dirv * SL_HOLGURA * atr_i
                    alto = abs(s.neck - extremo)
                    tp1 = s.neck + dirv * TP1_MOV * alto
                    tp2 = s.neck + dirv * TP2_MOV * alto
                    valido = (sl < entry < tp1) if bull else (tp1 < entry < sl)
                    if valido:
                        senal = Senal(idx=i, fecha=fecha, tipo="COMPRA" if bull else "VENTA",
                                      entrada=entry, stop=float(sl), tp1=float(tp1), tp2=float(tp2),
                                      detalle=(f"{'Doble suelo' if bull else 'Doble techo'} | RSI(14): {rsi_v[i]:.1f}\n"
                                               f"Extremos {px(s.e1)} / {px(s.e2)} | Cuello {px(s.neck)}"))
                s.st = 0
    return senal


def senales(df: pd.DataFrame) -> list:
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    rsi_v = rsi(df["Close"], RSI_LEN).to_numpy()
    atr_v = atr(df, ATR_LEN).to_numpy()
    ph, pl = pivotes(h, l, PIV_LEN, PIV_LEN)
    fechas = [str(pd.Timestamp(x).date()) for x in df.index]

    low_a = low_ai = low_b = low_bi = None       # ultimos dos minimos
    high_a = high_ai = high_b = high_bi = None   # ultimos dos maximos
    bull_s, bear_s = _Estado(), _Estado()
    out = []
    for i in range(len(df)):
        atr_i = atr_v[i]
        cierres = c[max(0, i - PIV_LEN):i + 1]   # equivale a ta.highest/lowest(close, pivLen + 1)

        # --- Doble suelo: el cuello es el maximo entre ambos minimos ---
        if not np.isnan(pl[i]):
            low_a, low_ai = low_b, low_bi
            low_b, low_bi = float(pl[i]), i - PIV_LEN
            if low_a is not None:
                sep = low_bi - low_ai
                parejos = abs(low_b - low_a) <= TOL_ATR * atr_i
                if SEP_MIN <= sep <= SEP_MAX and parejos:
                    neck = float(h[low_ai:i - PIV_LEN + 1].max())
                    alto = neck - max(low_a, low_b)
                    # Aun no se debe haber cerrado por encima del cuello
                    if alto >= ALTO_MIN * atr_i and cierres.max() < neck:
                        bull_s.st, bull_s.e1, bull_s.e2, bull_s.neck, bull_s.t0 = 1, low_a, low_b, neck, i

        # --- Doble techo: el cuello es el minimo entre ambos maximos ---
        if not np.isnan(ph[i]):
            high_a, high_ai = high_b, high_bi
            high_b, high_bi = float(ph[i]), i - PIV_LEN
            if high_a is not None:
                sep = high_bi - high_ai
                parejos = abs(high_b - high_a) <= TOL_ATR * atr_i
                if SEP_MIN <= sep <= SEP_MAX and parejos:
                    neck = float(l[high_ai:i - PIV_LEN + 1].min())
                    alto = min(high_a, high_b) - neck
                    if alto >= ALTO_MIN * atr_i and cierres.min() > neck:
                        bear_s.st, bear_s.e1, bear_s.e2, bear_s.neck, bear_s.t0 = 1, high_a, high_b, neck, i

        # --- Condiciones de compra y venta ---
        for s, bull in ((bull_s, True), (bear_s, False)):
            sig = _procesar(s, bull, i, c, rsi_v, atr_i, fechas[i])
            if sig:
                out.append(sig)
    return out
