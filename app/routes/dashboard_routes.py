"""Endpoints del dashboard — leen datos reales del usuario desde Firestore.

Todos los endpoints necesitan el 'uid' del usuario (el de Firebase
Auth). En los GET se envia como query param (?uid=...); en el PUT,
dentro del cuerpo JSON.

Devuelven SOLO los datos que el backend realmente tiene hoy: las 6
variables del modelo, la prediccion, el historial de recolecciones y
la configuracion. Las metricas extra que muestra el frontend (PJN,
TTS semanal, distribucion por dia, alertas) dependen de extender el
colector y de la capa de reglas — pendientes en el roadmap.
"""
from flask import Blueprint, request, jsonify

from app.services import firestore_service
from app.services import recomendaciones as reglas

dashboard_bp = Blueprint("dashboard", __name__)


def _sin_firestore():
    """Respuesta estandar cuando Firestore no esta disponible."""
    return jsonify({
        "error": "La persistencia en Firestore no esta disponible.",
        "detalle": firestore_service.estado().get("error"),
    }), 503


def _uid_de_query():
    """Lee y valida el uid de los query params."""
    uid = (request.args.get("uid") or "").strip()
    return uid or None


@dashboard_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    """Estado actual del usuario: su recoleccion mas reciente.
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
        description: Ultima recoleccion + prediccion + config del usuario
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    uid = _uid_de_query()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    usuario = firestore_service.obtener_usuario(uid)
    # Filtra por riotId actual del usuario: si cambió de summoner, muestra
    # solo la última recolección de ese summoner, no del anterior.
    riot_id = (usuario or {}).get("riotId")
    ultima = firestore_service.obtener_ultima_recoleccion(uid, riot_id=riot_id)
    config = firestore_service.obtener_config(uid)

    return jsonify({
        "uid": uid,
        "riotId": (usuario or {}).get("riotId"),
        "riotIdVinculado": (usuario or {}).get("riotIdVinculado"),
        "region": (usuario or {}).get("region"),
        "iconUrl": (usuario or {}).get("iconUrl"),
        "profileIconId": (usuario or {}).get("profileIconId"),
        "summonerLevel": (usuario or {}).get("summonerLevel"),
        "tiene_datos": ultima is not None,
        "actual": ultima,          # {fecha, demo, variables, prediccion, id} o None
        "config": config,
    })


@dashboard_bp.route("/historial", methods=["GET"])
def get_historial():
    """Historial de recolecciones del usuario (para la grafica de tendencia).
    ---
    tags:
      - Dashboard
    parameters:
      - in: query
        name: uid
        required: true
        type: string
        description: uid de Firebase Auth del usuario
      - in: query
        name: limite
        required: false
        type: integer
        default: 20
        description: Cuantas recolecciones devolver (mas recientes primero)
    responses:
      200:
        description: Lista de recolecciones
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    uid = _uid_de_query()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    try:
        limite = int(request.args.get("limite", 20))
    except (TypeError, ValueError):
        limite = 20
    limite = max(1, min(limite, 200))

    # riotId opcional: si se envía, filtra solo ese summoner.
    riot_id = (request.args.get("riotId") or "").strip() or None

    recolecciones = firestore_service.obtener_recolecciones(uid, limite=limite, riot_id=riot_id)
    return jsonify({
        "uid": uid,
        "total": len(recolecciones),
        "recolecciones": recolecciones,
    })


@dashboard_bp.route("/config", methods=["GET"])
def get_config():
    """Devuelve la configuracion del usuario.
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
        description: Mapa de configuracion del usuario
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    uid = _uid_de_query()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    return jsonify({"uid": uid, "config": firestore_service.obtener_config(uid)})


@dashboard_bp.route("/config", methods=["PUT"])
def put_config():
    """Actualiza la configuracion del usuario.
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
            uid:    {type: string, example: "abc123", description: uid de Firebase Auth}
            config: {type: object, description: "Campos a actualizar (hpdMax, ttsMax, dcjMax, sleepStart, sleepEnd, sensibilidad, recordatorios)"}
    responses:
      200:
        description: Configuracion actualizada
      400:
        description: Falta el uid o el config
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    data = request.json or {}
    uid = (data.get("uid") or "").strip()
    config = data.get("config")

    if not uid:
        return jsonify({"error": "Falta 'uid' en el cuerpo."}), 400
    if not isinstance(config, dict) or not config:
        return jsonify({"error": "Falta 'config' (objeto) en el cuerpo."}), 400

    firestore_service.guardar_config(uid, config)
    return jsonify({
        "uid": uid,
        "actualizado": True,
        "config": firestore_service.obtener_config(uid),
    })


@dashboard_bp.route("/perfil", methods=["GET"])
def get_perfil():
    """Perfil del usuario: identidad + agregados sobre todas las recolecciones.
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
        description: Datos del usuario + estadisticas acumuladas
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    uid = _uid_de_query()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    usuario = firestore_service.obtener_usuario(uid)
    # Para los agregados se leen todas las recolecciones (tope de seguridad 500).
    recolecciones = firestore_service.obtener_recolecciones(uid, limite=500)

    agregados = _calcular_agregados(recolecciones)

    return jsonify({
        "uid": uid,
        "email": (usuario or {}).get("email"),
        "displayName": (usuario or {}).get("displayName"),
        "riotId": (usuario or {}).get("riotId"),
        "region": (usuario or {}).get("region"),
        "iconUrl": (usuario or {}).get("iconUrl"),
        "profileIconId": (usuario or {}).get("profileIconId"),
        "summonerLevel": (usuario or {}).get("summonerLevel"),
        "creado": _iso(usuario.get("creado")) if usuario else None,
        "ultimaActividad": _iso(usuario.get("ultimaActividad")) if usuario else None,
        "agregados": agregados,
    })


def _iso(valor):
    """Convierte un timestamp de Firestore a ISO string si es posible."""
    if valor is None:
        return None
    return valor.isoformat() if hasattr(valor, "isoformat") else valor


def _calcular_agregados(recolecciones):
    """Estadisticas acumuladas sobre el historial de recolecciones."""
    total = len(recolecciones)
    if total == 0:
        return {
            "totalRecolecciones": 0,
            "distribucionNivel": {"Alto": 0, "Medio": 0, "Bajo": 0},
            "promedios": {},
            "thtAcumulado": 0.0,
        }

    claves = ["THT", "ND", "TP", "HPD", "NPPD", "DCJ"]
    sumas = {k: 0.0 for k in claves}
    distribucion = {"Alto": 0, "Medio": 0, "Bajo": 0}

    for rec in recolecciones:
        variables = rec.get("variables") or {}
        for k in claves:
            try:
                sumas[k] += float(variables.get(k, 0) or 0)
            except (TypeError, ValueError):
                pass
        nivel = (rec.get("prediccion") or {}).get("nivel")
        if nivel in distribucion:
            distribucion[nivel] += 1

    promedios = {k: round(sumas[k] / total, 2) for k in claves}

    return {
        "totalRecolecciones": total,
        "distribucionNivel": distribucion,
        "promedios": promedios,
        "thtAcumulado": round(sumas["THT"], 2),
    }


@dashboard_bp.route("/recomendaciones", methods=["GET"])
def get_recomendaciones():
    """Recomendaciones y alertas generadas por la capa de reglas.
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
        description: Lista de recomendaciones + cumplimiento
      400:
        description: Falta el uid
      503:
        description: Firestore no disponible
    """
    if not firestore_service.firestore_disponible():
        return _sin_firestore()

    uid = _uid_de_query()
    if not uid:
        return jsonify({"error": "Falta el parametro 'uid'."}), 400

    try:
        ultima = firestore_service.obtener_ultima_recoleccion(uid)
        config = firestore_service.obtener_config(uid)
    except Exception as exc:
        import traceback, logging
        logging.error("Error leyendo Firestore en /recomendaciones: %s\n%s",
                      exc, traceback.format_exc())
        return jsonify({"error": str(exc), "tiene_datos": False,
                        "recomendaciones": [], "cumplimiento": None}), 500

    if not ultima:
        return jsonify({
            "uid": uid,
            "tiene_datos": False,
            "recomendaciones": [],
            "cumplimiento": None,
        })

    variables  = ultima.get("variables")  or {}
    extras     = ultima.get("extras")     or {}
    prediccion = ultima.get("prediccion") or {}

    try:
        recos = reglas.generar_recomendaciones(variables, extras, config, prediccion)
        cum   = reglas.calcular_cumplimiento(variables, extras, config)
    except Exception as exc:
        import traceback, logging
        logging.error("Error en capa de reglas: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc), "tiene_datos": False,
                        "recomendaciones": [], "cumplimiento": None}), 500

    return jsonify({
        "uid": uid,
        "tiene_datos": True,
        "fecha": ultima.get("fecha"),
        "nivel": prediccion.get("nivel"),
        "recomendaciones": recos,
        "cumplimiento": cum,
    })
