"""Endpoint de predicciones: GET /api/predicciones?uid=..."""
from flask import Blueprint, request, jsonify

from app.services import firestore_service
from app.services.predicciones_service import generar_prediccion_futura

predicciones_bp = Blueprint("predicciones", __name__)


@predicciones_bp.route("/predicciones", methods=["GET"])
def get_predicciones():
    """Proyecciones de riesgo para 7, 14 y 30 días bajo 3 escenarios.
    ---
    tags:
      - Dashboard
    parameters:
      - in: query
        name: uid
        required: true
        type: string
        description: uid de Firebase Auth del usuario
    responses:
      200:
        description: >
          Tendencia, horizontes (7/14/30 d) y escenarios (actual/mejora/saludable)
      400:
        description: Falta el uid
      404:
        description: El usuario no tiene recolecciones previas
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return jsonify({
            "error": "La persistencia en Firestore no está disponible.",
            "detalle": firestore_service.estado().get("error"),
        }), 503

    uid = (request.args.get("uid") or "").strip()
    if not uid:
        return jsonify({"error": "Falta el parámetro 'uid'."}), 400

    recs = firestore_service.obtener_recolecciones(uid, limite=10) or []
    if not recs:
        return jsonify({
            "error": "sin_datos",
            "mensaje": "El usuario no tiene recolecciones previas.",
        }), 404

    cfg         = firestore_service.obtener_config(uid) or {}
    meta_activa = firestore_service.obtener_meta_activa(uid)
    ultima      = recs[0]

    resultado = generar_prediccion_futura(
        variables=ultima.get("variables") or {},
        extras=ultima.get("extras") or {},
        config=cfg,
        historial=recs,
        prediccion_actual=ultima.get("prediccion") or {},
        meta_activa=meta_activa,
    )

    return jsonify({"uid": uid, **resultado})
