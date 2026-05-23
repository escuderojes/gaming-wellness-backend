"""Punto de entrada WSGI para produccion (Render + Gunicorn).

En produccion las variables de entorno (RIOT_API_KEY,
FIREBASE_CREDENTIALS_JSON) las inyecta Render directamente —
no hace falta el archivo .env.
"""
from app import create_app

app = create_app()
