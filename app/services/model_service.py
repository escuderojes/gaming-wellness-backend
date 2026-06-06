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

# Orden EXACTO de features con el que se entreno el modelo.
# Solo los indicadores conductuales con señal real. THT, TP y NPPD se
# recolectan como variables extra (dashboard) pero NO entran al modelo.
FEATURES = ["ND", "HPD", "DCJ"]

# Clasificacion binaria (ICOGS-A): 0 = "Sin riesgo", 1 = "Riesgo".
# El score 0-100 es la probabilidad de la clase "Riesgo".
CLASE_RIESGO = "Riesgo"

# Niveles visuales derivados del score (capa de presentacion).
# El modelo predice P(Riesgo); el score 0-100 se segmenta en 3 bandas
# deducibles a partir del criterio del ICOGS-A: el corte de riesgo es el
# percentil 75 (Alto), y el punto medio (Medio) corresponde a la mediana
# del puntaje, lo que en el espacio del score equivale a 50.
#   Bajo  : score < 50           (por debajo de la mediana de riesgo)
#   Medio : 50 <= score < 75     (entre la mediana y el P75)
#   Alto  : score >= 75          (en o por encima del P75)
UMBRAL_ALTO = 75
UMBRAL_MEDIO = 50


def nivel_visual(score):
    """Nivel de presentacion (Alto/Medio/Bajo) derivado del score 0-100."""
    if score >= UMBRAL_ALTO:
        return "Alto"
    if score >= UMBRAL_MEDIO:
        return "Medio"
    return "Bajo"


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
    clase = str(encoder.inverse_transform([pred_idx])[0])

    probabilidades = {
        str(cls): round(float(p), 4)
        for cls, p in zip(encoder.classes_, proba)
    }

    # Score 0-100 = probabilidad de la clase "Riesgo".
    score = round(probabilidades.get(CLASE_RIESGO, 0.0) * 100)

    # Nivel visual (Alto/Medio/Bajo) derivado del score, y bandera
    # binaria de riesgo (clase predicha por el modelo) para las alertas.
    nivel = nivel_visual(score)
    en_riesgo = clase == CLASE_RIESGO

    # Confianza del modelo en su clasificacion = probabilidad de la clase
    # predicha (0-100). Es la metrica honesta para un clasificador binario:
    # "que tan seguro esta el modelo del estado asignado".
    confianza = round(max(probabilidades.values()) * 100, 1) if probabilidades else 0.0

    return {
        "nivel": nivel,
        "nivel_label": nivel.upper(),
        "clase": clase,
        "en_riesgo": en_riesgo,
        "score": score,
        "confianza": confianza,
        "probabilidades": probabilidades,
    }
