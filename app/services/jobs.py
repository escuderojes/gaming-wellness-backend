"""Gestor simple de trabajos en segundo plano.

Permite lanzar tareas largas (como la recoleccion de datos de Riot,
que tarda ~2 min) en un hilo aparte y consultar su progreso por id.
El almacen es en memoria: sirve para desarrollo y para una sola
instancia del servidor.
"""
import threading
import time
import uuid

_jobs = {}
_lock = threading.Lock()


def crear_job():
    """Crea un job nuevo y devuelve su id."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "estado": "en_proceso",   # en_proceso | completado | error
            "progreso": 0,
            "paso": "Iniciando...",
            "resultado": None,
            "error": None,
            "creado": time.time(),
        }
    return job_id


def actualizar(job_id, **campos):
    """Actualiza campos de un job de forma segura entre hilos."""
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(campos)


def get_job(job_id):
    """Devuelve una copia del job, o None si no existe."""
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def ejecutar_en_background(target, job_id):
    """Ejecuta target(job_id) en un hilo daemon; captura cualquier error."""
    def runner():
        try:
            target(job_id)
        except Exception as e:  # noqa: BLE001
            actualizar(job_id, estado="error", error=str(e), paso="Error")

    threading.Thread(target=runner, daemon=True).start()
