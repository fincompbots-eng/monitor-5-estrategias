"""Lanzador comun de los 5 bots (velas DIARIAS ya cerradas).

Uso:
    python run_bot.py bat
    python run_bot.py inside_bar --dry-run          # no envia ni guarda estado
    python run_bot.py engulfing --historial 250     # lista senales de las ultimas 250 velas
    python run_bot.py pin_bar --test-telegram       # solo prueba la conexion
    python run_bot.py bat --demo                    # 1 mensaje de ejemplo con una senal HISTORICA

Variables de entorno:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (GitHub Secrets)
    TICKERS         lista separada por comas (ej. "NVDA,AAPL,BTC-USD,GC=F,EURUSD=X")
    STATE_FILE      por defecto state/<estrategia>.json
    REPORTE_DIARIO  "1" (por defecto) envia un reporte de cierre por dia; "0" lo desactiva
"""
import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from core import (LOG, NY, descargar_diario, mensaje_reporte, mensaje_senal, px,
                  read_state, rsi, telegram_send, write_state)
from strategies import ESTRATEGIAS

TICKERS = [x.strip().upper() for x in os.getenv("TICKERS", "NVDA,AAPL,MSFT").split(",") if x.strip()]
DIAS_MAX_SENAL = 4   # no alertar por velas antiguas tras interrupciones largas


def _dias_desde(fecha: str) -> int:
    return (datetime.now(NY).date() - datetime.strptime(fecha, "%Y-%m-%d").date()).days


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("estrategia", choices=sorted(ESTRATEGIAS))
    parser.add_argument("--test-telegram", action="store_true", help="Enviar mensaje de prueba")
    parser.add_argument("--dry-run", action="store_true", help="No enviar ni guardar estado")
    parser.add_argument("--historial", type=int, default=0,
                        help="Listar las senales de las ultimas N velas (no envia nada)")
    parser.add_argument("--demo", action="store_true",
                        help="Enviar UN mensaje de ejemplo con la senal HISTORICA mas reciente (no es vigente)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    mod = ESTRATEGIAS[args.estrategia]
    state_path = Path(os.getenv("STATE_FILE", f"state/{args.estrategia}.json"))
    reporte_diario = os.getenv("REPORTE_DIARIO", "1") == "1"

    if args.test_telegram:
        telegram_send(f"✅ Bot {mod.NAME} conectado correctamente a Telegram.")
        LOG.info("Prueba de Telegram enviada")
        return

    state = read_state(state_path)
    updated = False
    failures = 0
    filas = []        # (ticker, fecha_vela, cierre, cambio %, rsi, tipo de senal | None)
    candidatas = []   # solo para --demo: (fecha, ticker, senal)

    for ticker in TICKERS:
        try:
            df = descargar_diario(ticker)
            if len(df) < mod.MIN_BARS:
                raise ValueError(f"Se necesitan al menos {mod.MIN_BARS} velas de historial")
            sigs = mod.senales(df)
            n = len(df)

            if args.demo:
                if sigs:
                    candidatas.append((sigs[-1].fecha, ticker, sigs[-1]))
                    LOG.info("%s: ultima señal histórica %s %s", ticker, sigs[-1].fecha, sigs[-1].tipo)
                else:
                    LOG.info("%s: sin señales históricas en los datos descargados", ticker)
                continue

            if args.historial:
                recientes = [s for s in sigs if s.idx >= n - args.historial]
                for s in recientes:
                    LOG.info("HISTORIAL %s %s | %s | entrada %s | stop %s | TP1 %s | TP2 %s",
                             ticker, s.fecha, s.tipo, px(s.entrada), px(s.stop), px(s.tp1), px(s.tp2))
                LOG.info("%s: %d señales en las últimas %d velas", ticker, len(recientes), args.historial)
                continue

            ultima = sigs[-1] if sigs and sigs[-1].idx == n - 1 else None
            fecha = str(pd.Timestamp(df.index[-1]).date())
            cierre = float(df["Close"].iloc[-1])
            cambio = (cierre / float(df["Close"].iloc[-2]) - 1) * 100
            rsi14 = float(rsi(df["Close"], 14).iloc[-1])
            LOG.info("%s %s | cierre %s | RSI %.1f | señal %s", ticker, fecha, px(cierre), rsi14,
                     ultima.tipo if ultima else "ninguna")
            filas.append((ticker, fecha, cierre, cambio, rsi14, ultima.tipo if ultima else None))

            if not ultima:
                continue
            if _dias_desde(fecha) > DIAS_MAX_SENAL:
                LOG.info("Señal antigua omitida: %s", ticker)
                continue
            key = f"{ticker}:{ultima.fecha}:{ultima.tipo}"
            if key in state:
                continue
            msg = mensaje_senal(mod.NAME, ticker, ultima)
            if args.dry_run:
                LOG.info("DRY RUN: %s", msg)
            else:
                telegram_send(msg)
                state[key] = datetime.now(NY).isoformat()
                updated = True
        except Exception as exc:
            failures += 1
            LOG.error("Error en %s: %s", ticker, exc)

    # --- Modo demostracion: un solo mensaje, claramente marcado como historico ---
    if args.demo:
        if candidatas:
            _, ticker, s = max(candidatas, key=lambda x: x[0])
            msg = ("🧪 DEMOSTRACIÓN: ejemplo de una señal HISTÓRICA, no es una señal vigente.\n"
                   + mensaje_senal(mod.NAME, ticker, s))
            if args.dry_run:
                LOG.info("DRY RUN: %s", msg)
            else:
                telegram_send(msg)
                LOG.info("Mensaje de demostración enviado (%s %s)", ticker, s.fecha)
        else:
            LOG.info("No hay señales históricas para mostrar.")
        if failures:
            raise SystemExit(f"Fallaron {failures} símbolos. Revisar logs.")
        return

    # --- Reporte de cierre: uno por dia, solo con datos completos de todos los activos ---
    if filas and not failures and not args.historial and reporte_diario:
        fecha_rep = max(f[1] for f in filas)   # fecha de la vela mas reciente entre los activos
        clave = f"reporte:{fecha_rep}"
        if clave not in state and _dias_desde(fecha_rep) <= DIAS_MAX_SENAL:
            msg = mensaje_reporte(mod.NAME, fecha_rep, filas)
            try:
                if args.dry_run:
                    LOG.info("DRY RUN: %s", msg)
                else:
                    telegram_send(msg)
                    state[clave] = datetime.now(NY).isoformat()
                    updated = True
            except Exception as exc:
                failures += 1
                LOG.error("Error enviando el reporte: %s", exc)

    if updated:
        write_state(state_path, state)
    if failures:
        raise SystemExit(f"Fallaron {failures} operaciones. Revisar logs.")


if __name__ == "__main__":
    main()
