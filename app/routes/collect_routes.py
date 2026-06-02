"""Endpoints de recoleccion de datos de un usuario.

Como la recoleccion tarda (~2 min con la Riot API real), se ejecuta
en segundo plano: POST /api/collect inicia un job y devuelve su id;
GET /api/collect/<job_id> permite consultar el progreso (el % que
alimenta el modal del dashboard).

Si el cuerpo incluye un 'uid' (el uid de Firebase Auth), al terminar
la recoleccion se guarda en Firestore (usuarios/{uid}/recolecciones).
Sin 'uid' el flujo sigue funcionando, solo que no se persiste.
"""
from flask import Blueprint, request, jsonify

from app.services import jobs
from app.services.collector_service import recolectar_usuario, RIOT_API_KEY
from app.services.model_service import predecir
from app.services import firestore_service
from app.services.metas_service import calcular_meta

collect_bp = Blueprint("collect", __name__)


def _job_collect(job_id, name, tag, demo, uid=None, datos_usuario=None):
    """Tarea que corre en segundo plano: recolecta, predice y persiste."""
    def progreso(pct, msg):
        jobs.actualizar(job_id, progreso=pct, paso=msg)

    # Ventana de sueño del usuario (para el PJN). Si no hay uid o config,
    # recolectar_usuario usa la franja por defecto (22:00–06:00).
    cfg = None
    if uid and firestore_service.firestore_disponible():
        try:
            cfg = firestore_service.obtener_config(uid)
        except Exception:  # noqa: BLE001
            cfg = None

    recoleccion = recolectar_usuario(name, tag, progreso, demo=demo, config=cfg)
    variables = recoleccion["variables"]
    perfil = recoleccion.get("perfil") or {}
    extras = recoleccion.get("extras") or {}

    progreso(90, "Ejecutando modelo predictivo")
    prediccion = predecir(variables)

    # Persistencia en Firestore (solo si hay uid y el servicio esta activo).
    recoleccion_id = None
    guardado = False
    if uid and firestore_service.firestore_disponible():
        progreso(95, "Guardando resultados")
        try:
            firestore_service.crear_o_actualizar_usuario(uid, {
                **(datos_usuario or {}),
                "riotId": f"{name}#{tag}",
                "profileIconId": perfil.get("profileIconId"),
                "summonerLevel": perfil.get("summonerLevel"),
                "iconUrl": perfil.get("iconUrl"),
            })
            recoleccion_id = firestore_service.guardar_recoleccion(
                uid, variables, prediccion, demo=demo, extras=extras,
                riot_id=f"{name}#{tag}",
            )
            guardado = recoleccion_id is not None
            # Vincula el Riot ID al usuario la primera vez que se recolecta.
            if guardado and not firestore_service.obtener_riot_id_vinculado(uid):
                firestore_service.vincular_riot_id(uid, f"{name}#{tag}")
            # Evaluar y actualizar meta automática del sistema.
            if guardado:
                try:
                    recs_recientes = firestore_service.obtener_recolecciones(uid, limite=10)
                    meta_actual    = firestore_service.obtener_meta_activa(uid)
                    meta_nueva     = calcular_meta(recs_recientes, meta_actual)
                    if meta_nueva:
                        if meta_nueva.get("cumplida") and not (meta_actual or {}).get("cumplida"):
                            # Meta recién cumplida: archivarla y crear la siguiente
                            firestore_service.archivar_meta_cumplida(uid, meta_nueva)
                            recs_recientes2 = firestore_service.obtener_recolecciones(uid, limite=10)
                            meta_sig = calcular_meta(recs_recientes2, meta_nueva)
                            if meta_sig:
                                firestore_service.guardar_meta_activa(uid, meta_sig)
                        else:
                            firestore_service.guardar_meta_activa(uid, meta_nueva)
                except Exception as e:  # noqa: BLE001
                    print(f"[collect] Error al actualizar meta: {e}")
        except Exception as e:  # noqa: BLE001
            # No tumbamos el job por un fallo de persistencia.
            print(f"[collect] Error al guardar en Firestore: {e}")

    progreso(100, "Generando recomendaciones")
    jobs.actualizar(
        job_id,
        estado="completado",
        resultado={
            "variables": variables,
            "prediccion": prediccion,
            "perfil": perfil,
            "extras": extras,
            "guardado": guardado,
            "recoleccion_id": recoleccion_id,
        },
    )


@collect_bp.route("/collect", methods=["POST"])
def iniciar_collect():
    """Inicia la recoleccion de datos de un usuario (en segundo plano).
    ---
    tags:
      - Recoleccion
    consumes:
      - application/json
    parameters:
      - in: body
        name: usuario
        required: true
        schema:
          type: object
          properties:
            name:     {type: string,  example: "Invoker",      description: Nombre del Riot ID}
            tag:      {type: string,  example: "LAS1",          description: Tag del Riot ID}
            summoner: {type: string,  example: "Invoker#LAS1",  description: "Alternativa: Riot ID completo Nombre#Tag"}
            demo:     {type: boolean, example: true,            description: "Si es true, simula la recoleccion sin llamar a la Riot API"}
            uid:      {type: string,  example: "abc123",        description: "uid de Firebase Auth. Si se envia, la recoleccion se guarda en Firestore."}
            email:    {type: string,  example: "user@mail.com", description: "Opcional. Se guarda en el documento del usuario."}
            displayName: {type: string, example: "Jesus",       description: "Opcional. Se guarda en el documento del usuario."}
            region:   {type: string,  example: "LAS",           description: "Opcional. Region del jugador."}
    responses:
      202:
        description: Job iniciado. Use el job_id para consultar el progreso.
      400:
        description: Falta identificar al usuario (name + tag, o summoner)
    """
    data = request.json or {}
    name = (data.get("name") or "").strip()
    tag = (data.get("tag") or "").strip()

    summoner = (data.get("summoner") or "").strip()
    if summoner and "#" in summoner and not (name and tag):
        name, tag = [p.strip() for p in summoner.rsplit("#", 1)]

    if not name or not tag:
        return jsonify({
            "error": "Falta identificar al usuario.",
            "ayuda": "Envia 'name' y 'tag', o 'summoner' con formato Nombre#Tag.",
        }), 400

    demo = data.get("demo")
    if demo is None:
        # Sin API key configurada => modo demo automaticamente.
        demo = not bool(RIOT_API_KEY)

    uid = (data.get("uid") or "").strip() or None
    datos_usuario = {
        "email": (data.get("email") or "").strip() or None,
        "displayName": (data.get("displayName") or "").strip() or None,
        "region": (data.get("region") or "").strip() or None,
    }

    job_id = jobs.crear_job()
    jobs.ejecutar_en_background(
        lambda jid: _job_collect(
            jid, name, tag, bool(demo), uid=uid, datos_usuario=datos_usuario
        ),
        job_id,
    )

    return jsonify({
        "job_id": job_id,
        "estado": "en_proceso",
        "demo": bool(demo),
        "persistira": bool(uid) and firestore_service.firestore_disponible(),
        "consulta": f"/api/collect/{job_id}",
    }), 202


@collect_bp.route("/collect/<job_id>", methods=["GET"])
def estado_collect(job_id):
    """Consulta el estado y progreso de un job de recoleccion.
    ---
    tags:
      - Recoleccion
    parameters:
      - in: path
        name: job_id
        required: true
        type: string
        description: Id devuelto por POST /api/collect
    responses:
      200:
        description: Estado actual del job (en_proceso | completado | error)
      404:
        description: job_id no encontrado
    """
    job = jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "job_id no encontrado."}), 404
    return jsonify(job)
