"""Engulfing (vela envolvente) - port de 'Engulfing Pro V1' (Pine) a velas DIARIAS.

Envolvente alcista: vela previa bajista + vela actual alcista cuyo CUERPO cubre el cuerpo
anterior, con cierre sobre la EMA y RSI de la vela previa en zona baja. La bajista es simetrica.
"""
import pandas as pd

from core import Senal, atr, ema, rsi

NAME = "Engulfing"
MIN_BARS = 220

# --- Parametros (iguales a los inputs del Pine) ---
MIN_CUERPO = 0.8         # cuerpo minimo de la vela envolvente (multiplo del ATR)
USAR_SOMBRAS = False     # exigir que tambien envuelva las sombras
USAR_TEND = True
EMA_LEN = 200
USAR_RSI = True
RSI_LEN = 14
RSI_UMBRAL = 45          # RSI de la vela previa: compra <= umbral | venta >= 100 - umbral
ATR_LEN = 14
SL_HOLGURA = 0.10        # multiplo del ATR
MAX_RIESGO = 3.0         # multiplo del ATR
TP1_R = 1.0
TP2_R = 2.0


def senales(df: pd.DataFrame) -> list:
    o = df["Open"].to_numpy(float)
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    atr_v = atr(df, ATR_LEN).to_numpy()
    ema_v = ema(df["Close"], EMA_LEN).to_numpy()
    rsi_v = rsi(df["Close"], RSI_LEN).to_numpy()
    fechas = [str(pd.Timestamp(x).date()) for x in df.index]

    out = []
    for i in range(1, len(df)):
        cuerpo = abs(c[i] - o[i])
        cuerpo_prev = abs(c[i - 1] - o[i - 1])
        cuerpo_ok = cuerpo >= MIN_CUERPO * atr_v[i] and cuerpo > cuerpo_prev
        sombras_ok = (not USAR_SOMBRAS) or (h[i] > h[i - 1] and l[i] < l[i - 1])
        if not (cuerpo_ok and sombras_ok):
            continue

        env_alcista = c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1] and o[i] <= c[i - 1]
        env_bajista = c[i - 1] > o[i - 1] and c[i] < o[i] and c[i] <= o[i - 1] and o[i] >= c[i - 1]
        if env_alcista:
            bull = True
        elif env_bajista:
            bull = False
        else:
            continue

        tend_ok = (not USAR_TEND) or (c[i] > ema_v[i] if bull else c[i] < ema_v[i])
        rsi_ok = (not USAR_RSI) or (rsi_v[i - 1] <= RSI_UMBRAL if bull else rsi_v[i - 1] >= 100 - RSI_UMBRAL)
        # Stop detras del patron completo (las dos velas)
        if bull:
            sl = min(l[i], l[i - 1]) - SL_HOLGURA * atr_v[i]
            riesgo = c[i] - sl
        else:
            sl = max(h[i], h[i - 1]) + SL_HOLGURA * atr_v[i]
            riesgo = sl - c[i]
        valido = 0 < riesgo <= MAX_RIESGO * atr_v[i]

        if tend_ok and rsi_ok and valido:
            dirv = 1.0 if bull else -1.0
            entry = float(c[i])
            out.append(Senal(idx=i, fecha=fechas[i], tipo="COMPRA" if bull else "VENTA",
                             entrada=entry, stop=float(sl),
                             tp1=entry + dirv * TP1_R * riesgo, tp2=entry + dirv * TP2_R * riesgo,
                             detalle=(f"Envolvente {'alcista' if bull else 'bajista'} | RSI previo: {rsi_v[i - 1]:.1f}\n"
                                      f"EMA({EMA_LEN}): {ema_v[i]:.2f} | Riesgo: {riesgo:.2f}")))
    return out
