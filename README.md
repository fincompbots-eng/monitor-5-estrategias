# Monitor de 5 estrategias con Python, GitHub Actions y Telegram (v2)

Un repositorio, **5 bots de Telegram**, **5 workflows** y **5 estrategias** sobre velas **diarias cerradas**.
Cada bot analiza 7 activos y avisa por Telegram. El sistema **emite señales; no ejecuta operaciones**.

| Bot | Estrategia | Workflow | Secret del token | Hora (UTC) |
|---|---|---|---|---|
| 1 | Bat (patrón armónico + RSI) | `bot_bat.yml` | `TOKEN_BAT` | 23:17 |
| 2 | Inside Bar | `bot_inside_bar.yml` | `TOKEN_INSIDE_BAR` | 23:22 |
| 3 | Engulfing | `bot_engulfing.yml` | `TOKEN_ENGULFING` | 23:27 |
| 4 | Pin Bar | `bot_pin_bar.yml` | `TOKEN_PIN_BAR` | 23:32 |
| 5 | Doble Suelo / Techo | `bot_double_top_bottom.yml` | `TOKEN_DOBLE` | 23:37 |

## Activos (variable `TICKERS` de cada workflow)

`NVDA, AAPL, MSFT, BTC-USD, ETH-USD, GC=F, EURUSD=X`

| Tipo | Símbolo | ¿Genera velas nuevas en fin de semana? |
|---|---|---|
| Acciones | NVDA, AAPL, MSFT | No (bolsa cerrada) |
| Cripto | BTC-USD, ETH-USD | **Sí, todos los días** |
| Oro (futuro) | GC=F | No |
| Divisa | EURUSD=X | No |

Otros símbolos de Yahoo Finance: `GBPUSD=X`, `USDJPY=X`, `USDCOP=X`, `SOL-USD`, `XAUUSD=X` (el oro spot suele fallar; usa `GC=F`).

Para cambiar los activos de un bot, edita la línea `TICKERS:` de su workflow.

## Estructura

```
monitor-5-estrategias/
├── core.py               # datos, indicadores, Telegram y estado
├── run_bot.py            # lanzador común: python run_bot.py <estrategia>
├── requirements.txt
├── strategies/           # bat, inside_bar, engulfing, pin_bar, double_top_bottom
├── state/                # un JSON por bot (alertas ya enviadas)
└── .github/workflows/    # un workflow por bot
```

## Puesta en marcha

1. **Telegram**: crea 5 bots con @BotFather (`/newbot`), guarda los 5 tokens en privado y envía `/start` a cada uno. Obtén tu Chat ID una sola vez con `getUpdates`.
2. **GitHub**: repositorio **privado** con el *contenido* de esta carpeta en la raíz (incluye `.github/workflows/`, `state/` y `strategies/`).
3. **Secrets** (Settings → Secrets and variables → Actions → *Repository secrets*): `TOKEN_BAT`, `TOKEN_INSIDE_BAR`, `TOKEN_ENGULFING`, `TOKEN_PIN_BAR`, `TOKEN_DOBLE` y `TELEGRAM_CHAT_ID`.
4. **Permisos**: Settings → Actions → General → Workflow permissions → *Read and write permissions*.
5. **Probar Telegram** en cada bot: Actions → workflow → Run workflow → `test_telegram`.
6. **Ejecución real**: Run workflow con todo desactivado. Revisa en el log una línea por activo.

## Opciones al ejecutar manualmente (Run workflow)

| Opción | Qué hace |
|---|---|
| `test_telegram` | Envía "Bot conectado" y termina. No descarga datos. |
| `demo` | Envía **un** mensaje con la señal **histórica** más reciente, marcado como DEMOSTRACIÓN. No es una señal vigente y no se guarda en el estado. |
| `historial` = `250` | Lista en el log las señales de las últimas 250 velas. No envía nada. |

## Mensajes que envía cada bot

- **Alerta por señal**: activo, fecha de la vela, entrada (cierre), stop, TP1 y TP2. Una por señal, sin duplicados.
- **Reporte de cierre**: uno por día, con cierre, cambio, RSI y señal de cada activo. Si un activo no tiene vela nueva (mercado cerrado), aparece con su fecha entre corchetes, por ejemplo `NVDA [11-13]`. Se desactiva con `REPORTE_DIARIO: "0"`.

Si repites una ejecución el mismo día no se vuelve a enviar el reporte ni la alerta: es el anti-duplicados (`state/<bot>.json`).

`VENTA` es un aviso bajista, no necesariamente abrir una posición corta.

## Velas cerradas y horarios

- **Acciones**: se usa la última vela cerrada de Nueva York.
- **Cripto, divisas y oro**: la vela del día en curso se descarta y se analiza la del día anterior (alertas con un día de desfase, a cambio de no analizar velas abiertas).
- El cron corre **todos los días** para no perder las velas de cripto del fin de semana.

## Evidencias sugeridas para la entrega

1. Captura de **Actions** con el job en *Success*.
2. Log de *Analizar acciones y enviar alertas* con una línea por activo (fecha de vela, cierre, RSI, señal).
3. Captura del mensaje de **prueba de Telegram** (`test_telegram`) sin mostrar tokens.
4. Captura del **reporte de cierre** en Telegram.
5. Si no hubo señal vigente: explica por qué (cruce, RSI y filtro de tendencia no coincidieron). Si quieres mostrar el formato de una alerta, usa `demo` y **preséntalo como demostración con señal histórica**.
6. Descripción de cómo `state/<bot>.json` evita duplicados.

## Limitaciones

- Datos de Yahoo Finance: pueden retrasarse o fallar. GitHub puede aplazar o, rara vez, omitir una ejecución programada.
- Estrategias educativas: sin costos, liquidez, gestión monetaria ni backtesting.
- Pruébalo localmente con `python run_bot.py bat --dry-run`.
