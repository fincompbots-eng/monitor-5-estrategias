# Monitor de 5 estrategias con Python, GitHub Actions y Telegram

Un repositorio, **5 bots de Telegram**, **5 workflows** y **5 estrategias** sobre velas **diarias cerradas**.
Cada bot analiza 3 acciones (por defecto NVDA, AAPL y MSFT) y avisa por Telegram. El sistema **emite señales; no ejecuta operaciones**.

| Bot | Estrategia | Workflow | Secret del token | Hora (UTC) |
|---|---|---|---|---|
| 1 | Bat (patrón armónico + RSI) | `bot_bat.yml` | `TOKEN_BAT` | 23:17 |
| 2 | Inside Bar | `bot_inside_bar.yml` | `TOKEN_INSIDE_BAR` | 23:22 |
| 3 | Engulfing | `bot_engulfing.yml` | `TOKEN_ENGULFING` | 23:27 |
| 4 | Pin Bar | `bot_pin_bar.yml` | `TOKEN_PIN_BAR` | 23:32 |
| 5 | Doble Suelo / Techo | `bot_double_top_bottom.yml` | `TOKEN_DOBLE` | 23:37 |

## Estructura

```
monitor-5-estrategias/
├── core.py               # datos, indicadores, Telegram y estado
├── run_bot.py            # lanzador común: python run_bot.py <estrategia>
├── requirements.txt
├── strategies/           # una estrategia por archivo (bat, inside_bar, engulfing, pin_bar, double_top_bottom)
├── state/                # un JSON por bot (alertas ya enviadas)
└── .github/workflows/    # un workflow por bot
```

## Puesta en marcha

1. **Telegram**: crea 5 bots con @BotFather (`/newbot`), guarda los 5 tokens en privado y envía `/start` a cada uno. Obtén tu Chat ID una sola vez con `getUpdates`; sirve para los 5 bots.
2. **GitHub**: crea un repositorio **privado** y sube *el contenido* de esta carpeta a la raíz (no la carpeta dentro de otra carpeta). Incluye `.github/workflows/` y `state/`.
3. **Secrets** (Settings → Secrets and variables → Actions): `TOKEN_BAT`, `TOKEN_INSIDE_BAR`, `TOKEN_ENGULFING`, `TOKEN_PIN_BAR`, `TOKEN_DOBLE` y `TELEGRAM_CHAT_ID`.
4. **Probar Telegram** en cada bot: Actions → elige el workflow → Run workflow → activa `test_telegram`.
5. **Ejecución real**: Run workflow con `test_telegram` desactivado. Revisa en el log una línea por acción.
6. **Ver señales pasadas** sin esperar: Run workflow con `historial` = `250`. Lista las señales de las últimas 250 velas y no envía nada.

## Cambiar las 3 acciones de un bot

En el workflow del bot, edita `TICKERS: "NVDA,AAPL,MSFT"`. Cada estrategia puede tener sus propias acciones.

## Qué mensajes envía cada bot

- **Alerta por señal**: ticker, fecha de la vela, entrada (cierre), stop, TP1 y TP2. Una por señal, sin duplicados.
- **Reporte de cierre**: una vez por sesión, con cierre, cambio diario, RSI y señal de cada acción. Se desactiva con `REPORTE_DIARIO: "0"`.

`VENTA` es un aviso bajista, no necesariamente abrir una posición corta.

## Cómo evita duplicados

`state/<bot>.json` guarda claves `TICKER:FECHA:SEÑAL` y `reporte:FECHA`. Cada bot tiene su propio archivo para que los 5 workflows no choquen al hacer commit. Las claves de más de 180 días se podan solas.

## Parámetros

Cada estrategia tiene sus parámetros como constantes al inicio de su archivo en `strategies/` (mismos nombres que los `input` del Pine). Edítalos ahí.

## Limitaciones

- Datos de Yahoo Finance: pueden retrasarse o fallar. GitHub puede aplazar o, rara vez, omitir una ejecución programada.
- Estrategias educativas: sin costos, liquidez, gestión monetaria ni backtesting. No evalúes una estrategia por un caso aislado.
- Pruébalo localmente con `python run_bot.py bat --dry-run`.
