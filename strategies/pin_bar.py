"""Pin Bar - port de 'Pin Bar Pro V1' (Pine) a velas DIARIAS.

Pin bar alcista (martillo): mecha inferior larga y cuerpo pequeno arriba.
Pin bar bajista (estrella fugaz): mecha superior larga y cuerpo pequeno abajo.
Con barrido: la mecha perfora el extremo reciente y el cierre lo recupera.
"""
import pandas as pd

from core import Senal, atr, ema, rsi

NAME = "Pin Bar"
MIN_BARS = 220

# --- Parametros (iguales a los inputs del Pine) ---
MIN_RANGO = 0.8          # rango minimo de la vela (multiplo del ATR)
MIN_MECHA = 0.60         # mecha minima (fraccion del rango total)
MAX_CUERPO = 0.35        # cuerpo maximo (fraccion del rango total)
USAR_BARRIDO = True      # exigir barrido del minimo/maximo reciente con cierre de rechazo
LOOKBACK = 20            # barras para definir el minimo/maximo reciente
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
    for i in range(max(LOOKBACK, 1), len(df)):
        rango = h[i] - l[i]
        cuerpo = abs(c[i] - o[i])
        mecha_inf = min(o[i], c[i]) - l[i]
        mecha_sup = h[i] - max(o[i], c[i])
        forma_ok = rango > 0 and rango >= MIN_RANGO * atr_v[i] and cuerpo <= MAX_CUERPO * rango
        if not forma_ok:
            continue

        # Minimo y maximo de las LOOKBACK velas ANTERIORES a la actual
        min_prev = l[i - LOOKBACK:i].min()
        max_prev = h[i - LOOKBACK:i].max()
        pin_alcista = mecha_inf >= MIN_MECHA * rango and ((not USAR_BARRIDO) or (l[i] < min_prev and c[i] > min_prev))
        pin_bajista = mecha_sup >= MIN_MECHA * rango and ((not USAR_BARRIDO) or (h[i] > max_prev and c[i] < max_prev))
        if pin_alcista:
            bull = True
        elif pin_bajista:
            bull = False
        else:
            continue

        tend_ok = (not USAR_TEND) or (c[i] > ema_v[i] if bull else c[i] < ema_v[i])
        rsi_ok = (not USAR_RSI) or (rsi_v[i - 1] <= RSI_UMBRAL if bull else rsi_v[i - 1] >= 100 - RSI_UMBRAL)
        if bull:
            sl = l[i] - SL_HOLGURA * atr_v[i]
            riesgo = c[i] - sl
        else:
            sl = h[i] + SL_HOLGURA * atr_v[i]
            riesgo = sl - c[i]
        valido = 0 < riesgo <= MAX_RIESGO * atr_v[i]

        if tend_ok and rsi_ok and valido:
            dirv = 1.0 if bull else -1.0
            entry = float(c[i])
            ref = min_prev if bull else max_prev
            out.append(Senal(idx=i, fecha=fechas[i], tipo="COMPRA" if bull else "VENTA",
                             entrada=entry, stop=float(sl),
                             tp1=entry + dirv * TP1_R * riesgo, tp2=entry + dirv * TP2_R * riesgo,
                             detalle=(f"Pin bar {'alcista (martillo)' if bull else 'bajista (estrella fugaz)'} | RSI previo: {rsi_v[i - 1]:.1f}\n"
                                      f"{'Minimo' if bull else 'Maximo'} de {LOOKBACK} velas: {ref:.2f} | EMA({EMA_LEN}): {ema_v[i]:.2f}")))
    return out
