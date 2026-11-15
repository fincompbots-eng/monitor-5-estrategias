"""Inside Bar - port de 'Inside Bar Pro V1' (Pine) a velas DIARIAS.

Madre = vela previa. Inside bar = vela cuyo rango queda dentro del de la madre.
Se espera una ruptura de la madre con CIERRE, a favor de la EMA.
"""
import numpy as np
import pandas as pd

from core import Senal, atr, ema, px

NAME = "Inside Bar"
MIN_BARS = 80

# --- Parametros (iguales a los inputs del Pine) ---
MIN_MADRE = 0.8          # rango minimo de la madre (multiplo del ATR)
MAX_ESPERA = 5           # barras maximas para esperar la ruptura
PERMITIR_IGUAL = False   # permitir maximo/minimo igual al de la madre
USAR_TEND = True
EMA_LEN = 50
ATR_LEN = 14
SL_MODO = "extremo"      # "extremo" de la madre | "mitad" de la madre
SL_HOLGURA = 0.10        # multiplo del ATR
MAX_RIESGO = 3.0         # multiplo del ATR
TP1_R = 1.0
TP2_R = 2.0


def senales(df: pd.DataFrame) -> list:
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    atr_v = atr(df, ATR_LEN).to_numpy()
    ema_v = ema(df["Close"], EMA_LEN).to_numpy()
    fechas = [str(pd.Timestamp(x).date()) for x in df.index]

    activo = False
    m_high = m_low = np.nan
    m_bar = -1
    edad = 0
    out = []
    for i in range(1, len(df)):
        # A) Seguimiento de un setup activo (a partir de la vela siguiente a la inside bar)
        if activo and i > m_bar:
            edad += 1
            rompe_arriba = c[i] > m_high
            rompe_abajo = c[i] < m_low
            if rompe_arriba or rompe_abajo:
                bull = bool(rompe_arriba)
                tend_ok = (not USAR_TEND) or (c[i] > ema_v[i] if bull else c[i] < ema_v[i])
                sl_base = (m_low if bull else m_high) if SL_MODO == "extremo" else (m_high + m_low) / 2
                sl = sl_base - SL_HOLGURA * atr_v[i] if bull else sl_base + SL_HOLGURA * atr_v[i]
                entry = float(c[i])
                riesgo = abs(entry - sl)
                valido = entry > sl if bull else entry < sl
                if tend_ok and valido and 0 < riesgo <= MAX_RIESGO * atr_v[i]:
                    dirv = 1.0 if bull else -1.0
                    out.append(Senal(idx=i, fecha=fechas[i], tipo="COMPRA" if bull else "VENTA",
                                     entrada=entry, stop=float(sl),
                                     tp1=entry + dirv * TP1_R * riesgo, tp2=entry + dirv * TP2_R * riesgo,
                                     detalle=(f"Ruptura de la vela madre ({px(m_low)} - {px(m_high)})\n"
                                              f"EMA({EMA_LEN}): {px(ema_v[i])} | Riesgo: {px(riesgo)}")))
                activo = False
            elif edad > MAX_ESPERA:
                activo = False

        # B) Busqueda de una nueva inside bar
        if not activo:
            inside = (h[i] <= h[i - 1] and l[i] >= l[i - 1]) if PERMITIR_IGUAL else (h[i] < h[i - 1] and l[i] > l[i - 1])
            madre_ok = (h[i - 1] - l[i - 1]) >= MIN_MADRE * atr_v[i - 1]
            if inside and madre_ok:
                activo = True
                m_high, m_low = h[i - 1], l[i - 1]
                m_bar = i
                edad = 0
    return out
