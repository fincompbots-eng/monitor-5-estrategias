"""Nucleo comun de los 5 bots: datos, indicadores, Telegram y estado.

Todo trabaja con velas DIARIAS ya cerradas (mismo criterio que el monitor EMA/RSI original).
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
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

def descargar_diario(ticker: str) -> pd.DataFrame:
    """OHLC diario de Yahoo Finance, solo con velas ya cerradas."""
    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=False,
                     progress=False, threads=False, multi_level_index=False, timeout=20)
    cols = ["Open", "High", "Low", "Close"]
    if df is None or df.empty or any(c not in df for c in cols):
        raise ValueError(f"No hay datos para {ticker}")
    df = df[cols].apply(pd.to_numeric, errors="coerce").dropna().astype(float)
    # Si se ejecuta antes de las 17:00 NY, no usar la barra del dia, que podria estar abierta.
    ny_now = datetime.now(NY)
    if pd.Timestamp(df.index[-1]).date() >= ny_now.date() and ny_now.hour < 17:
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


def mensaje_senal(nombre: str, ticker: str, s: Senal) -> str:
    icono = "🟢" if s.tipo == "COMPRA" else "🔴"
    return (f"{icono} {s.tipo} | {ticker} | {nombre}\n"
            f"Vela cerrada: {s.fecha} (Nueva York)\n"
            f"Entrada (cierre): ${s.entrada:.2f}\n"
            f"Stop: ${s.stop:.2f}\n"
            f"TP1: ${s.tp1:.2f} | TP2: ${s.tp2:.2f}\n"
            f"{s.detalle}\n"
            "Señal técnica informativa; no es una orden de inversión.")


def mensaje_reporte(nombre: str, fecha: str, filas: list) -> str:
    """filas = [(ticker, cierre, cambio_pct, rsi14, tipo_senal | None), ...]"""
    lineas = [f"📊 Reporte de cierre | {nombre} | {fecha} (Nueva York)"]
    for t, cierre, cambio, r, sig in filas:
        lineas.append(f"{t}: ${cierre:.2f} ({cambio:+.1f}%) | RSI {r:.1f} | señal {sig or 'ninguna'}")
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
