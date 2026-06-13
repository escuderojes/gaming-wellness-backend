"""Servicio de Firestore - persistencia por usuario.

Inicializa Firebase Admin con la clave de servicio y expone funciones
para guardar y leer:

  usuarios/{uid}                         -> documento del usuario + config
  usuarios/{uid}/recolecciones/{autoId}  -> una extraccion ("Buscar")

El modelo de datos esta descrito en CONTEXTO_PROYECTO.md (seccion 6).

Diseno tolerante a fallos: si firebase-admin no esta instalado o la
clave no existe, el backend NO se cae. Las funciones de lectura
devuelven valores vacios y las de escritura quedan sin efecto, pero
los endpoints de prediccion/recoleccion siguen funcionando. Usa
firestore_disponible() para saber si la persistencia esta activa.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# services -> app -> Backend (donde esta la clave .json)
BASE = Path(__file__).resolve().parents[2]

# Ruta de la clave de servicio. Se puede sobreescribir con la variable
# de entorno FIREBASE_KEY_PATH; por defecto busca firebase-key.json.
KEY_PATH = Path(os.environ.get("FIREBASE_KEY_PATH", BASE / "firebase-key.json"))

# Alternativa para despliegues en la nube (Render, Railway, etc.):
# pega el contenido completo del JSON en esta variable de entorno.
# Si esta definida, tiene prioridad sobre KEY_PATH.
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")

# Config por defecto que se asigna a un usuario nuevo (ver seccion 6).
CONFIG_DEFAULT = {
    "hpdMax": 4.0,
    "ttsMax": 21.0,
    "dcjMax": 5,
    "sleepStart": "23:00",
    "sleepEnd": "07:00",
    "sensibilidad": "media",
    "recordatorios": True,
}

_db = None
_init_error = None


def _inicializar():
    """Inicializa Firebase Admin una sola vez. Idempotente."""
    global _db, _init_error
    if _db is not None or _init_error is not None:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        _init_error = "firebase-admin no esta instalado. Ejecuta: pip install firebase-admin"
        print(f"[firestore] {_init_error}")
        return
    if not FIREBASE_CREDENTIALS_JSON and not KEY_PATH.exists():
        _init_error = f"No se encontro la clave de servicio en {KEY_PATH}"
        print(f"[firestore] {_init_error}")
        return
    try:
        if not firebase_admin._apps:
            if FIREBASE_CREDENTIALS_JSON:
                # Modo nube: credenciales en variable de entorno.
                cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON))
            else:
                # Modo local: archivo firebase-key.json.
                cred = credentials.Certificate(str(KEY_PATH))
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("[firestore] Conectado correctamente.")
    except ValueError as e:
        # Flask debug reloader puede llamar initialize_app() dos veces.
        # Si la app ya existe la reutilizamos en lugar de fallar.
        if "already exists" in str(e).lower():
            try:
                _db = firestore.client()
                print("[firestore] Reutilizando app Firebase existente.")
            except Exception as e2:
                _init_error = f"Error al obtener cliente Firestore: {e2}"
                print(f"[firestore] {_init_error}")
        else:
            _init_error = f"Error al inicializar Firebase Admin: {e}"
            print(f"[firestore] {_init_error}")
    except Exception as e:
        _init_error = f"Error al inicializar Firebase Admin: {e}"
        print(f"[firestore] {_init_error}")


def firestore_disponible():
    """True si la persistencia en Firestore esta operativa."""
    _inicializar()
    return _db is not None


def estado():
    """Devuelve un dict con el estado de la conexion."""
    _inicializar()
    return {"disponible": _db is not None, "clave": str(KEY_PATH), "error": _init_error}


def get_db():
    """Devuelve el cliente de Firestore o None si no esta disponible."""
    _inicializar()
    return _db


# --------------------------------------------------------------------
# Usuarios
# --------------------------------------------------------------------

def crear_o_actualizar_usuario(uid, datos):
    """Crea o actualiza el documento de un usuario."""
    db = get_db()
    if db is None:
        return False
    ref = db.collection("usuarios").document(uid)
    ahora = datetime.now(timezone.utc)
    snap = ref.get()
    payload = {k: v for k, v in (datos or {}).items() if v is not None}
    payload["ultimaActividad"] = ahora
    if not snap.exists:
        payload["creado"] = ahora
        payload.setdefault("config", CONFIG_DEFAULT.copy())
    ref.set(payload, merge=True)
    return True


def obtener_usuario(uid):
    """Devuelve el documento del usuario como dict, o None si no existe."""
    db = get_db()
    if db is None:
        return None
    snap = db.collection("usuarios").document(uid).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["uid"] = uid
    return data


# --------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------

def obtener_config(uid):
    """Devuelve la config del usuario; CONFIG_DEFAULT si no tiene."""
    usuario = obtener_usuario(uid)
    if not usuario:
        return CONFIG_DEFAULT.copy()
    config = CONFIG_DEFAULT.copy()
    config.update(usuario.get("config") or {})
    return config


def guardar_config(uid, config):
    """Actualiza (merge) el mapa config del usuario."""
    db = get_db()
    if db is None:
        return False
    ref = db.collection("usuarios").document(uid)
    ref.set({"config": config or {}, "ultimaActividad": datetime.now(timezone.utc)}, merge=True)
    return True


# --------------------------------------------------------------------
# Recolecciones
# --------------------------------------------------------------------

def guardar_recoleccion(uid, variables, prediccion, demo=False, extras=None, riot_id=None):
    """Guarda una recoleccion en usuarios/{uid}/recolecciones.

    riot_id identifica a que summoner pertenece esta recoleccion,
    permitiendo filtrar el historial por cuenta de LoL.
    """
    db = get_db()
    if db is None:
        return None
    doc = {
        "fecha": datetime.now(timezone.utc),
        "demo": bool(demo),
        "variables": variables or {},
        "prediccion": prediccion or {},
        "extras": extras or {},
    }
    if riot_id:
        doc["riotId"] = riot_id
    ref = db.collection("usuarios").document(uid).collection("recolecciones").document()
    ref.set(doc)
    db.collection("usuarios").document(uid).set({"ultimaActividad": doc["fecha"]}, merge=True)
    return ref.id


def obtener_recolecciones(uid, limite=20, riot_id=None):
    """Devuelve las ultimas recolecciones del usuario (mas reciente primero).

    Si se especifica riot_id, filtra solo ese summoner. Las recolecciones
    antiguas sin campo riotId se incluyen siempre (compatibilidad hacia atras).
    """
    db = get_db()
    if db is None:
        return []
    from firebase_admin import firestore as _fs
    fetch_limite = limite if not riot_id else min(500, limite * 10)
    query = (
        db.collection("usuarios").document(uid)
        .collection("recolecciones")
        .order_by("fecha", direction=_fs.Query.DESCENDING)
        .limit(fetch_limite)
    )
    resultado = []
    for snap in query.stream():
        item = snap.to_dict()
        item["id"] = snap.id
        fecha = item.get("fecha")
        if hasattr(fecha, "isoformat"):
            item["fecha"] = fecha.isoformat()
        if riot_id:
            item_riot = item.get("riotId", "")
            if item_riot and item_riot.lower() != riot_id.lower():
                continue
        resultado.append(item)
        if len(resultado) >= limite:
            break
    return resultado


def obtener_ultima_recoleccion(uid, riot_id=None):
    """Devuelve la recoleccion mas reciente del usuario (o del summoner
    indicado si se pasa riot_id), o None si no hay ninguna."""
    recientes = obtener_recolecciones(uid, limite=1, riot_id=riot_id)
    return recientes[0] if recientes else None


# --------------------------------------------------------------------
# Tests ICOGS-A (cuestionario de control sobre el comportamiento de juego)
# --------------------------------------------------------------------
# usuarios/{uid}/icogs/{autoId} -> un test respondido
#   { fecha, respuestas: [12 valores 1-5 crudos], puntaje, nivel, origen }
# El puntaje recodifica los items invertidos {2,3,4,5,6,8} como (6 - v).
# Umbral del instrumento: >= 36 -> nivel "Alto" (control deteriorado).

ICOGS_ITEMS_INVERTIDOS = {2, 3, 4, 5, 6, 8}   # numeracion 1-12
ICOGS_UMBRAL = 36


def calcular_icogs(respuestas):
    """Puntaje total ICOGS-A (12-60) a partir de las 12 respuestas crudas."""
    total = 0
    for i, v in enumerate(respuestas, start=1):
        v = int(v)
        total += (6 - v) if i in ICOGS_ITEMS_INVERTIDOS else v
    return total


def guardar_icogs(uid, respuestas, origen="plataforma", fecha=None, puntaje=None):
    """Guarda un test ICOGS-A en usuarios/{uid}/icogs y devuelve el registro.

    Regla de la plataforma: el historial mantiene como maximo el par
    antes/despues. Si el usuario ya tiene 2 o mas tests y responde de
    nuevo, el test mas reciente se SOBRESCRIBE (el penultimo queda como
    ancla del "antes"); con 0 o 1 tests, simplemente se agrega.
    """
    db = get_db()
    if db is None:
        return None
    if origen == "plataforma":
        previos = obtener_icogs(uid, limite=2)
        if len(previos) >= 2 and previos[0].get("id"):
            (db.collection("usuarios").document(uid)
               .collection("icogs").document(previos[0]["id"]).delete())
    respuestas = [int(v) for v in respuestas]
    if puntaje is None:
        puntaje = calcular_icogs(respuestas)
    doc = {
        "fecha": fecha or datetime.now(timezone.utc),
        "respuestas": respuestas,
        "puntaje": int(puntaje),
        "nivel": "Alto" if int(puntaje) >= ICOGS_UMBRAL else "Bajo",
        "umbral": ICOGS_UMBRAL,
        "origen": origen,
    }
    ref = db.collection("usuarios").document(uid).collection("icogs").document()
    ref.set(doc)
    doc["id"] = ref.id
    if hasattr(doc["fecha"], "isoformat"):
        doc["fecha"] = doc["fecha"].isoformat()
    return doc


def obtener_icogs(uid, limite=10):
    """Devuelve los ultimos tests ICOGS-A del usuario (mas reciente primero)."""
    db = get_db()
    if db is None:
        return []
    from firebase_admin import firestore as _fs
    query = (
        db.collection("usuarios").document(uid)
        .collection("icogs")
        .order_by("fecha", direction=_fs.Query.DESCENDING)
        .limit(limite)
    )
    resultado = []
    for snap in query.stream():
        item = snap.to_dict()
        item["id"] = snap.id
        fecha = item.get("fecha")
        if hasattr(fecha, "isoformat"):
            item["fecha"] = fecha.isoformat()
        resultado.append(item)
    return resultado


# --------------------------------------------------------------------
# Vinculación de cuenta de LoL
# --------------------------------------------------------------------

def vincular_riot_id(uid, riot_id):
    """Guarda el Riot ID vinculado del usuario (una sola vez por cuenta)."""
    db = get_db()
    if db is None:
        return False
    ref = db.collection("usuarios").document(uid)
    ref.set({"riotIdVinculado": riot_id, "ultimaActividad": datetime.now(timezone.utc)}, merge=True)
    return True


def obtener_riot_id_vinculado(uid):
    """Devuelve el riotIdVinculado del usuario, o None si no tiene."""
    usuario = obtener_usuario(uid)
    return (usuario or {}).get("riotIdVinculado")


# --------------------------------------------------------------------
# Metas automáticas
# --------------------------------------------------------------------

def obtener_meta_activa(uid):
    """Devuelve la meta activa del usuario o None si no tiene."""
    usuario = obtener_usuario(uid)
    return (usuario or {}).get("metaActiva")


def guardar_meta_activa(uid, meta):
    """Guarda o actualiza la meta activa en el documento del usuario."""
    db = get_db()
    if db is None:
        return False
    ref = db.collection("usuarios").document(uid)
    ref.set({"metaActiva": meta, "ultimaActividad": datetime.now(timezone.utc)}, merge=True)
    return True


def archivar_meta_cumplida(uid, meta):
    """Mueve la meta cumplida al historial y borra la activa."""
    db = get_db()
    if db is None:
        return False
    from firebase_admin import firestore as _fs
    ref = db.collection("usuarios").document(uid)
    ref.set({
        "historialMetas": _fs.ArrayUnion([meta]),
        "metaActiva":     None,
        "ultimaActividad": datetime.now(timezone.utc),
    }, merge=True)
    return True


def obtener_historial_metas(uid):
    """Devuelve la lista de metas cumplidas del usuario."""
    usuario = obtener_usuario(uid)
    return (usuario or {}).get("historialMetas") or []


def resetear_cuenta(uid):
    """Borra el historial completo y desvincula la cuenta de LoL.

    Operaciones:
      1. Elimina todos los documentos de usuarios/{uid}/recolecciones.
      2. Limpia riotIdVinculado y riotId del documento del usuario.
      3. Resetea config.metas a [].
    """
    db = get_db()
    if db is None:
        return False

    from firebase_admin import firestore as _fs

    # 1. Borrar subcolección de recolecciones en lotes de 100.
    col_ref = db.collection("usuarios").document(uid).collection("recolecciones")
    while True:
        docs = list(col_ref.limit(100).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

    # 2. Limpiar riotIdVinculado y riotId del documento del usuario.
    ref = db.collection("usuarios").document(uid)
    try:
        ref.update({
            "riotIdVinculado": _fs.DELETE_FIELD,
            "riotId": _fs.DELETE_FIELD,
            "ultimaActividad": datetime.now(timezone.utc),
        })
    except Exception:  # noqa: BLE001
        pass

    # 3. Resetear config.metas a [].
    config = obtener_config(uid) or {}
    config["metas"] = []
    guardar_config(uid, config)

    return True
