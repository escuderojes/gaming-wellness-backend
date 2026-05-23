import csv

# ============================================
# CONFIGURACIÓN
# ============================================

INPUT_FILE = "zrecoleccion/dataset_detallado.csv"
OUTPUT_FILE = "zrecoleccion/dataset_reducido.csv"

# Columnas finales recomendadas
COLUMNAS_DESEADAS = [
    "Usuario",
    "Tag",
    "THT",
    "ND",
    "HPD",
    "NPPD",
    "DCJ",
    "Riesgo"
]

# ============================================
# FUNCIÓN PARA RECALCULAR RIESGO
# ============================================

def calcular_riesgo(hpd, nppd, dcj):

    score = 0

    # Intensidad diaria
    if hpd > 5:
        score += 2
    elif hpd > 3:
        score += 1

    # Frecuencia diaria
    if nppd > 7:
        score += 2
    elif nppd > 4:
        score += 1

    # Continuidad del hábito
    if dcj > 5:
        score += 2
    elif dcj > 3:
        score += 1

    # Clasificación final
    if score >= 5:
        return "Alto"

    elif score >= 3:
        return "Medio"

    return "Bajo"

# ============================================
# PROCESO DE FILTRADO
# ============================================

datos_filtrados = []

try:

    with open(INPUT_FILE, mode="r", encoding="utf-8") as file:

        reader = csv.DictReader(file)

        for row in reader:

            try:

                # ====================================
                # CONVERTIR VARIABLES NUMÉRICAS
                # ====================================

                hpd = float(row["HPD"])
                nppd = float(row["NPPD"])
                dcj = float(row["DCJ"])

                # ====================================
                # RECALCULAR RIESGO
                # ====================================

                riesgo = calcular_riesgo(
                    hpd,
                    nppd,
                    dcj
                )

                # ====================================
                # CREAR FILA REDUCIDA
                # ====================================

                fila_reducida = {
                    "Usuario": row["Usuario"].strip(),
                    "Tag": row["Tag"].strip(),
                    "THT": row["THT"].strip(),
                    "ND": row["ND"].strip(),
                    "HPD": row["HPD"].strip(),
                    "NPPD": row["NPPD"].strip(),
                    "DCJ": row["DCJ"].strip(),
                    "Riesgo": riesgo
                }

                datos_filtrados.append(fila_reducida)

            except KeyError as e:

                print(f"⚠ Falta la columna: {e}")
                continue

            except ValueError as e:

                print(f"⚠ Error convirtiendo datos numéricos: {e}")
                continue

    # ============================================
    # GUARDAR NUEVO CSV
    # ============================================

    with open(OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=COLUMNAS_DESEADAS
        )

        writer.writeheader()
        writer.writerows(datos_filtrados)

    # ============================================
    # FINAL
    # ============================================

    print("===================================")
    print("✅ Dataset reducido generado")
    print("===================================")
    print(f"📄 Archivo generado: {OUTPUT_FILE}")
    print(f"📊 Columnas conservadas: {', '.join(COLUMNAS_DESEADAS)}")
    print(f"📝 Registros procesados: {len(datos_filtrados)}")
    print("===================================")

except FileNotFoundError:

    print(f"❌ Error: El archivo '{INPUT_FILE}' no existe.")