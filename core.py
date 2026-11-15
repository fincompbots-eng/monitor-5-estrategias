"""Nucleo comun de los 5 bots: datos, indicadores, Telegram y estado.

Todo trabaja con velas DIARIAS ya cerradas (mismo criterio que el monitor EMA/RSI original).
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

LOG = logging.getLogger("monitor")
NY = ZoneInfo("America/New_York")


@dataclass
class Senal:
    """Una senal emitida en una vela cerrada (idx = posicion de la vela en el DataFrame)."""
    idx: int
    fecha: str
    tipo: str          # "COMPRA" | "VENTA"
    entrada: float
    stop: float
    tp1: float
    tp2: float
    detalle: str = ""


# =====================================
# INDICADORES (equivalentes a las funciones ta.* de Pine)
# =====================================

def ema(s: pd.Series, n: int) -> pd.Series:
    """Igual a ta.ema."""
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Igual a ta.rma: se siembra con la SMA de los primeros n valores validos."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    validos = np.where(~np.isnan(v))[0]
    if len(validos) >= n:
        ini = validos[0] + n - 1
        out[ini] = v[validos[0]:ini + 1].mean()
        for i in range(ini + 1, len(v)):
            out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return pd.Series(out, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI de Wilder (igual a ta.rsi)."""
    delta = close.diff()
    avg_g = rma(delta.clip(lower=0), n)
    avg_l = rma((-delta).clip(lower=0), n)
    rs = avg_g / avg_l.replace(0, np.nan)
    r = 100 - 100 / (1 + rs)
    r = r.mask((avg_l == 0) & (avg_g > 0), 100)
    r = r.mask((avg_g == 0) & (avg_l > 0), 0)
    r = r.mask((avg_g == 0) & (avg_l == 0), 50)
    return r


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Igual a ta.atr (RMA del rango verdadero)."""
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return rma(tr, n)


def pivotes(h: np.ndarray, l: np.ndarray, izq: int, der: int):
    """Equivalente a ta.pivothigh / ta.pivotlow.

    Devuelve (ph, pl) alineados a la vela de CONFIRMACION i: el pivote esta en i - der y solo
    se conoce der velas despues, asi no se usa informacion del futuro. (En empates exactos
    puede diferir marginalmente de Pine.)
    """
    n = len(h)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(izq + der, n):
        c = i - der
        if h[c] > h[c - izq:c].max() and h[c] >= h[c + 1:i + 1].max():
            ph[i] = h[c]
        if l[c] < l[c - izq:c].min() and l[c] <= l[c + 1:i + 1].min():
            pl[i] = l[c]
    return ph, pl


# =====================================
# DATOS
# =====================================

def es_24h(ticker: str) -> bool:
    """Cripto (BTC-USD), divisas (EURUSD=X) y futuros (GC=F): no siguen el horario de la bolsa."""
    return ticker.endswith(("-USD", "=X", "=F"))


def descargar_diario(ticker: str) -> pd.DataFrame:
    """OHLC diario de Yahoo Finance, solo con velas ya cerradas."""
    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=False,
                     progress=False, threads=False, multi_level_index=False, timeout=20)
    cols = ["Open", "High", "Low", "Close"]
    if df is None or df.empty or any(c not in df for c in cols):
        raise ValueError(f"No hay datos para {ticker}")
    df = df[cols].apply(pd.to_numeric, errors="coerce").dropna().astype(float)
    ultima = pd.Timestamp(df.index[-1]).date()
    if es_24h(ticker):
        # Cripto, divisas y futuros operan casi 24 h: la vela del dia sigue abierta -> usar la anterior.
        if ultima >= datetime.now(timezone.utc).date():
            df = df.iloc[:-1]
    else:
        # Acciones: si se ejecuta antes de las 17:00 NY, no usar la barra del dia (podria estar abierta).
        ny_now = datetime.now(NY)
        if ultima >= ny_now.date() and ny_now.hour < 17:
            df = df.iloc[:-1]
    if df.empty:
        raise ValueError("Sin barras cerradas")
    return df


# =====================================
# TELEGRAM
# =====================================

def telegram_send(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": message}, timeout=20)
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram no confirmo el envio")


def px(x: float) -> str:
    """Precio con decimales segun su magnitud (las divisas necesitan 4-5)."""
    if abs(x) >= 100:
        return f"{x:,.2f}"
    return f"{x:.4f}" if abs(x) >= 1 else f"{x:.5f}"


def mensaje_senal(nombre: str, ticker: str, s: Senal) -> str:
    icono = "🟢" if s.tipo == "COMPRA" else "🔴"
    zona = "" if es_24h(ticker) else " (Nueva York)"
    return (f"{icono} {s.tipo} | {ticker} | {nombre}\n"
            f"Vela cerrada: {s.fecha}{zona}\n"
            f"Entrada (cierre): {px(s.entrada)}\n"
            f"Stop: {px(s.stop)}\n"
            f"TP1: {px(s.tp1)} | TP2: {px(s.tp2)}\n"
            f"{s.detalle}\n"
            "Señal técnica informativa; no es una orden de inversión.")


def mensaje_reporte(nombre: str, fecha: str, filas: list) -> str:
    """filas = [(ticker, fecha_vela, cierre, cambio_pct, rsi14, tipo_senal | None), ...]"""
    lineas = [f"📊 Reporte de cierre | {nombre} | {fecha}"]
    hay_desfase = False
    for t, f, cierre, cambio, r, sig in filas:
        marca = ""
        if f != fecha:
            marca = f" [{f[5:]}]"
            hay_desfase = True
        lineas.append(f"{t}{marca}: {px(cierre)} ({cambio:+.1f}%) | RSI {r:.1f} | señal {sig or 'ninguna'}")
    if hay_desfase:
        lineas.append("[MM-DD] = última vela disponible de ese activo (mercado cerrado o día en curso).")
    lineas.append("Informativo; no es una orden de inversión.")
    return "\n".join(lineas)


# =====================================
# ESTADO (alertas ya enviadas)
# =====================================

def read_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _podar(state: dict, dias: int = 180) -> dict:
    """Elimina claves antiguas para que el archivo no crezca indefinidamente."""
    hoy = datetime.now(NY).date()
    nuevo = {}
    for k, v in state.items():
        try:
            f = datetime.strptime(k.split(":")[1], "%Y-%m-%d").date()
            if (hoy - f).days > dias:
                continue
        except (IndexError, ValueError):
            pass
        nuevo[k] = v
    return nuevo


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_podar(state), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
