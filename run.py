"""Punto de entrada del backend Gaming Wellness Prevent."""
from pathlib import Path
from dotenv import load_dotenv

# Carga las variables de entorno (RIOT_API_KEY, etc.) desde el archivo
# .env ANTES de importar la app: collector_service lee RIOT_API_KEY en
# tiempo de importacion, asi que .env debe cargarse primero.
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
