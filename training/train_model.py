# ============================================================
# SISTEMA PREDICTIVO - GAMING DISORDER  (CLASIFICACIÓN BINARIA)
# ============================================================
# Etiqueta: Riesgo_ICOGS_A (1 = en riesgo / 0 = sin riesgo)
# derivada del cuestionario ICOGS-A (12 ítems) por umbral P75
# intra-muestra sobre el pretest. Reemplaza la antigua etiqueta
# heurística de 3 clases (Alto/Medio/Bajo).
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import joblib
from scipy import stats

from sklearn.model_selection import (
    train_test_split,
    cross_val_score,
    StratifiedKFold
)
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, classification_report,
    roc_curve, auc
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.utils.class_weight import compute_sample_weight


# ============================================================
# FASE 2 - CARGAR DATASET REAL (features + etiqueta binaria)
# ============================================================

df = pd.read_csv("data_collector/dataset_final.csv")
df = df.drop(columns=["Usuario", "Tag"], errors="ignore")

# Nombres legibles de las clases binarias (0 -> "Sin riesgo", 1 -> "Riesgo")
CLASES = ["Sin riesgo", "Riesgo"]

print("\n====================================================")
print("DATASET REAL CARGADO (etiqueta binaria ICOGS-A)")
print("====================================================")
print(f"  Total registros : {len(df)}")
print(f"  Variables usadas: {[c for c in df.columns if c != 'Riesgo']}")
print("\nDistribución de la etiqueta:")
for val in [0, 1]:
    n = (df["Riesgo"] == val).sum()
    print(f"  {CLASES[val]} ({val}): {n} ({n/len(df)*100:.1f}%)")


# ============================================================
# FASE 3 - PREPROCESAMIENTO
# ============================================================

# Encoder compatible con model_service: classes_ = ["Sin riesgo","Riesgo"]
# en las posiciones 0 y 1 (sin reordenar alfabéticamente).
encoder = LabelEncoder()
encoder.classes_ = np.array(CLASES)   # índice 0 = "Sin riesgo", 1 = "Riesgo"

X = df.drop(columns=["Riesgo"])
y = df["Riesgo"].astype(int)          # ya es 0/1

print("\n====================================================")
print("CLASES CODIFICADAS")
print("====================================================")
for i, c in enumerate(CLASES):
    print(f"  {c} -> {i}")
print(f"\n  Features finales: {list(X.columns)}")


# ============================================================
# FASE 4 - SPLIT ESTRATIFICADO 80/20
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

print("\n====================================================")
print("SPLIT ESTRATIFICADO 80% / 20%")
print("====================================================")
print(f"  Train : {len(X_train)} registros")
print(f"  Test  : {len(X_test)}  registros (BLOQUEADO hasta Paso 3)")
print("\n  Distribución TRAIN:")
for i, c in enumerate(CLASES):
    n = (y_train == i).sum()
    print(f"    {c}: {n} ({n/len(y_train)*100:.1f}%)")
print("\n  Distribución TEST:")
for i, c in enumerate(CLASES):
    n = (y_test == i).sum()
    print(f"    {c}: {n} ({n/len(y_test)*100:.1f}%)")

scaler     = StandardScaler()
X_train_sc = scaler.fit_transform(X_train)
X_test_sc  = scaler.transform(X_test)


# ============================================================
# PASO 1 — DESARROLLO SOBRE 80% REAL
# ============================================================

print("\n====================================================")
print("PASO 1 — DESARROLLO SOBRE TRAIN (80% real)")
print("====================================================")

# scale_pos_weight para XGBoost binario = n_neg / n_pos (maneja el desbalance)
n_neg = int((y_train == 0).sum())
n_pos = int((y_train == 1).sum())
spw   = n_neg / max(n_pos, 1)

# Modelo ÚNICO: XGBoost (clasificador binario).
mejor_nombre = "XGBoost"
mejor_modelo = XGBClassifier(
    n_estimators=300, learning_rate=0.05, max_depth=5,
    random_state=42, eval_metric="logloss", scale_pos_weight=spw
)

print("\n----------------------------------------------------")
print("CROSS-VALIDATION (k=5, stratified) — XGBoost (80% real)")
print("----------------------------------------------------")

cv         = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores_acc = cross_val_score(mejor_modelo, X_train, y_train, cv=cv, scoring="accuracy")
scores_f1  = cross_val_score(mejor_modelo, X_train, y_train, cv=cv, scoring="f1")
scores_pre = cross_val_score(mejor_modelo, X_train, y_train, cv=cv, scoring="precision")
scores_rec = cross_val_score(mejor_modelo, X_train, y_train, cv=cv, scoring="recall")

print(f"\n  XGBoost")
print(f"    Accuracy mean : {scores_acc.mean():.4f} ± {scores_acc.std():.4f}")
print(f"    Precision mean: {scores_pre.mean():.4f} ± {scores_pre.std():.4f}")
print(f"    Recall mean   : {scores_rec.mean():.4f} ± {scores_rec.std():.4f}")
print(f"    F1  mean      : {scores_f1.mean():.4f}  ± {scores_f1.std():.4f}")

df_resultados = pd.DataFrame([{
    "Modelo": "XGBoost",
    "Accuracy": round(scores_acc.mean(), 4),
    "Precision": round(scores_pre.mean(), 4),
    "Recall": round(scores_rec.mean(), 4),
    "F1-Score": round(scores_f1.mean(), 4),
}])


# ============================================================
# PASO 2 — CONGELAR MODELO
# ============================================================

print("\n====================================================")
print("PASO 2 — MODELO CONGELADO")
print(f"  Entrenando {mejor_nombre} con 100% del train...")
print("====================================================")

mejor_modelo.fit(X_train, y_train)
X_eval = X_test

print(f"  Modelo entrenado con {len(X_train)} registros reales")


# ============================================================
# PASO 3 — EVALUACIÓN FINAL SOBRE 20% REAL
# ============================================================

print("\n====================================================")
print("PASO 3 — EVALUACIÓN FINAL SOBRE TEST (20% real)")
print(f"         ({len(X_test)} registros — nunca vistos)")
print("====================================================")

y_pred = mejor_modelo.predict(X_eval)

acc_f  = accuracy_score(y_test, y_pred)
prec_f = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
rec_f  = recall_score(y_test, y_pred, pos_label=1, zero_division=0)
f1_f   = f1_score(y_test, y_pred, pos_label=1, zero_division=0)

print(f"\n  Accuracy                 : {acc_f:.4f}")
print(f"  Precision (clase Riesgo) : {prec_f:.4f}")
print(f"  Recall    (clase Riesgo) : {rec_f:.4f}")
print(f"  F1-Score  (clase Riesgo) : {f1_f:.4f}")
print(f"\n  Recall Riesgo : {rec_f:.4f}  <- métrica clave (no perder casos en riesgo)")

print("\n----------------------------------------------------")
print("TABLA 7 — REPORTE DE CLASIFICACIÓN")
print("----------------------------------------------------")
print(classification_report(y_test, y_pred, target_names=CLASES, digits=4))

cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
print("Matriz de confusión [filas=real, cols=pred] (orden: Sin riesgo, Riesgo):")
print(cm)

plt.figure(figsize=(6, 5))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=CLASES, yticklabels=CLASES)
plt.xlabel("Predicción"); plt.ylabel("Real")
plt.title(f"Matriz de Confusión — {mejor_nombre}\n(Test 20% real, n={len(X_test)})")
plt.tight_layout(); plt.savefig("fig_matriz_confusion.png", dpi=150); plt.close()


# ============================================================
# IMPORTANCIA DE VARIABLES (TABLA 6)
# ============================================================

print("\n----------------------------------------------------")
print("TABLA 6 — IMPORTANCIA DE VARIABLES")
print("----------------------------------------------------")

if hasattr(mejor_modelo, "feature_importances_"):
    importancias = mejor_modelo.feature_importances_
elif hasattr(mejor_modelo, "coef_"):
    importancias = np.abs(mejor_modelo.coef_).ravel()

df_importancia = pd.DataFrame({
    "Variable": X.columns,
    "Importancia": importancias,
    "Importancia (%)": importancias / importancias.sum() * 100
}).sort_values(by="Importancia", ascending=False).round(4)

print(df_importancia[["Variable", "Importancia (%)"]].to_string(index=False))

plt.figure(figsize=(8, 4))
sns.barplot(data=df_importancia, x="Importancia (%)", y="Variable",
            hue="Variable", palette="Blues_r", legend=False)
plt.title(f"Importancia de Variables — {mejor_nombre}")
plt.xlabel("Importancia relativa (%)")
plt.tight_layout(); plt.savefig("fig_importancia_variables.png", dpi=150); plt.close()


# ============================================================
# CURVA ROC (binaria — clase Riesgo)
# ============================================================

print("\n----------------------------------------------------")
print("CURVA ROC — AUC (clase Riesgo)")
print("----------------------------------------------------")

y_score = mejor_modelo.predict_proba(X_eval)[:, 1]
fpr, tpr, _ = roc_curve(y_test, y_score)
roc_auc = auc(fpr, tpr)
print(f"  AUC (Riesgo vs Sin riesgo): {roc_auc:.4f}")

plt.figure(figsize=(7, 6))
plt.plot(fpr, tpr, label=f"Riesgo (AUC = {roc_auc:.2f})", color="#2E75B6")
plt.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Azar")
plt.xlabel("Tasa de Falsos Positivos (FPR)")
plt.ylabel("Tasa de Verdaderos Positivos (TPR)")
plt.title(f"Curva ROC — {mejor_nombre}")
plt.legend(loc="lower right")
plt.tight_layout(); plt.savefig("fig_curva_roc.png", dpi=150); plt.close()


# ============================================================
# DISTRIBUCIÓN DE RIESGO — TODOS LOS DATOS REALES (TABLA 8)
# ============================================================

print("\n----------------------------------------------------")
print("TABLA 8 — DISTRIBUCIÓN DE RIESGO (n=300)")
print("----------------------------------------------------")

if mejor_nombre == "LogisticRegression":
    y_pred_all = mejor_modelo.predict(scaler.transform(X))
else:
    y_pred_all = mejor_modelo.predict(X)

conteo = pd.Series(y_pred_all).value_counts().reindex([0, 1]).fillna(0).astype(int)
total  = int(conteo.sum())
df_dist = pd.DataFrame({
    "Nivel de Riesgo": CLASES,
    "Cantidad": [conteo.get(0, 0), conteo.get(1, 0)],
    "Porcentaje": [f"{conteo.get(0,0)/total*100:.2f}%", f"{conteo.get(1,0)/total*100:.2f}%"],
})
df_dist_print = pd.concat(
    [df_dist, pd.DataFrame([{"Nivel de Riesgo": "Total", "Cantidad": total, "Porcentaje": "100%"}])],
    ignore_index=True)
print(df_dist_print.to_string(index=False))


# ============================================================
# RESUMEN FINAL
# ============================================================

print("\n====================================================")
print("RESUMEN FINAL — MODELO BINARIO (ICOGS-A)")
print("====================================================")
print(f"  Modelo                   : {mejor_nombre}")
print(f"  Etiqueta                 : Riesgo_ICOGS_A (P75 intra-muestra)")
print(f"  Estrategia               : class_weight / scale_pos_weight balanceado")
print(f"  Variables usadas         : {list(X.columns)}")
print(f"  Train / Test             : {len(X_train)} / {len(X_test)} registros reales")
print(f"  Accuracy                 : {acc_f:.4f}")
print(f"  Precision (Riesgo)       : {prec_f:.4f}")
print(f"  Recall    (Riesgo)       : {rec_f:.4f}")
print(f"  F1-Score  (Riesgo)       : {f1_f:.4f}")
print(f"  AUC                      : {roc_auc:.4f}")


# ── Guardar artefactos ───────────────────────────────────────

joblib.dump(mejor_modelo, "modelo_gaming.pkl")
joblib.dump(scaler,       "scaler.pkl")
joblib.dump(encoder,      "encoder.pkl")
df_resultados.to_csv("reporte_modelos.csv", index=False)
df_importancia.to_csv("importancia_variables.csv", index=False)
df_dist_print.to_csv("tabla_distribucion_riesgo.csv", index=False)

print("""
  Artefactos guardados:
    modelo_gaming.pkl   (clasificador binario)
    scaler.pkl
    encoder.pkl         (classes_ = ['Sin riesgo','Riesgo'])
    reporte_modelos.csv
    importancia_variables.csv
    tabla_distribucion_riesgo.csv
    fig_matriz_confusion.png
    fig_importancia_variables.png
    fig_curva_roc.png
""")
