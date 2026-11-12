# Orquestador del Agente de Reportes (Fase 6 / F7 extendido).
# Maneja Tool Calling con LLM, fallback a reglas, autodeteccion visual y persistencia.

import json
import logging
import uuid

from django.conf import settings
from django.db import transaction

from apps.reportes.models import ReporteDinamico
from apps.usuarios.services import registrar_bitacora

from . import consultas, interprete_reglas, llm_cliente, tabla

logger = logging.getLogger(__name__)

HERRAMIENTAS_MAP = {
    "consultar_inspecciones": consultas.consultar_inspecciones,
    "consultar_predios": consultas.consultar_predios,
    "resumen_distritos": consultas.resumen_distritos,
    "consultar_infracciones": consultas.consultar_infracciones,
    "consultar_campanias": consultas.consultar_campanias,
    "consultar_hidrantes": consultas.consultar_hidrantes,
    "resumen_tipos_predio": consultas.resumen_tipos_predio,
    "consultar_inspectores": consultas.consultar_inspectores,
}


@transaction.atomic
def procesar_consulta_agente(*, pregunta: str, usuario, idempotency_key: str | None = None) -> dict:
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise ValueError("La pregunta o instrucción del reporte no puede estar vacía.")

    if idempotency_key:
        existente = ReporteDinamico.objects.filter(idempotency_key=idempotency_key).first()
        if existente:
            return _formatear_respuesta_bd(existente)

    usar_llm = bool(getattr(settings, "GROQ_API_KEY", ""))
    resultado_agente = None

    if usar_llm:
        try:
            resultado_agente = _ejecutar_ciclo_llm(pregunta)
        except Exception as exc:
            logger.warning("Fallo en ciclo LLM, activando fallback a reglas: %s", exc)
            resultado_agente = None

    if not resultado_agente:
        resultado_agente = _ejecutar_ciclo_reglas(pregunta)

    # Persistencia
    reporte_id = uuid.uuid4()
    columnas_visibles = resultado_agente["columnas"]
    columnas_disponibles = resultado_agente["columnas_disponibles"]

    reporte_obj = ReporteDinamico.objects.create(
        id=reporte_id,
        pregunta=pregunta,
        titulo=resultado_agente["titulo"],
        interpretacion=resultado_agente["interpretacion"],
        columnas=columnas_visibles,
        columnas_disponibles=columnas_disponibles,
        filas=resultado_agente["filas"],
        grafico=resultado_agente["grafico"],
        kpis=resultado_agente["kpis"],
        respuesta_nl=resultado_agente["respuesta_nl"],
        motor=resultado_agente["motor"],
        idempotency_key=idempotency_key,
        generado_por=usuario,
    )

    registrar_bitacora(
        usuario=usuario,
        accion=f"Generar reporte dinamico ({resultado_agente['motor']}): {resultado_agente['titulo'][:80]}",
        entidad_afectada="ReporteDinamico",
    )

    return _formatear_respuesta_bd(reporte_obj)


def _ejecutar_herramienta(nombre: str, args: dict) -> list[dict]:
    if nombre not in HERRAMIENTAS_MAP:
        raise ValueError(f"Herramienta desconocida: {nombre}")
    fn = HERRAMIENTAS_MAP[nombre]
    try:
        return fn(**args)
    except Exception as exc:
        logger.warning("Error ejecutando herramienta %s(%s): %s", nombre, args, exc)
        return []


def _ejecutar_ciclo_llm(pregunta: str) -> dict:
    mensajes = [
        {"role": "system", "content": llm_cliente.PROMPT_SISTEMA},
        {"role": "user", "content": pregunta},
    ]

    herramienta_usada = None
    params_usados = {}
    filas = []
    columnas_elegidas = None

    for _ in range(4):
        msg = llm_cliente.llamar_llm(mensajes, tools=llm_cliente.HERRAMIENTAS_LLM)
        mensajes.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            respuesta_nl = msg.get("content") or ""
            break

        for tc in tool_calls:
            call_id = tc["id"]
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except Exception:
                fn_args = {}

            if fn_name == "definir_presentacion":
                columnas_elegidas = fn_args.get("columnas") or []
                resultado_str = json.dumps(
                    {"status": "ok", "columnas_aplicadas": columnas_elegidas}
                )
            elif fn_name in HERRAMIENTAS_MAP:
                herramienta_usada = fn_name
                params_usados = fn_args
                filas = _ejecutar_herramienta(fn_name, fn_args)
                resultado_str = json.dumps(
                    filas[:30], ensure_ascii=False
                )  # Muestra para el contexto
            else:
                resultado_str = json.dumps({"error": f"Herramienta {fn_name} no existe."})

            mensajes.append({"role": "tool", "tool_call_id": call_id, "content": resultado_str})
    else:
        respuesta_nl = "Reporte generado satisfactoriamente a partir de los datos consolidados."

    if not herramienta_usada:
        # Si el LLM no llamó ninguna herramienta de consulta, fallback suave a inspecciones
        herramienta_usada = "consultar_inspecciones"
        params_usados = {}
        filas = consultas.consultar_inspecciones()

    columnas_visibles, columnas_disponibles = tabla.conformar_columnas(filas, columnas_elegidas)
    grafico = tabla.autodetectar_grafico(columnas_visibles, filas)
    kpis = tabla.calcular_kpis(columnas_visibles, filas)

    titulos_map = {
        "consultar_inspecciones": "Inspecciones Técnicas y Evaluación Pericial",
        "consultar_predios": "Catastro de Predios y Niveles de Riesgo",
        "resumen_distritos": "Resumen y Clasificación de Riesgo por Distritos Municipales",
        "consultar_infracciones": "Registro y Análisis de Infracciones Técnicas",
        "consultar_campanias": "Avance y Estado de Campañas de Fiscalización",
        "consultar_hidrantes": "Estado Operativo de la Red de Hidrantes",
        "resumen_tipos_predio": "Evaluación de Riesgo por Rubro de Edificación",
        "consultar_inspectores": "Rendimiento y Productividad de Inspectores Técnicos",
    }

    return {
        "titulo": titulos_map.get(herramienta_usada, "Reporte Dinámico"),
        "interpretacion": {"herramienta": herramienta_usada, "parametros": params_usados},
        "columnas": columnas_visibles,
        "columnas_disponibles": columnas_disponibles,
        "filas": filas,
        "grafico": grafico,
        "kpis": kpis,
        "respuesta_nl": respuesta_nl
        or interprete_reglas.generar_sintesis_reglas(
            "Reporte Dinámico", herramienta_usada, params_usados, filas
        ),
        "motor": "llm",
    }


def _ejecutar_ciclo_reglas(pregunta: str) -> dict:
    herramienta, params, cols_solicitadas, titulo = interprete_reglas.interpretar_pregunta(pregunta)
    filas = _ejecutar_herramienta(herramienta, params)
    columnas_visibles, columnas_disponibles = tabla.conformar_columnas(filas, cols_solicitadas)
    grafico = tabla.autodetectar_grafico(columnas_visibles, filas)
    kpis = tabla.calcular_kpis(columnas_visibles, filas)
    respuesta_nl = interprete_reglas.generar_sintesis_reglas(titulo, herramienta, params, filas)

    return {
        "titulo": titulo,
        "interpretacion": {"herramienta": herramienta, "parametros": params},
        "columnas": columnas_visibles,
        "columnas_disponibles": columnas_disponibles,
        "filas": filas,
        "grafico": grafico,
        "kpis": kpis,
        "respuesta_nl": respuesta_nl,
        "motor": "reglas",
    }


def _formatear_respuesta_bd(obj: ReporteDinamico) -> dict:
    return {
        "id": str(obj.id),
        "pregunta": obj.pregunta,
        "titulo": obj.titulo,
        "generado_en": obj.fecha_generacion.isoformat(),
        "interpretacion": obj.interpretacion,
        "columnas": obj.columnas,
        "columnas_disponibles": obj.columnas_disponibles,
        "filas": obj.filas,
        "grafico": obj.grafico,
        "kpis": obj.kpis,
        "respuesta_nl": obj.respuesta_nl,
        "motor": obj.motor,
        "presentacion_ia": len(obj.columnas) < len(obj.columnas_disponibles),
        "total_filas": len(obj.filas),
    }
