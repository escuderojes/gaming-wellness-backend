import csv

# ============================================
# CONFIGURACIÓN DE ARCHIVOS
# ============================================

INPUT_FILE = "zrecoleccion/dataset_detallado.csv"
OUTPUT_FILE = "zrecoleccion/usuarios_separados.csv"

# ============================================
# PROCESO
# ============================================

usuarios_procesados = []

try:
    with open(INPUT_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            try:
                # Extraer los campos necesarios
                # El CSV de entrada tiene: Usuario, Tag, THT, etc.
                usuario = row["Usuario"].strip()
                tag = row["Tag"].strip()
                
                # Unir en el formato deseado: Usuario#Tag
                full_user = f"{usuario}#{tag}"
                
                usuarios_procesados.append({
                    "Usuario_Completo": full_user
                })
                
            except KeyError as e:
                print(f"⚠ Columna no encontrada: {e}")
                continue
            except Exception as e:
                print(f"⚠ Error procesando fila: {e}")

    # ============================================
    # GUARDAR NUEVO CSV
    # ============================================

    with open(OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as file:
        # Definimos el nombre de la única columna de salida
        fieldnames = ["Usuario_Completo"]
        
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        
        for u in usuarios_procesados:
            writer.writerow(u)

    # ============================================
    # RESULTADOS
    # ============================================

    print("===================================")
    print("✅ CSV generado correctamente")
    print("===================================")
    print(f"📄 Archivo: {OUTPUT_FILE}")
    print(f"👥 Usuarios procesados: {len(usuarios_procesados)}")
    print("===================================")

except FileNotFoundError:
    print(f"❌ Error: No se encontró el archivo '{INPUT_FILE}'")