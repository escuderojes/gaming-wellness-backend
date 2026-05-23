# ============================================
# SISTEMA PREDICTIVO - GAMING DISORDER
# Escudero Santillan, Jesus Humberto
# Universidad César Vallejo - Lima Norte 2026
#
# ESTRATEGIA:
#   TRAIN → 702 registros sintéticos balanceados
#   TEST  → 252 registros reales (API Riot Games)
# ============================================


# ============================================
# FASE 1 - IMPORTACIÓN DE LIBRERÍAS
# ============================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler, label_binarize
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, classification_report,
    roc_curve, auc
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier


# ============================================
# FASE 2 - CARGAR DATASETS
# ============================================

# TRAIN: sintético balanceado (234 por clase)
df_train = pd.read_csv("data_collector/synthetic_700.csv")
df_train = df_train.drop(columns=["origen"], errors="ignore")

# TEST: exclusivamente datos reales (API Riot Games)
df_test = pd.read_csv("data_collector/dataset_final.csv")

print("\n===================================")
print("DATASETS CARGADOS")
print("===================================")
print(f"Train (sintético) : {len(df_train)} registros")
print(f"Test  (real)      : {len(df_test)} registros")

print("\nDistribución TRAIN:")
print(df_train["Riesgo"].value_counts())

print("\nDistribución TEST (real):")
print(df_test["Riesgo"].value_counts())


# ============================================
# FASE 3 - ANÁLISIS EXPLORATORIO
# ============================================

print("\n===================================")
print("PROMEDIOS POR NIVEL DE RIESGO — TRAIN")
print("===================================")
print(
    df_train.groupby("Riesgo")[
        ["THT","ND","TPP","HPD","NPPD","DCJ"]
    ].mean().round(2)
)

# Distribución clases TRAIN
plt.figure(figsize=(7,5))
order   = ["Bajo","Medio","Alto"]
palette = {"Bajo":"#4CAF50","Medio":"#FF9800","Alto":"#F44336"}
sns.countplot(data=df_train, x="Riesgo", order=order, palette=palette)
plt.title("Distribución de Clases — Dataset de Entrenamiento", fontsize=13)
plt.xlabel("Nivel de Riesgo")
plt.ylabel("Cantidad")
for p in plt.gca().patches:
    plt.gca().annotate(f'{int(p.get_height())}',
        (p.get_x() + p.get_width()/2., p.get_height()),
        ha='center', va='bottom', fontsize=11)
plt.tight_layout()
plt.savefig("fig_distribucion_clases.png", dpi=150)
plt.show()


# ============================================
# FASE 4 - PREPROCESAMIENTO
# ============================================

# Eliminar columnas no relevantes
df_train = df_train.drop(columns=["Usuario","Tag"], errors="ignore")
df_test  = df_test.drop(columns=["Usuario","Tag"], errors="ignore")

# Codificar etiquetas con el mismo encoder
encoder = LabelEncoder()
encoder.fit(["Alto","Bajo","Medio"])   # orden fijo: Alto=0, Bajo=1, Medio=2

df_train["Riesgo"] = encoder.transform(df_train["Riesgo"])
df_test["Riesgo"]  = encoder.transform(df_test["Riesgo"])

print("\n===================================")
print("CLASES CODIFICADAS")
print("===================================")
for i, c in enumerate(encoder.classes_):
    print(f"  {c} -> {i}")

# Variables X e Y
X_train = df_train.drop(columns=["Riesgo"])
y_train = df_train["Riesgo"]

X_test  = df_test.drop(columns=["Riesgo"])
y_test  = df_test["Riesgo"]

print("\n===================================")
print("FEATURES UTILIZADAS")
print("===================================")
print(list(X_train.columns))

print(f"\nTrain: {X_train.shape}  |  Test: {X_test.shape}")
print("\nDistribución TEST real:")
for i, c in enumerate(encoder.classes_):
    print(f"  {c}: {(y_test == i).sum()}")


# ============================================
# ESCALADO (solo para Regresión Logística)
# ============================================

scaler         = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled  = scaler.transform(X_test)


# ============================================
# FASE 5 - DEFINICIÓN DE MODELOS
# ============================================

modelos = {
    "LogisticRegression": LogisticRegression(max_iter=2000, random_state=42),
    "RandomForest"      : RandomForestClassifier(n_estimators=300, random_state=42),
    "XGBoost"           : XGBClassifier(
                              n_estimators=300, learning_rate=0.05,
                              max_depth=5, random_state=42,
                              eval_metric="mlogloss"
                          )
}


# ============================================
# FASE 6 - ENTRENAMIENTO Y MÉTRICAS
# ============================================

resultados         = []
modelos_entrenados = {}

for nombre, modelo in modelos.items():

    print(f"\n===================================")
    print(f"ENTRENANDO: {nombre}")
    print(f"===================================")

    if nombre == "LogisticRegression":
        modelo.fit(X_train_scaled, y_train)
        y_pred = modelo.predict(X_test_scaled)
    else:
        modelo.fit(X_train, y_train)
        y_pred = modelo.predict(X_test)

    modelos_entrenados[nombre] = modelo

    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall    = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1        = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    resultados.append({
        "Modelo"   : nombre,
        "Accuracy" : round(accuracy,  6),
        "Precision": round(precision, 6),
        "Recall"   : round(recall,    6),
        "F1-Score" : round(f1,        6)
    })

    print(f"  Accuracy : {accuracy:.6f}")
    print(f"  Precision: {precision:.6f}")
    print(f"  Recall   : {recall:.6f}")
    print(f"  F1-Score : {f1:.6f}")


# ============================================
# TABLA COMPARATIVA
# ============================================

df_resultados = pd.DataFrame(resultados)

print("\n===================================")
print("COMPARACIÓN DE MODELOS")
print("===================================")
print(df_resultados.to_string(index=False))


# ============================================
# FASE 7 - SELECCIÓN DEL MEJOR MODELO
# ============================================

df_sorted = df_resultados.sort_values(
    by=["F1-Score","Precision"], ascending=[False,False]
)

top_f1   = df_sorted.iloc[0]["F1-Score"]
top_prec = df_sorted.iloc[0]["Precision"]
empate   = df_sorted[
    (df_sorted["F1-Score"]  == top_f1) &
    (df_sorted["Precision"] == top_prec)
]

if len(empate) > 1 and "XGBoost" in empate["Modelo"].values:
    mejor_modelo_nombre = "XGBoost"
else:
    mejor_modelo_nombre = df_sorted.iloc[0]["Modelo"]

print("\n===================================")
print("MEJOR MODELO SELECCIONADO")
print("===================================")
if len(empate) > 1:
    print(f"  ⚠ Empate entre: {list(empate['Modelo'])}")
    print(f"  → Desempate: boosting secuencial + regularización L1/L2 (Chen & Guestrin, 2016)")
print(f"  → Modelo seleccionado: {mejor_modelo_nombre}")

mejor_modelo = modelos_entrenados[mejor_modelo_nombre]


# ============================================
# FASE 8 - VALIDACIÓN CRUZADA (k=5)
# Nota: CV se aplica sobre el dataset sintético
# (el real se reserva exclusivamente para test)
# ============================================

print("\n===================================")
print("VALIDACIÓN CRUZADA (k=5) — datos sintéticos")
print("===================================")

X_cv = X_train_scaled if mejor_modelo_nombre == "LogisticRegression" else X_train

scores = cross_val_score(mejor_modelo, X_cv, y_train, cv=5, scoring="f1_weighted")

print("F1-Score por fold:")
for i, s in enumerate(scores, 1):
    print(f"  Fold {i}: {s:.4f}")
print(f"\n  Promedio  : {scores.mean():.4f}")
print(f"  Desviación: {scores.std():.4f}")


# ============================================
# DATOS DE EVALUACIÓN FINAL (siempre reales)
# ============================================

X_eval      = X_test_scaled if mejor_modelo_nombre == "LogisticRegression" else X_test
y_pred_best = mejor_modelo.predict(X_eval)


# ============================================
# FASE 9 - IMPORTANCIA DE VARIABLES
# ============================================

print("\n===================================")
print("IMPORTANCIA DE VARIABLES")
print("===================================")

if hasattr(mejor_modelo, "feature_importances_"):
    importancias = mejor_modelo.feature_importances_
elif hasattr(mejor_modelo, "coef_"):
    importancias = np.mean(np.abs(mejor_modelo.coef_), axis=0)

df_importancia = pd.DataFrame({
    "Variable"       : X_train.columns,
    "Importancia"    : importancias,
    "Importancia (%)" : importancias / importancias.sum() * 100
}).sort_values(by="Importancia", ascending=False).round(4)

print(df_importancia[["Variable","Importancia (%)"]].to_string(index=False))

plt.figure(figsize=(8,5))
sns.barplot(
    data=df_importancia, x="Importancia (%)", y="Variable",
    hue="Variable", palette="Blues_r", legend=False
)
plt.title(f"Importancia de Variables — {mejor_modelo_nombre}", fontsize=13)
plt.xlabel("Importancia relativa (%)")
plt.tight_layout()
plt.savefig("fig_importancia_variables.png", dpi=150)
plt.show()


# ============================================
# FASE 10 - MATRIZ DE CONFUSIÓN
# ============================================

print("\n===================================")
print("MATRIZ DE CONFUSIÓN — datos reales")
print("===================================")

cm = confusion_matrix(y_test, y_pred_best)
print(cm)

plt.figure(figsize=(7,5))
sns.heatmap(
    cm, annot=True, fmt='d', cmap='Blues',
    xticklabels=encoder.classes_,
    yticklabels=encoder.classes_
)
plt.xlabel("Predicción")
plt.ylabel("Real")
plt.title(f"Matriz de Confusión — {mejor_modelo_nombre}", fontsize=13)
plt.tight_layout()
plt.savefig("fig_matriz_confusion.png", dpi=150)
plt.show()

print("\n===================================")
print("REPORTE DE CLASIFICACIÓN — datos reales")
print("===================================")
print(classification_report(y_test, y_pred_best, target_names=encoder.classes_, digits=4))


# ============================================
# FASE 11 - CURVA ROC
# ============================================

print("\n===================================")
print("CURVA ROC — AUC POR CLASE")
print("===================================")

y_test_bin = label_binarize(y_test, classes=np.unique(y_train))
y_score    = mejor_modelo.predict_proba(X_eval)
n_classes  = y_test_bin.shape[1]

plt.figure(figsize=(9,6))
auc_scores = []

for i in range(n_classes):
    fpr, tpr, _ = roc_curve(y_test_bin[:, i], y_score[:, i])
    roc_auc     = auc(fpr, tpr)
    auc_scores.append(roc_auc)
    plt.plot(fpr, tpr, label=f"{encoder.classes_[i]} (AUC = {roc_auc:.2f})")
    print(f"  {encoder.classes_[i]}: AUC = {roc_auc:.4f}")

auc_macro = np.mean(auc_scores)
print(f"\n  AUC Macro promedio: {auc_macro:.4f}")

plt.plot([0,1],[0,1], linestyle="--", color="gray", label="Azar")
plt.xlabel("Tasa de Falsos Positivos (FPR)")
plt.ylabel("Tasa de Verdaderos Positivos (TPR)")
plt.title(f"Curva ROC — {mejor_modelo_nombre}", fontsize=13)
plt.legend(loc="lower right")
plt.tight_layout()
plt.savefig("fig_curva_roc.png", dpi=150)
plt.show()


# ============================================
# RESUMEN FINAL PARA LA TESIS
# ============================================

print("\n===================================")
print("RESUMEN FINAL — TESIS")
print("===================================")
fila = df_resultados[df_resultados["Modelo"] == mejor_modelo_nombre].iloc[0]
print(f"  Modelo              : {mejor_modelo_nombre}")
print(f"  Train               : {len(df_train)} registros sintéticos")
print(f"  Test                : {len(df_test)} registros reales")
print(f"  Accuracy            : {fila['Accuracy']:.6f}")
print(f"  Precision (weighted): {fila['Precision']:.6f}")
print(f"  Recall    (weighted): {fila['Recall']:.6f}")
print(f"  F1-Score  (weighted): {fila['F1-Score']:.6f}")
print(f"  CV F1 promedio (k=5): {scores.mean():.4f} ± {scores.std():.4f}")
print(f"  AUC Macro promedio  : {auc_macro:.4f}")


# ============================================
# FASE 12 - GUARDAR ARTEFACTOS
# ============================================

print("\n===================================")
print("GUARDANDO ARTEFACTOS")
print("===================================")

joblib.dump(mejor_modelo,  "modelo_gaming.pkl")
joblib.dump(scaler,        "scaler.pkl")
joblib.dump(encoder,       "encoder.pkl")
df_resultados.to_csv("reporte_modelos.csv", index=False)
df_importancia.to_csv("importancia_variables.csv", index=False)

print("""
✅ Artefactos generados:

  modelo_gaming.pkl
  scaler.pkl
  encoder.pkl
  reporte_modelos.csv
  importancia_variables.csv
  fig_distribucion_clases.png
  fig_importancia_variables.png
  fig_matriz_confusion.png
  fig_curva_roc.png
""")