import pandas as pd

# ── Cargar archivos ────────────────────────────────────────
# Cambia los nombres de archivo según donde estén guardados
pre  = pd.read_csv("data_collector/dataset_PRETEST.csv")
post = pd.read_csv("data_collector/dataset_POSTEST.csv")

# ── Renombrar columnas agregando sufijo _pre y _post ───────
# Columnas que se renombran (excluimos Usuario y Tag que son identificadores)
cols_datos = ["THT", "ND", "TPP", "HPD", "NPPD", "DCJ", "Riesgo"]

# Solo renombrar columnas que existen en el CSV
cols_pre  = [c for c in cols_datos if c in pre.columns]
cols_post = [c for c in cols_datos if c in post.columns]

pre_renamed  = pre.rename(columns={c: f"{c}_pre"  for c in cols_pre})
post_renamed = post.rename(columns={c: f"{c}_post" for c in cols_post})

# ── Unir por Usuario y Tag ─────────────────────────────────
df = pd.merge(pre_renamed, post_renamed, on=["Usuario", "Tag"], how="inner")

# ── Calcular PRTPJ para cada indicador ────────────────────
df["PRTPJ_HPD"]  = ((df["HPD_pre"]  - df["HPD_post"])  / df["HPD_pre"])  * 100
df["PRTPJ_NPPD"] = ((df["NPPD_pre"] - df["NPPD_post"]) / df["NPPD_pre"]) * 100
df["PRTPJ_DCJ"]  = ((df["DCJ_pre"]  - df["DCJ_post"])  / df["DCJ_pre"])  * 100

# ── Calcular diferencias para prueba K-S en SPSS ──────────
df["dif_HPD"]  = df["HPD_pre"]  - df["HPD_post"]
df["dif_NPPD"] = df["NPPD_pre"] - df["NPPD_post"]
df["dif_DCJ"]  = df["DCJ_pre"]  - df["DCJ_post"]

# ── Ordenar columnas detectando las disponibles ────────────
columnas_base = ["Usuario", "Tag"]
columnas_pre  = [c for c in df.columns if c.endswith("_pre")]
columnas_post = [c for c in df.columns if c.endswith("_post")]
columnas_calc = ["PRTPJ_HPD", "PRTPJ_NPPD", "PRTPJ_DCJ",
                 "dif_HPD", "dif_NPPD", "dif_DCJ"]

columnas_orden = columnas_base + columnas_pre + columnas_post + columnas_calc
df = df[columnas_orden]

# ── Guardar dataset completo ───────────────────────────────
df.to_csv("dataset_prepost.csv", index=False)
df.to_excel("dataset_prepost.xlsx", index=False)

# ── Guardar CSV de resultados por separado ─────────────────
resultados = df[["Usuario", "Tag",
                 "HPD_pre",  "HPD_post",  "PRTPJ_HPD",
                 "NPPD_pre", "NPPD_post", "PRTPJ_NPPD",
                 "DCJ_pre",  "DCJ_post",  "PRTPJ_DCJ",
                 "dif_HPD",  "dif_NPPD",  "dif_DCJ"]].copy()

resultados.to_csv("resultados_oe2.csv", index=False)

# ── Resumen en pantalla ────────────────────────────────────
print(f"✅ Archivos generados correctamente")
print(f"   📁 dataset_prepost.csv  → dataset completo para SPSS")
print(f"   📁 dataset_prepost.xlsx → versión Excel")
print(f"   📁 resultados_oe2.csv   → solo resultados pre/post y PRTPJ")
print(f"   Registros: {len(df)}")
print(f"\n📊 Vista previa:")
print(df[["Usuario", "HPD_pre", "HPD_post", "PRTPJ_HPD",
          "NPPD_pre", "NPPD_post", "PRTPJ_NPPD",
          "DCJ_pre",  "DCJ_post",  "PRTPJ_DCJ"]].head(10).to_string(index=False))

print(f"\n📈 Estadísticos básicos de los PRTPJ:")
print(df[["PRTPJ_HPD", "PRTPJ_NPPD", "PRTPJ_DCJ"]].describe().round(2).to_string())

print(f"\n📈 Medias pre vs post:")
for ind in ["HPD", "NPPD", "DCJ"]:
    media_pre  = df[f"{ind}_pre"].mean()
    media_post = df[f"{ind}_post"].mean()
    prtpj      = df[f"PRTPJ_{ind}"].mean()
    print(f"   {ind}: {media_pre:.4f} → {media_post:.4f} | PRTPJ promedio: {prtpj:.2f}%")