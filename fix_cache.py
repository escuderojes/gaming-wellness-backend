"""
Limpia el pyc cacheado de predicciones_service y verifica que el código
actualizado está activo. Ejecutar desde D:\Backend con el venv activado:

    python fix_cache.py
"""
import os, sys, pathlib, importlib.util

BASE = pathlib.Path(__file__).parent
PY  = BASE / "app/services/predicciones_service.py"
PYC = BASE / "app/services/__pycache__/predicciones_service.cpython-39.pyc"

# 1. Verificar que el .py tiene los cambios
contenido = PY.read_text(encoding="utf-8")
tiene_min        = "min(s_sal, s_mej)" in contenido
tiene_time_factor = "time_factor" in contenido
tiene_k09        = "k=0.9" in contenido

print("=== VERIFICACIÓN DEL ARCHIVO .py ===")
print(f"  min(s_sal, s_mej) presente : {'✓' if tiene_min else '✗ FALTA'}")
print(f"  time_factor presente       : {'✓' if tiene_time_factor else '✗ FALTA'}")
print(f"  k=0.9 presente             : {'✓' if tiene_k09 else '✗ FALTA'}")

if not (tiene_min and tiene_time_factor and tiene_k09):
    print("\n⚠ El archivo .py NO tiene todos los cambios. Algo falló al guardar.")
    sys.exit(1)

# 2. Borrar el pyc
if PYC.exists():
    try:
        PYC.unlink()
        print(f"\n✓ Borrado: {PYC}")
    except Exception as e:
        print(f"\n✗ No se pudo borrar {PYC}: {e}")
        print("  Intenta cerrando el servidor Flask primero.")
        sys.exit(1)
else:
    print(f"\n  {PYC.name} no existe, no hay nada que borrar.")

# 3. Forzar mtime del .py para que Python lo recompile
PY.touch()
print(f"✓ mtime actualizado en {PY.name}")

# 4. Cargar el módulo fresco y probar la función
print("\n=== RESULTADO A 30 DÍAS ===")
spec = importlib.util.spec_from_file_location("ps_fresh", str(PY))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

variables   = {"THT": 0, "ND": 7, "TP": 0, "HPD": 3.9, "NPPD": 0, "DCJ": 6}
extras      = {"pjnMin": 0}
config      = {"hpdMax": 3.1, "dcjMax": 5}
historial   = [
    {"prediccion": {"score": 90}, "variables": {"HPD": 3.9, "DCJ": 6}},
    {"prediccion": {"score": 90}, "variables": {"HPD": 3.9, "DCJ": 6}},
]
pred_actual = {"score": 90, "nivel": "Alto"}

result = mod.generar_prediccion_futura(variables, extras, config, historial, pred_actual)

for h in result["horizontes"]:
    ok = "✓" if h["score_saludable"] <= h["score_mejora"] else "✗"
    print(f"  {h['dias']:2}d  actual={h['score_actual']}  "
          f"mejora={h['score_mejora']}  saludable={h['score_saludable']}  {ok}")

print("\nListo. Ahora reinicia el servidor Flask.")
