"""Registro de las 5 estrategias. Cada modulo expone NAME, MIN_BARS y senales(df)."""
from . import bat, double_top_bottom, engulfing, inside_bar, pin_bar

ESTRATEGIAS = {
    "bat": bat,
    "inside_bar": inside_bar,
    "engulfing": engulfing,
    "pin_bar": pin_bar,
    "double_top_bottom": double_top_bottom,
}
