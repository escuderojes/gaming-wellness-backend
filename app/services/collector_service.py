"""Servicio de recoleccion de datos de un usuario.

Adapta la logica de data_collector/collector3.0.py para procesar UN
solo usuario y reportar el progreso paso a paso (para el modal del
dashboard).

Devuelve un dict con dos partes:
  - "variables": las 6 variables que alimentan el modelo predictivo.
  - "perfil":    datos de identidad del invocador (icono, nivel) que
                 NO van al modelo, solo enriquecen el dashboard.

"""
import os
import time
import random
from datetime import datetime, timedelta
from functools import lru_cache

import requests

RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")

# Routing regional (account-v1, match-v5).
REGION = "americas"
# Plataforma para summoner-v4 (LAS = la2). El proyecto opera en LAS.
PLATFORM = "la2"

# Version de Data Dragon usada para construir la URL del icono de perfil.
# Se intenta leer la ultima version publica; si falla, se usa esta.
DDRAGON_VERSION_FALLBACK = "15.10.1"

# Ventana de observacion: ultimos PERIODO_DIAS dias (no por nro de partidas).
# Garantiza que ND <= PERIODO_DIAS y que HPD sea comparable entre usuarios.
PERIODO_DIAS = 14
# Minimo de partidas en la ventana para considerar la evaluacion valida.
# Si hay menos, se reporta "sin actividad reciente" (Opcion 1 refinada).
MIN_PARTIDAS_VENTANA = 3

# Ventana nocturna para el calculo de PJN (juego nocturno).
NOCHE_INICIO = 22  # 22:00
NOCHE_FIN = 6      # 06:00

# Hitos de progreso (porcentaje, mensaje) que ve el usuario en el modal.
PASOS = [
    (5,   "Conectando con Riot API"),
    (25,  "Descargando ultimas partidas"),
    (55,  "Analizando patrones temporales"),
    (75,  "Calculando HPD / TTS / DCJ / PJN"),
]


@lru_cache(maxsize=1)
def _ddragon_version():
    """Ultima version de Data Dragon (cacheada). Cae al fallback si no hay red."""
    try:
        r = requests.get(
            "https://ddragon.leagueoflegends.com/api/versions.json", timeout=8
        )
        if r.status_code == 200:
            versiones = r.json()
            if versiones:
                return versiones[0]
    except Exception:  # noqa: BLE001
        pass
    return DDRAGON_VERSION_FALLBACK


def _icon_url(icon_id):
    """URL publica del icono de invocador en Data Dragon."""
    return (
        f"https://ddragon.leagueoflegends.com/cdn/"
        f"{_ddragon_version()}/img/profileicon/{icon_id}.png"
    )


def calcular_dcj(dates):
    """DCJ = racha maxima de dias consecutivos con actividad."""
    sorted_days = sorted(set(d.date() for d in dates))
    if not sorted_days:
        return 0
    racha = max_racha = 1
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            racha += 1
        else:
            max_racha = max(max_racha, racha)
            racha = 1
    return max(max_racha, racha)


def _riot_get(url, headers, params=None, reintentos=3):
    """GET a la Riot API con reintento ante rate limit (429)."""
    for _ in range(reintentos):
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code == 429:
            time.sleep(30)
            continue
        if r.status_code == 200:
            return r.json()
        return None
    return None


def _perfil_invocador(puuid, headers):
    """Consulta summoner-v4 para el icono y el nivel del invocador."""
    datos = _riot_get(
        f"https://{PLATFORM}.api.riotgames.com"
        f"/lol/summoner/v4/summoners/by-puuid/{puuid}",
        headers,
    ) or {}
    icon_id = datos.get("profileIconId", 0)
    return {
        "profileIconId": icon_id,
        "summonerLevel": datos.get("summonerLevel", 0),
        "iconUrl": _icon_url(icon_id),
    }


def _recolectar_real(name, tag, on_progress, noche_inicio=NOCHE_INICIO, noche_fin=NOCHE_FIN):
    """Recoleccion real contra la Riot API para un usuario."""
    headers = {"X-Riot-Token": RIOT_API_KEY}

    on_progress(*PASOS[0])
    cuenta = _riot_get(
        f"https://{REGION}.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}",
        headers,
    )
    if not cuenta or "puuid" not in cuenta:
        raise RuntimeError(
            f"No se encontro la cuenta {name}#{tag} "
            "(revisa el Riot ID o la API key)."
        )
    puuid = cuenta["puuid"]

    # Identidad del invocador (icono, nivel) — no va al modelo.
    perfil = _perfil_invocador(puuid, headers)

    on_progress(*PASOS[1])
    # Ventana temporal: partidas de los ultimos PERIODO_DIAS dias.
    # match-v5 acepta startTime (epoch en segundos) para filtrar por fecha.
    start_epoch = int((datetime.now() - timedelta(days=PERIODO_DIAS)).timestamp())
    match_ids = _riot_get(
        f"https://{REGION}.api.riotgames.com"
        f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
        headers,
        params={"startTime": start_epoch, "start": 0, "count": 100},
    )
    if not match_ids or len(match_ids) < MIN_PARTIDAS_VENTANA:
        raise RuntimeError(
            f"Sin actividad reciente: el usuario tiene menos de "
            f"{MIN_PARTIDAS_VENTANA} partidas en los ultimos {PERIODO_DIAS} dias."
        )

    durations, dates = [], []
    total = len(match_ids)
    for i, mid in enumerate(match_ids, start=1):
        match = _riot_get(
            f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{mid}",
            headers,
        )
        time.sleep(0.08)
        if not match:
            continue
        info = match.get("info", {})
        durations.append(info.get("gameDuration", 0) / 3600)
        dates.append(datetime.fromtimestamp(info.get("gameCreation", 0) / 1000))
        # progreso entre 25% y 55% durante la descarga de partidas
        on_progress(25 + int((i / total) * 30),
                    f"Descargando partidas ({i}/{total})")

    if not durations:
        raise RuntimeError("No se pudo leer ninguna partida del usuario.")

    on_progress(*PASOS[3])
    return {
        "variables": _metricas(durations, dates),
        "perfil": perfil,
        "extras": _extras(durations, dates, noche_inicio, noche_fin),
    }


def _metricas(durations, dates):
    """Calcula las 6 variables del modelo a partir de partidas crudas."""
    THT = round(sum(durations), 2)              # tiempo total de horas
    ND = len(set(d.date() for d in dates))      # dias con actividad
    TP = len(durations)                         # total de partidas
    HPD = round(THT / ND, 2) if ND else 0.0     # horas promedio por dia
    NPPD = round(TP / ND, 2) if ND else 0.0     # partidas promedio por dia
    DCJ = calcular_dcj(dates)                   # dias consecutivos de juego
    return {"THT": THT, "ND": ND, "TP": TP, "HPD": HPD, "NPPD": NPPD, "DCJ": DCJ}


def _es_noche(hora, inicio=NOCHE_INICIO, fin=NOCHE_FIN):
    """True si la hora (0-23) cae en la ventana nocturna [inicio, fin).

    La ventana puede cruzar la medianoche (p. ej. 23→07). Los límites
    provienen de la configuración del usuario (Ventana de sueño).
    """
    if inicio == fin:
        return False
    if inicio < fin:               # ventana sin cruce de medianoche
        return inicio <= hora < fin
    return hora >= inicio or hora < fin  # ventana con cruce de medianoche


def _extras(durations, dates, noche_inicio=NOCHE_INICIO, noche_fin=NOCHE_FIN):
    """Metricas adicionales para el dashboard (NO van al modelo):
    PJN (juego nocturno), distribucion por hora y por dia de semana.

    noche_inicio/noche_fin: ventana de sueño configurada por el usuario
    (horas 0-23). Define qué partidas cuentan como juego nocturno.

    Solo se consideran las partidas de la semana ISO en curso
    (lunes → hoy), de modo que el grafico horario y semanal siempre
    refleja los ultimos 7 dias naturales.

    porDiaSemana es el PROMEDIO de horas en cada dia de la semana: se
    suma lo jugado cada lunes/martes/... y se divide entre cuantas
    fechas distintas de ese dia aparecen en la semana filtrada.
    """
    today  = datetime.now().date()
    monday = today - timedelta(days=today.weekday())   # lunes de la semana actual

    # Filtrar solo partidas de la semana en curso (lunes inclusive → hoy inclusive).
    semana = [
        (dur, fecha)
        for dur, fecha in zip(durations, dates)
        if monday <= fecha.date() <= today
    ]

    por_dia_total    = [0.0] * 7              # lunes(0) .. domingo(6)
    dias_por_weekday = [set() for _ in range(7)]
    por_hora         = [0.0] * 24             # horas totales por franja horaria
    noche_horas      = 0.0
    noches           = set()
    dias_activos     = set()

    for dur, fecha in semana:
        wd = fecha.weekday()
        por_dia_total[wd] += dur
        dias_por_weekday[wd].add(fecha.date())
        por_hora[fecha.hour] += dur
        if _es_noche(fecha.hour, noche_inicio, noche_fin):
            noche_horas += dur
            noches.add(fecha.date())
        dias_activos.add(fecha.date())

    nd = len(dias_activos) or 1
    por_dia = [
        round(por_dia_total[i] / len(dias_por_weekday[i]), 2)
        if dias_por_weekday[i] else 0.0
        for i in range(7)
    ]

    # Métricas de semana para alertas y cumplimiento (misma fuente que los gráficos).
    total_horas_semana = sum(dur for dur, _ in semana)
    hpd_semana = round(total_horas_semana / nd, 2)
    # DCJ de la semana: racha máxima de días consecutivos dentro del rango filtrado.
    dcj_semana = calcular_dcj([f for _, f in semana]) if semana else 0

    return {
        # PJN: minutos de juego nocturno promedio por dia activo en la semana.
        "pjnMin": round(noche_horas * 60 / nd, 1),
        "nochesActivas": len(noches),
        "porDiaSemana": por_dia,
        "porHora": [round(x, 2) for x in por_hora],
        # Rango fijo: lunes de la semana actual → hoy.
        "desde": monday.isoformat(),
        "hasta": today.isoformat(),
        # Dias con actividad dentro de la semana (para el subtitulo del grafico).
        "diasActivosSemana": len(dias_activos),
        # Métricas semanales usadas por alertas y cumplimiento.
        "hpdSemana": hpd_semana,                         # h/día activo esta semana
        "ttsSemana": round(total_horas_semana, 2),        # horas reales acumuladas esta semana
        "dcjSemana": dcj_semana,                          # racha máx. de días consecutivos esta semana
    }


def _extras_demo(perfil_juego, THT, ND, noche_inicio=NOCHE_INICIO, noche_fin=NOCHE_FIN):
    """Simula las metricas extra de forma plausible segun el perfil.

    porHora y porDiaSemana usan tts_semana como base comun para que
    ambas graficas del dashboard sean coherentes entre si.
    """
    # Rango de fechas: semana ISO en curso (lunes → hoy).
    hasta = datetime.now().date()
    desde = hasta - timedelta(days=hasta.weekday())
    dias_transcurridos = hasta.weekday() + 1
    dias_activos_semana = random.randint(1, min(int(ND), dias_transcurridos))

    # tts_semana = horas reales de la semana: BASE ÚNICA para ambas gráficas.
    hpd_semana = round(THT / max(ND, 1), 2)
    tts_semana = round(hpd_semana * dias_activos_semana, 2)
    dcj_semana = min(dias_activos_semana, dias_transcurridos)

    # porDiaSemana: distribuye tts_semana entre los 7 días.
    pesos = [random.uniform(0.4, 1.6) for _ in range(7)]
    s_pesos = sum(pesos) or 1
    por_dia = [round(tts_semana * w / s_pesos, 2) for w in pesos]

    # porHora: distribuye tts_semana con forma horaria realista que
    # VARÍA por usuario. Se parte de una curva base (más juego por la
    # tarde-noche) y se desplaza el "pico" de juego a una hora aleatoria
    # propia de cada jugador, con jitter por franja, de modo que ningún
    # histograma sea idéntico a otro.
    base = [3, 2, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 11, 11,
            12, 13, 15, 17, 19, 21, 22, 20, 12, 6]
    desplazamiento = random.randint(-4, 4)          # corre el pico de cada usuario
    forma = [0.0] * 24
    for h in range(24):
        v = base[(h - desplazamiento) % 24]
        v *= random.uniform(0.55, 1.45)             # jitter por franja
        forma[h] = max(v, 0.0)
    # Realce nocturno según el perfil (más madrugada = mayor riesgo).
    if perfil_juego == "alto":
        for h in (22, 23, 0, 1, 2, 3):
            forma[h] *= random.uniform(2.2, 3.4)
    elif perfil_juego == "medio":
        for h in (22, 23, 0, 1):
            forma[h] *= random.uniform(1.4, 2.1)
    s_forma = sum(forma) or 1
    por_hora = [round(tts_semana * f / s_forma, 2) for f in forma]

    noche_horas = sum(por_hora[h] for h in range(24)
                      if _es_noche(h, noche_inicio, noche_fin))
    return {
        "pjnMin": round(noche_horas * 60 / max(dias_activos_semana, 1), 1),
        "nochesActivas": random.randint(0, min(dias_activos_semana, 7)),
        "porDiaSemana": por_dia,
        "porHora": por_hora,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "diasActivosSemana": dias_activos_semana,
        "hpdSemana": hpd_semana,
        "ttsSemana": tts_semana,
        "dcjSemana": dcj_semana,
    }


def _recolectar_demo(name, tag, on_progress, noche_inicio=NOCHE_INICIO, noche_fin=NOCHE_FIN):
    """Simula la recoleccion (sin red) con metricas plausibles."""
    for pct, msg in PASOS:
        on_progress(pct, msg)
        time.sleep(random.uniform(2.0, 3.5))

    perfil_juego = random.choice(["bajo", "medio", "alto"])
    if perfil_juego == "alto":
        HPD = round(random.uniform(5.0, 8.0), 2)
        DCJ = random.randint(6, 9)
        NPPD = round(random.uniform(7.0, 11.0), 2)
    elif perfil_juego == "medio":
        HPD = round(random.uniform(3.2, 4.8), 2)
        DCJ = random.randint(4, 6)
        NPPD = round(random.uniform(4.0, 7.0), 2)
    else:
        HPD = round(random.uniform(1.0, 2.8), 2)
        DCJ = random.randint(1, 3)
        NPPD = round(random.uniform(1.5, 4.0), 2)

    # Ventana de 14 dias: ND no puede superar PERIODO_DIAS.
    # Se elige ND segun el perfil y se deriva TP = NPPD * ND.
    ND = random.randint(max(3, PERIODO_DIAS // 3), PERIODO_DIAS)
    TP = max(ND, int(round(NPPD * ND)))
    NPPD = round(TP / ND, 2)            # recalcula NPPD exacto sobre ese ND
    DCJ = min(DCJ, ND)                  # la racha no puede exceder los dias
    THT = round(HPD * ND, 2)
    variables = {"THT": THT, "ND": ND, "TP": TP,
                 "HPD": HPD, "NPPD": NPPD, "DCJ": DCJ}

    # Identidad simulada: un icono real de Data Dragon (rango seguro 0-28).
    icon_id = random.randint(0, 28)
    perfil = {
        "profileIconId": icon_id,
        "summonerLevel": random.randint(30, 450),
        "iconUrl": _icon_url(icon_id),
    }
    return {
        "variables": variables,
        "perfil": perfil,
        "extras": _extras_demo(perfil_juego, THT, ND, noche_inicio, noche_fin),
    }


def _hora_de(valor, defecto):
    """Convierte 'HH:MM' (config Ventana de sueño) a hora entera 0-23."""
    try:
        return int(str(valor).split(":")[0])
    except (TypeError, ValueError, IndexError):
        return defecto


def recolectar_usuario(name, tag, on_progress, demo=False, config=None):
    """Recolecta las variables del modelo + el perfil de un usuario.

    Devuelve: {"variables": {...}, "perfil": {...}, "extras": {...}}.
    on_progress(pct, mensaje) se llama en cada hito del proceso.
    config: dict opcional con la Ventana de sueño del usuario
            (sleepStart / sleepEnd en formato 'HH:MM') que define la
            franja de juego nocturno para el cálculo del PJN.
    Si demo=True o no hay RIOT_API_KEY, se usa el modo simulado.
    """
    cfg = config or {}
    ni = _hora_de(cfg.get("sleepStart"), NOCHE_INICIO)
    nf = _hora_de(cfg.get("sleepEnd"), NOCHE_FIN)
    if demo or not RIOT_API_KEY:
        return _recolectar_demo(name, tag, on_progress, ni, nf)
    return _recolectar_real(name, tag, on_progress, ni, nf)
