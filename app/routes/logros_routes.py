"""Endpoint de logros: GET /api/logros?uid=..."""
from flask import Blueprint, request, jsonify

from app.services import firestore_service
from app.services.logros_service import calcular_logros

logros_bp = Blueprint("logros", __name__)


@logros_bp.route("/logros", methods=["GET"])
def get_logros():
    """Logros del usuario calculados a partir de su historial.
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
        description: Lista de logros con estado desbloqueado/bloqueado
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return jsonify({
            "error": "La persistencia en Firestore no esta disponible.",
            "detalle": firestore_service.estado().get("error"),
        }), 503

    uid = (request.args.get("uid") or "").strip()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    recolecciones   = firestore_service.obtener_recolecciones(uid, limite=500)
    config          = firestore_service.obtener_config(uid)
    usuario         = firestore_service.obtener_usuario(uid)
    historial_metas = firestore_service.obtener_historial_metas(uid)

    logros = calcular_logros(recolecciones, config, usuario, historial_metas)
    desbloqueados = sum(1 for lg in logros if lg["desbloqueado"])

    return jsonify({
        "uid": uid,
        "logros": logros,
        "total": len(logros),
        "desbloqueados": desbloqueados,
    })
