"""Endpoint de reset de cuenta: POST /api/resetear-cuenta."""
from flask import Blueprint, request, jsonify

from app.services import firestore_service

resetear_cuenta_bp = Blueprint("resetear_cuenta", __name__)


@resetear_cuenta_bp.route("/resetear-cuenta", methods=["POST"])
def post_resetear_cuenta():
    """Borra el historial y desvincula la cuenta de LoL del usuario.
    ---
    tags:
      - Dashboard
    consumes:
      - application/json
    parameters:
      - in: body
        name: payload
        required: true
        schema:
          type: object
          properties:
            uid: {type: string, example: "abc123", description: uid de Firebase Auth}
    responses:
      200:
        description: Cuenta reseteada correctamente
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return jsonify({
            "error": "La persistencia en Firestore no está disponible.",
            "detalle": firestore_service.estado().get("error"),
        }), 503

    data = request.json or {}
    uid = (data.get("uid") or "").strip()
    if not uid:
        return jsonify({"error": "Falta el parámetro 'uid'."}), 400

    ok = firestore_service.resetear_cuenta(uid)
    if not ok:
        return jsonify({"error": "No se pudo resetear la cuenta."}), 500

    return jsonify({"ok": True, "uid": uid})
