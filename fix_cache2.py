"""Limpia los .pyc de predicciones_service y metas_service y verifica el código."""
import pathlib, sys, importlib, shutil

BASE = pathlib.Path(__file__).parent
PYCACHE = BASE / "app" / "services" / "__pycache__"

targets = [
    "predicciones_service.cpython-39.pyc",
    "predicciones_service.cpython-310.pyc",
    "metas_service.cpython-39.pyc",
    "metas_service.cpython-310.pyc",
]

print("=== Limpiando .pyc ===")
for name in targets:
    p = PYCACHE / name
    if p.exists():
        p.unlink()
        print(f"  ✓ Eliminado {name}")
    else:
        print(f"  — No existe {name}")

# Tocar .py para actualizar mtime
for svc in ("predicciones_service.py", "metas_service.py"):
    py = BASE / "app" / "services" / svc
    py.touch()
    print(f"  ✓ mtime actualizado: {svc}")

# Verificar metas_service
print("\n=== Verificando metas_service ===")
sys.path.insert(0, str(BASE))
from app.services.metas_service import calcular_meta

# Test 1: meta NO obsoleta (hpd actual 3.4, objetivo 3.3 → 3.4 < 3.3*0.95=3.135 es FALSE)
meta_antigua = {
    "nivel": 1,
    "hpd_objetivo": 3.3,
    "dcj_objetivo": 5,
    "cumplida": False,
    "recolecciones_cumplidas": 0,
    "recolecciones_requeridas": 3,
}
recs_no = [{"variables": {"HPD": 3.4, "DCJ": 2}, "prediccion": {"score": 72}}]
r1 = calcular_meta(recs_no, meta_antigua)
ok1 = not r1.get("cumplida")
print(f"  Test 1 – meta NO obsoleta (HPD=3.4 vs obj=3.3): cumplida={r1.get('cumplida')} {'✓' if ok1 else '✗ ERROR'}")

# Test 2: meta SÍ obsoleta (hpd actual 2.8 < 3.3*0.95=3.135)
recs_si = [{"variables": {"HPD": 2.8, "DCJ": 2}, "prediccion": {"score": 60}}]
r2 = calcular_meta(recs_si, meta_antigua)
ok2 = r2.get("cumplida") is True
print(f"  Test 2 – meta SÍ obsoleta (HPD=2.8 vs obj=3.3): cumplida={r2.get('cumplida')} {'✓' if ok2 else '✗ ERROR'}")

# Test 3: sin meta → crea nivel 1
recs_new = [{"variables": {"HPD": 3.4, "DCJ": 2}, "prediccion": {"score": 72}}]
r3 = calcular_meta(recs_new, None)
hpd_exp = round(3.4 * 0.75, 1)
ok3 = r3 and r3.get("nivel") == 1 and abs(r3.get("hpd_objetivo", 0) - hpd_exp) < 0.05
print(f"  Test 3 – sin meta → nivel 1, hpd_obj={r3.get('hpd_objetivo')} (esperado {hpd_exp}) {'✓' if ok3 else '✗ ERROR'}")

# Verificar predicciones_service
print("\n=== Verificando predicciones_service ===")
from app.services.predicciones_service import generar_prediccion_futura

meta = {"hpd_objetivo": 2.55, "etiqueta": "Meta inicial", "nivel": 1}
pred = generar_prediccion_futura(
    variables={"HPD": 3.4, "DCJ": 3, "THT": 40, "ND": 12, "TP": 45, "NPPD": 2},
    extras={"pjnMin": 30, "nochesActivas": 3, "porHora": [0]*24, "porDiaSemana": [0]*7},
    config={"hpdMax": 4, "ttsMax": 21, "dcjMax": 5},
    historial=[
        {"prediccion": {"score": 72}, "variables": {"HPD": 3.4, "DCJ": 3}},
        {"prediccion": {"score": 68}, "variables": {"HPD": 3.6, "DCJ": 4}},
    ],
    prediccion_actual={"score": 72, "nivel": "Alto"},
    meta_activa=meta,
)
esc = pred["escenarios"]
print(f"  Actual:    HPD={esc['actual']['hpd']}  score={esc['actual']['score']}")
print(f"  Mejora:    HPD={esc['mejora']['hpd']}  score={esc['mejora']['score']}")
print(f"  Saludable: HPD={esc['saludable']['hpd']}  score={esc['saludable']['score']}")
print(f"  Subtítulo: {esc['saludable']['subtitulo']}")

hpd_sal = esc["saludable"]["hpd"]
hpd_mej = esc["mejora"]["hpd"]
score_sal = esc["saludable"]["score"]
score_mej = esc["mejora"]["score"]

ok4 = abs(hpd_sal - 2.55) < 0.05
ok5 = hpd_sal <= hpd_mej
ok6 = score_sal <= score_mej + 0.5  # saludable nunca peor que mejora

print(f"\n  HPD saludable == meta objetivo (2.55): {'✓' if ok4 else '✗ ERROR'} ({hpd_sal})")
print(f"  HPD saludable ≤ HPD mejora: {'✓' if ok5 else '✗ ERROR'} ({hpd_sal} ≤ {hpd_mej})")
print(f"  Score saludable ≤ Score mejora: {'✓' if ok6 else '✗ ERROR'} ({score_sal} ≤ {score_mej})")

all_ok = all([ok1, ok2, ok3, ok4, ok5, ok6])
print(f"\n{'✅ Todo correcto — puedes reiniciar Flask.' if all_ok else '❌ Hay errores — revisar.'}")
