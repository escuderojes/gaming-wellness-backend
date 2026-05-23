"""Servicio del modelo predictivo.

Centraliza la carga de artefactos (modelo, scaler, encoder) y la
funcion de prediccion, para que tanto el endpoint /api/predict como
el job de recoleccion la reutilicen sin duplicar codigo.
"""
import joblib
import pandas as pd
from functools import lru_cache
from pathlib import Path

from sklearn.linear_model import LogisticRegression

# services -> app -> Backend (donde estan los .pkl)
BASE = Path(__file__).resolve().parents[2]

# Orden EXACTO de variables con el que se entreno el modelo XGBoost.
FEATURES = ["THT", "ND", "TP", "HPD", "NPPD", "DCJ"]

# Severidad de referencia de cada clase para derivar el score 0-100.
SEVERIDAD = {"Bajo": 15, "Medio": 55, "Alto": 90}


@lru_cache(maxsize=1)
def load_artifacts():
    """Carga modelo, encoder y scaler una sola vez (cacheado)."""
    model = joblib.load(BASE / "modelo_gaming.pkl")
    encoder = joblib.load(BASE / "encoder.pkl")
    try:
        scaler = joblib.load(BASE / "scaler.pkl")
    except Exception:
        scaler = None
    return model, scaler, encoder


def predecir(fila):
    """Recibe un dict con las 6 FEATURES y devuelve la prediccion.

    Devuelve: {nivel, nivel_label, score, probabilidades}.
    """
    model, scaler, encoder = load_artifacts()

    X = pd.DataFrame([{f: float(fila[f]) for f in FEATURES}], columns=FEATURES)

    # LogisticRegression requiere escalado; los modelos de arboles no.
    if isinstance(model, LogisticRegression) and scaler is not None:
        X_in = scaler.transform(X)
    else:
        X_in = X

    pred_idx = int(model.predict(X_in)[0])
    proba = model.predict_proba(X_in)[0]
    nivel = str(encoder.inverse_transform([pred_idx])[0])

    probabilidades = {
        str(cls): round(float(p), 4)
        for cls, p in zip(encoder.classes_, proba)
    }

    score = round(sum(
        probabilidades.get(cls, 0.0) * sev
        for cls, sev in SEVERIDAD.items()
    ))

    return {
        "nivel": nivel,
        "nivel_label": nivel.upper(),
        "score": score,
        "probabilidades": probabilidades,
    }
