from flask import Flask
from flask_cors import CORS
from flasgger import Swagger


def create_app():
    app = Flask(__name__)
    CORS(app)

    # registra las rutas de la api en un solo lugar.
    from app.routes.prediction_routes import prediction_bp
    from app.routes.collect_routes import collect_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.logros_routes import logros_bp
    from app.routes.predicciones_routes import predicciones_bp
    from app.routes.resetear_cuenta_routes import resetear_cuenta_bp
    from app.routes.metas_routes import metas_bp

    app.register_blueprint(prediction_bp, url_prefix="/api")
    app.register_blueprint(collect_bp, url_prefix="/api")
    app.register_blueprint(dashboard_bp, url_prefix="/api")
    app.register_blueprint(logros_bp, url_prefix="/api")
    app.register_blueprint(predicciones_bp, url_prefix="/api")
    app.register_blueprint(resetear_cuenta_bp, url_prefix="/api")
    app.register_blueprint(metas_bp, url_prefix="/api")

    # documentacion interactiva disponible en /apidocs/.
    app.config["SWAGGER"] = {
        "title": "Gaming Wellness Prevent - API",
        "description": "API del sistema predictivo de uso excesivo en gaming.",
        "version": "0.2.0",
        "uiversion": 3,
    }
    Swagger(app)

    return app
