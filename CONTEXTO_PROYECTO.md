# Contexto del Proyecto — Gaming Wellness Prevent

> Documento de continuidad. Resume qué se hizo, qué falta y qué sigue,
> para retomar el trabajo en cualquier sesión nueva.
> **Última actualización:** 1 de junio de 2026 (sesión de reformulación).

---

## 0. Cambios clave de la reformulación (LEER PRIMERO)

Esta sección resume los cambios estructurales más recientes. El resto del
documento conserva el historial; ante cualquier contradicción, **manda esta
sección**.

### Indicadores oficiales de la tesis (4)
La variable dependiente se operacionaliza con **4 indicadores**, agrupados
en 3 dimensiones / objetivos específicos:

| Dimensión (OE) | Indicador | Fórmula |
|---|---|---|
| OE1 · Intensidad | **HPD** | THT / ND |
| OE2 · Frecuencia | **NPPD** | TPP / ND |
| OE2 · Frecuencia | **DCJ** | max(racha de días consecutivos) |
| OE3 · Control | **ICOGS-A** | Σ ítems (12 ítems, rango 12–60) |

- Se **eliminó** el indicador FBG (binge gaming) que se había propuesto.
- El antiguo NPPD/PRTPJ y otros derivados quedaron fuera como indicadores.
- `PJN` (juego nocturno) y `TTS` (tiempo total semana) son **métricas
  complementarias** del dashboard, NO indicadores de la tesis.

### Instrumento ICOGS → ICOGS-A
- Pasó de **8 ítems (rango 8–40)** a **12 ítems (rango 12–60)**.
- Ítems invertidos {2,3,4,5,6,8} se recodifican (6 − valor) antes de sumar.
- Confiabilidad piloto (n=50): **α de Cronbach = 0.925** (12 ítems).
- Datos en `D:\...\OE3\` (carpeta de la tesis): `icogs_a_dataset.csv`,
  `icogs_a_spss.csv`.

### Etiqueta de riesgo = EXTERNA (no heurística)
- **Antes:** la etiqueta Alto/Medio/Bajo se derivaba de las mismas
  variables de juego (circular).
- **Ahora:** la etiqueta sale del **ICOGS-A por percentiles**. Corte:
  **riesgo = puntaje ICOGS-A ≥ P75**. El collector **ya no calcula riesgo**:
  solo extrae indicadores conductuales; la etiqueta se asigna aparte.

### Modelo
- **XGBoost binario** (clases del encoder: `["Sin riesgo", "Riesgo"]`).
- `train_model.py` entrena **solo XGBoost** (sin comparar 3 modelos).
- Métricas test (20%): Accuracy ≈ 0.87, Recall(Riesgo) ≈ 0.76, AUC ≈ 0.96.
- `ND` sigue siendo el predictor dominante (~74.8%).
- Dataset de entrenamiento: `data_collector/dataset_final.csv` =
  features de pretest + etiqueta binaria del ICOGS-A.

### Niveles visuales = 3 bandas derivadas del score
El modelo es binario, pero la **presentación** usa 3 niveles deducibles del
score 0–100 (= probabilidad de "Riesgo"):
- **Bajo**: score < 50
- **Medio**: 50 ≤ score < 75
- **Alto**: score ≥ 75 (corresponde al P75 del ICOGS-A)

`model_service.predecir()` devuelve `nivel` (Alto/Medio/Bajo, para mostrar),
`clase` ("Riesgo"/"Sin riesgo"), `en_riesgo` (bool), `score` y
`probabilidades`. La función `nivel_visual(score)` hace el mapeo.

### Ventana de sueño / PJN (arreglado)
- Antes la ventana configurable (sleepStart/sleepEnd) **no se usaba**: el
  PJN se calculaba con franja fija 22:00–06:00.
- Ahora `collect_routes` lee la config del usuario y la pasa a
  `recolectar_usuario(..., config=cfg)`; `_es_noche(hora, ini, fin)` respeta
  la ventana (incluso si cruza medianoche).

### Dashboard (frontend)
- Tarjetas principales de indicadores: **HPD, THT, DCJ, NPPD** (grilla 2×2).
- Barra horizontal de métricas complementarias: **PJN, TTS, ND**.
- Niveles Alto/Medio/Bajo en medidor, banner, historial y colores.
- Distribución horaria del modo demo ahora **varía por usuario** (pico
  desplazado + jitter), ya no es una silueta fija.

---

## 1. Qué es el proyecto

Sistema predictivo de **uso excesivo en gaming** (tesis de Jesús Humberto
Escudero Santillán — Universidad César Vallejo, Lima Norte). Clasifica el
riesgo (**Alto / Medio / Bajo**) de un jugador de *League of Legends* a
partir de sus hábitos de juego, y lo presenta en un dashboard web.

El proyecto tiene dos partes, en dos carpetas separadas:

- **`D:\Backend`** — API en Flask + modelo de Machine Learning entrenado.
- **`D:\frontend`** — Aplicación web en Vite + React 19.

---

## 2. Estado del BACKEND (`D:\Backend`)

API Flask que se levanta con `python run.py` en el puerto **5000**.

### Modelo de ML  (ver sección 0 para el detalle vigente)
- Algoritmo: **XGBoost binario**. Clases del encoder: `["Sin riesgo","Riesgo"]`.
- Etiqueta de entrenamiento: **externa**, del ICOGS-A (riesgo si ≥ P75).
- **6 variables de entrada (features), orden EXACTO** del `.pkl`:
  `THT, ND, TP, HPD, NPPD, DCJ`. (De estas, 4 son indicadores de la tesis;
  el modelo usa las 6 como features, pero `ND` domina ~74.8%.)
- Artefactos en la raíz de `D:\Backend`: `modelo_gaming.pkl`, `scaler.pkl`,
  `encoder.pkl`.
- Script de entrenamiento: `training/train_model.py` (solo XGBoost).
- Dataset: `data_collector/dataset_final.csv` (features pretest + etiqueta
  binaria ICOGS-A).
- Métricas test (20%): Accuracy ≈ 0.87, Recall(Riesgo) ≈ 0.76, AUC ≈ 0.96.

### Estructura de carpetas
```
app/
 ├─ __init__.py            create_app(): registra blueprints + Swagger
 ├─ routes/
 │   ├─ prediction_routes.py   POST /api/predict
 │   ├─ collect_routes.py      POST /api/collect · GET /api/collect/<id>
 │   ├─ dashboard_routes.py    GET /api/dashboard·historial·config·perfil · PUT /api/config
 │   └─ auth_routes.py         (vacío, sin usar)
 └─ services/
     ├─ model_service.py       carga del modelo + función predecir()
     ├─ jobs.py                gestor de trabajos en segundo plano (en memoria)
     ├─ collector_service.py   recolectar_usuario() — modo real + demo
     ├─ firestore_service.py   persistencia en Firestore (usuarios + recolecciones)
     └─ recomendaciones.py     capa de reglas (alertas/tips + cumplimiento)
data_collector/             colector original (collector3.0.py) y datasets
training/                   train_model.py
DATOS DE ML/                figuras y CSV de resultados del modelo
```

### Endpoints listos y probados
- **`POST /api/predict`** — recibe las 6 variables, devuelve `nivel`
  (Alto/Medio/Bajo derivado del score), `nivel_label`, `clase`
  ("Riesgo"/"Sin riesgo"), `en_riesgo` (bool), `score` (0-100 = P(Riesgo))
  y `probabilidades`.
- **`POST /api/collect`** — inicia la recolección de un usuario en segundo
  plano; devuelve un `job_id` (código 202). Acepta un `uid` opcional
  (Firebase Auth): si se envía, la recolección se guarda en Firestore al
  terminar. También admite `email`, `displayName` y `region` opcionales.
- **`GET /api/collect/<job_id>`** — consulta progreso/estado/resultado del job.
- **`GET /api/dashboard?uid=...`** — estado actual: la recolección más
  reciente del usuario + su config.
- **`GET /api/historial?uid=...&limite=N`** — últimas N recolecciones.
- **`GET /api/config?uid=...`** · **`PUT /api/config`** — leer/actualizar la
  configuración del usuario.
- **`GET /api/perfil?uid=...`** — datos del usuario + agregados sobre todas
  sus recolecciones.
- **`GET /api/recomendaciones?uid=...`** — alertas, tips y cumplimiento
  generados por la capa de reglas.
- **Swagger UI** disponible en `http://localhost:5000/apidocs/` (flasgger).

### Servicio de recolección (`collector_service.py`)
Adaptación de `data_collector/collector3.0.py` para procesar **un solo
usuario** y reportar progreso. Dos modos:
- **real**: consulta la Riot API. Requiere la variable de entorno
  `RIOT_API_KEY` con una key vigente (las dev keys caducan cada 24h).
- **demo**: simula el proceso sin red, con métricas plausibles aleatorias.
  Es el modo por defecto si no hay `RIOT_API_KEY` configurada.

---

## 3. Estado del FRONTEND (`D:\frontend`)

Aplicación Vite + React 19 (`npm run dev`). Dependencias: `react-router-dom`,
`firebase`, `axios`.

### Lo que está hecho
- **Login** (`src/pages/Auth.jsx`): diseño completo integrado desde el
  prototipo, con **Firebase Authentication** (correo/contraseña), registro,
  recuperación de contraseña. Responsive.
- **Dashboard**: las 5 vistas convertidas a React desde los prototipos —
  `DashboardPage`, `HistorialPage`, `RecomendacionesPage`,
  `ConfiguracionPage`, `PerfilPage` (en `src/pages/dashboard/`).
- **Layout** (sidebar + topbar) y **CollectingModal** (modal con
  temporizador de recolección).
- Estilos del prototipo convertidos y **scopeados** para que login y
  dashboard no choquen: `src/styles/auth.css` (bajo `.gw-auth`) y
  `src/styles/dashboard.css` (bajo `.gw-app`).
- Rutas (`src/routes/AppRouter.jsx`): `/` = login, `/dashboard` = protegido.
- Config de Firebase en `src/services/firebase.js` (proyecto `tesis-f4bdb`).
- Dashboard responsive (breakpoints + sidebar que se auto-colapsa).

### Conexión con el backend (parcial — 22 may 2026)
- `src/services/api.js` — cliente axios con funciones para todos los
  endpoints (`iniciarCollect`, `consultarJob`, `getDashboard`, `getHistorial`,
  `getConfig`, `putConfig`, `getPerfil`, `predecir`). URL base configurable
  con `VITE_API_URL` (por defecto `http://localhost:5000/api`).
- **Flujo de recolección REAL conectado**: el botón "Buscar" llama a
  `POST /api/collect` con el `uid` del usuario logueado; el `CollectingModal`
  hace polling de `GET /api/collect/<job_id>` y muestra el progreso y los
  pasos verdaderos. Maneja fases loading / done / error.
- **`DashboardPage`** lee la última recolección real desde `GET /api/dashboard`:
  el medidor de riesgo (score + nivel Alto/Medio/Bajo), las 4 tarjetas de
  indicadores (**HPD, THT, DCJ, NPPD** en grilla 2×2), la barra de métricas
  complementarias (**PJN, TTS, ND**), el avatar/ícono de invocador y la
  tarjeta `ModelBreakdown` (probabilidades del modelo + las 6 variables)
  muestran datos reales. Tiene estados de carga y vacío. El layout se reorganizó
  en filas (22 may): perfil/indicadores/desglose · distribución horaria
  (ancha) + metas · promedio por día + comparativa · tips.
- **Comparativa antes/después** (`Comparative`): compara el HPD de la
  primera recolección contra la más reciente (usa `GET /api/historial`).
- **Avatar de invocador**: el colector trae `profileIconId`/`summonerLevel`
  (Riot summoner-v4 en modo real; aleatorio en demo) y construye la URL del
  ícono con Data Dragon. Se muestra en el topbar y en la tarjeta de perfil.

### Vistas conectadas (22 may 2026)
- **`ConfiguracionPage`** → `GET`/`PUT /api/config`: carga y guarda las
  metas (hpdMax, ttsMax, dcjMax), la ventana de sueño y la sensibilidad.
  La tarjeta "Recordatorios" sigue como UI local (notificaciones no
  implementadas).
- **`PerfilPage`** → `GET /api/perfil`: identidad real del invocador +
  agregados (total de recolecciones, promedios de las 6 variables,
  distribución de niveles de riesgo).
- **`HistorialPage`** → `GET /api/historial`: lista real de recolecciones
  con filtro por nivel, resumen por nivel y tendencia del score.

- **`RecomendacionesPage`** → `GET /api/recomendaciones`: lista de
  alertas/tips reales (capa de reglas) + resumen de cumplimiento.

### Métricas extra del colector (22 may 2026)
El colector calcula, además de las 6 variables, un dict `extras`:
`pjnMin` (juego nocturno), `nochesActivas`, `porHora` (24 valores),
`porDiaSemana` (7 valores = PROMEDIO de horas en cada día de la semana)
y el rango `desde`/`hasta` que abarcan las partidas. Se guarda en cada
recolección y llega al dashboard. Con eso, en `DashboardPage` son reales:
la tarjeta **PJN**, la **distribución horaria de juego** y el **promedio
por día de la semana** (con su rango de fechas).

### Lo que SIGUE con datos de ejemplo (mock)
- En `DashboardPage`: las **metas semanales** (`WeeklyGoals`) y los **tips
  preventivos** (`PreventionTips`) siguen con datos de ejemplo. La
  comparativa antes/después ya es real (primera vs última recolección).
- La tarjeta de **recordatorios** (en Configuración/Recomendaciones) es UI:
  no hay sistema de notificaciones.
- Tendencia: `HistorialPage` ya muestra una tendencia real del score; falta
  una de TTS por semana si se quiere.

---

## 4. Estado actual y qué sigue

Todo el flujo principal está conectado y funcionando con datos reales:
login con Firebase, recolección real vía Riot API, persistencia en
Firestore, los 6 endpoints del backend, la capa de reglas y las 5 vistas
del frontend. El dashboard fue reorganizado en filas (22 may) y casi
todas sus tarjetas usan datos reales.

Lo que queda — todo opcional / de pulido:
1. Secciones aún mock en `DashboardPage`: tips preventivos
   (`PreventionTips`). La tarjeta de recordatorios (Configuración /
   Recomendaciones) es solo UI (sin notificaciones reales).
2. **Verificación del token de Firebase** en el backend: hoy el `uid`
   llega del cliente y se confía. Para producción, validar el ID token.
3. **Desplegar los cambios**: backend a Render (`git push` → redeploy
   automático) y frontend a Firebase (`npm run build` + `firebase deploy`).
   Los cambios de la reformulación están en disco local pero la app web
   usa los servicios desplegados hasta que se publiquen.
4. Tras desplegar, **generar una recolección nueva** para ver los datos
   recalculados (el dashboard muestra la última recolección guardada).

### Firestore — ✅ HECHO (21 may 2026)
- Firestore Database habilitado en la consola (proyecto `tesis-f4bdb`,
  edición Standard, modo producción).
- Clave de servicio en `D:\Backend\firebase-key.json` (protegida por
  `.gitignore`).
- `firebase-admin` instalado en el `venv`.
- `app/services/firestore_service.py` creado y probado con
  `test_firestore.py` (escribe/lee/borra OK).
- Se añadieron `.gitignore` y `requirements.txt` a la raíz del backend.

Funciones disponibles en `firestore_service.py`:
`firestore_disponible()`, `estado()`, `crear_o_actualizar_usuario(uid, datos)`,
`obtener_usuario(uid)`, `obtener_config(uid)`, `guardar_config(uid, config)`,
`guardar_recoleccion(uid, variables, prediccion, demo, extras)`,
`obtener_recolecciones(uid, limite)`, `obtener_ultima_recoleccion(uid)`.

---

## 5. Roadmap — lo que falta

En orden sugerido:

1. **Firestore** — ✅ hecho (persistencia por usuario lista).
2. **Conectar el dashboard con el backend** — ✅ hecho: `CollectingModal`
   usa `/api/collect` real con progreso verdadero, y las 5 vistas leen
   datos reales de sus endpoints.
3. **Capa de reglas** — ✅ hecho (`app/services/recomendaciones.py`):
   genera alertas/tips deterministicos y el cumplimiento. Falta solo el
   plan semanal por día (depende de métricas extra del colector).
4. **Endpoints del dashboard** — ✅ hechos salvo `/api/recomendaciones`
   (depende de la capa de reglas, item 3).
5. **Métricas extra** — ✅ hecho en su mayoría: el colector calcula `extras`
   (PJN, distribución por hora y por día de la semana) junto a las 6
   variables, y se guardan en cada recolección. Queda opcional: TTS por
   semana para una gráfica de tendencia adicional.
6. **Verificación del token de Firebase** en el backend (opcional, para que
   cada usuario solo acceda a sus datos).

---

## 6. Modelo de datos de Firestore (ya definido)

```
usuarios  (colección)
 └─ {uid}  ← documento, identificado por el uid de Firebase Auth
     ├─ email, displayName
     ├─ riotId:  "Invoker#LAS1"
     ├─ region:  "LAS"
     ├─ profileIconId, summonerLevel, iconUrl   ← identidad del invocador
     ├─ creado, ultimaActividad
     ├─ config:  { hpdMax, ttsMax, dcjMax, sleepStart, sleepEnd,
     │             sensibilidad, recordatorios... }
     │
     └─ recolecciones  (subcolección)
         └─ {autoId}  ← un documento por CADA extracción ("Buscar")
             ├─ fecha:       timestamp
             ├─ demo:        true / false
             ├─ variables:   { THT, ND, TP, HPD, NPPD, DCJ }
             ├─ prediccion:  { nivel, score, probabilidades }
             └─ extras:      { pjnMin, nochesActivas, porHora,
                               porDiaSemana, desde, hasta }
```

- **Dashboard** (estado actual) → la recolección más reciente.
- **Gráfica de tendencia** → las últimas N recolecciones por fecha.
- **Perfil** → agregados sobre todas las recolecciones.
- **Configuración** → el mapa `config` embebido en el documento del usuario.
- **Historial de alertas** → se generará con la capa de reglas (pendiente
  decidir si se guardan en una subcolección o se calculan al vuelo).

---

## 7. Notas técnicas importantes (gotchas)

Cosas descubiertas durante el trabajo que conviene recordar:

- **Variables del modelo**: el orden exacto es `THT, ND, TP, HPD, NPPD, DCJ`.
  El colector llama `TPP` a lo que el modelo llama `TP` (el endpoint acepta
  ambos como alias).
- **Riot API key**: estaba escrita directamente en `collector3.0.py`. En el
  backend nuevo se lee de la variable de entorno `RIOT_API_KEY`. Las dev
  keys de Riot caducan cada 24 horas.
- **Score 0-100**: se deriva de las probabilidades del modelo con la fórmula
  `Bajo·15 + Medio·55 + Alto·90`.
- **Estilos del frontend**: `auth.css` va scopeado bajo `.gw-auth` y
  `dashboard.css` bajo `.gw-app` para que los dos sistemas de diseño no
  choquen (ambos definían clases con los mismos nombres).
- **Windows no distingue mayúsculas** en nombres de archivo (`Auth.css` y
  `auth.css` son el mismo archivo) — cuidado al renombrar.
- El almacén de jobs (`jobs.py`) es **en memoria**: se reinicia cuando se
  reinicia el servidor. Suficiente para desarrollo.

---

## 8. Cómo ejecutar el proyecto

**Backend:**
```
cd D:\Backend
venv\Scripts\activate
python run.py
```
→ API en `http://localhost:5000` · Swagger en `http://localhost:5000/apidocs/`

**Frontend:**
```
cd D:\frontend
npm run dev
```
→ abre la URL que muestre la consola.

---

## 9. Credenciales y configuración

- **Firebase** — proyecto `tesis-f4bdb`. Config del cliente en
  `D:\frontend\src\services\firebase.js`.
- **Firestore** — clave de servicio en `D:\Backend\firebase-key.json`
  (secreta, ignorada por Git). Variable opcional `FIREBASE_KEY_PATH` para
  cambiar la ruta.
- **Riot API** — la clave se lee de `RIOT_API_KEY`, cargada desde un archivo
  `D:\Backend\.env` (vía `python-dotenv` en `run.py`). El `.env` está en el
  `.gitignore`. Se obtiene del portal de desarrolladores de Riot y la dev key
  caduca cada 24h. Sin clave => el colector usa modo demo automáticamente.
  El colector usa routing `americas` (account/match) y plataforma `la2`
  (LAS) para summoner-v4. En modo real recolecta 60 partidas fijas.

---

## 10. Resumen de avance

| Área | Estado |
|------|--------|
| Frontend — login con Firebase | ✅ Hecho |
| Frontend — dashboard (5 vistas, diseño) | ✅ Hecho |
| Frontend — `api.js` + recolección real | ✅ Hecho |
| Frontend — `DashboardPage` con datos reales | ✅ Hecho |
| Frontend — Historial / Config / Perfil conectados | ✅ Hecho |
| Backend — capa de reglas (recomendaciones.py) | ✅ Hecho |
| Frontend — Recomendaciones conectada | ✅ Hecho |
| Colector — métricas extra (PJN, distribuciones) | ✅ Hecho |
| Frontend — responsive | ✅ Hecho |
| Backend — `/api/predict` alineado al modelo | ✅ Hecho |
| Backend — `/api/collect` + progreso | ✅ Hecho |
| Backend — Swagger | ✅ Hecho |
| Backend — Firestore (persistencia) | ✅ Hecho |
| Backend — `/api/collect` persiste en Firestore | ✅ Hecho |
| Backend — endpoints del dashboard | ✅ Hecho |
| Frontend — 5 vistas conectadas a endpoints | ✅ Hecho |
| Dashboard — layout reorganizado en filas | ✅ Hecho |
| Verificación del token de Firebase (backend) | ⬜ Pendiente (opcional) |
