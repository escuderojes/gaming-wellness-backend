"""Endpoint de metas automáticas: GET /api/metas?uid=..."""
from flask import Blueprint, request, jsonify

from app.services import firestore_service
from app.services.metas_service import calcular_meta, progreso_meta

metas_bp = Blueprint("metas", __name__)


@metas_bp.route("/metas", methods=["GET"])
def get_metas():
    """Meta activa del usuario y su historial de metas cumplidas.
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
        description: Meta activa con progreso e historial de metas cumplidas
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

    recs = firestore_service.obtener_recolecciones(uid, limite=10)
    if not recs:
        return jsonify({
            "error": "sin_datos",
            "mensaje": "El usuario no tiene recolecciones previas.",
        }), 404

    meta_actual    = firestore_service.obtener_meta_activa(uid)
    historial      = firestore_service.obtener_historial_metas(uid)

    # Si no hay meta todavía, generarla y guardarla ahora
    if not meta_actual:
        meta_actual = calcular_meta(recs, None)
        if meta_actual:
            firestore_service.guardar_meta_activa(uid, meta_actual)

    return jsonify({
        "uid":            uid,
        "meta_activa":    meta_actual,
        "progreso":       progreso_meta(meta_actual),
        "historial_metas": historial,
        "total_cumplidas": len(historial),
    })
