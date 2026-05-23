"""Prueba rapida de la conexion a Firestore.

Ejecutar desde D:\\Backend con el venv activado:
    python test_firestore.py

Escribe un usuario de prueba, le guarda una recoleccion, la lee de
vuelta y luego borra el documento de prueba. Si todo sale bien,
veras "TODO OK" al final.
"""
from app.services import firestore_service as fs

UID_PRUEBA = "_test_uid_borrar"


def main():
    print("1) Estado de la conexion:")
    estado = fs.estado()
    for k, v in estado.items():
        print(f"   {k}: {v}")

    if not fs.firestore_disponible():
        print("\n>>> Firestore NO esta disponible. Revisa el error de arriba.")
        return

    print("\n2) Creando usuario de prueba...")
    fs.crear_o_actualizar_usuario(UID_PRUEBA, {
        "email": "prueba@test.com",
        "displayName": "Usuario Prueba",
        "riotId": "Invoker#LAS1",
        "region": "LAS",
    })

    print("3) Guardando una recoleccion de prueba...")
    rec_id = fs.guardar_recoleccion(
        UID_PRUEBA,
        variables={"THT": 30.0, "ND": 10, "TP": 50,
                   "HPD": 3.0, "NPPD": 5.0, "DCJ": 4},
        prediccion={"nivel": "Medio", "score": 55,
                    "probabilidades": {"Bajo": 0.2, "Medio": 0.6, "Alto": 0.2}},
        demo=True,
    )
    print(f"   recoleccion creada con id: {rec_id}")

    print("4) Leyendo de vuelta...")
    ultima = fs.obtener_ultima_recoleccion(UID_PRUEBA)
    print(f"   ultima recoleccion: {ultima}")
    config = fs.obtener_config(UID_PRUEBA)
    print(f"   config del usuario: {config}")

    print("\n5) Limpiando el documento de prueba...")
    db = fs.get_db()
    for snap in db.collection("usuarios").document(UID_PRUEBA) \
                  .collection("recolecciones").stream():
        snap.reference.delete()
    db.collection("usuarios").document(UID_PRUEBA).delete()
    print("   limpiado.")

    print("\n>>> TODO OK. Firestore esta funcionando.")


if __name__ == "__main__":
    main()
