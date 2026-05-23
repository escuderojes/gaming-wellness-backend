from flask import Blueprint, request, jsonify

from app.services.model_service import FEATURES, predecir

prediction_bp = Blueprint("prediction", __name__)


@prediction_bp.route("/predict", methods=["POST"])
def predict():
    """Clasifica el nivel de riesgo de uso excesivo.
    ---
    tags:
      - Prediccion
    consumes:
      - application/json
    parameters:
      - in: body
        name: variables
        required: true
        description: Las 6 variables del modelo.
        schema:
          type: object
          required: [THT, ND, TP, HPD, NPPD, DCJ]
          properties:
            THT:  {type: number,  example: 45.0, description: Tiempo total de horas jugadas}
            ND:   {type: integer, example: 7,    description: Numero de dias con actividad}
            TP:   {type: integer, example: 70,   description: Total de partidas del periodo}
            HPD:  {type: number,  example: 6.4,  description: Horas promedio por dia}
            NPPD: {type: number,  example: 10,   description: Partidas promedio por dia}
            DCJ:  {type: integer, example: 7,    description: Dias consecutivos de juego}
    responses:
      200:
        description: Prediccion generada correctamente
      400:
        description: Faltan variables requeridas o un valor no es numerico
    """
    data = request.json or {}

    # 'TP' es el nombre del modelo; el colector lo llama 'TPP'. Se acepta alias.
    if "TP" not in data and "TPP" in data:
        data = {**data, "TP": data["TPP"]}

    faltantes = [f for f in FEATURES if f not in data]
    if faltantes:
        return jsonify({
            "error": "Faltan variables requeridas.",
            "requeridas": FEATURES,
            "faltantes": faltantes,
        }), 400

    try:
        fila = {f: float(data[f]) for f in FEATURES}
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Valor no numerico: {e}"}), 400

    resultado = predecir(fila)
    resultado["variables"] = fila
    return jsonify(resultado)
