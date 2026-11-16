# Cliente HTTP para modelos LLM con soporte de Tool Calling (API OpenAI / Groq).
# Usa urllib de la libreria estandar para no agregar dependencias pesadas.

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

HERRAMIENTAS_LLM = [
    {
        "type": "function",
        "function": {
            "name": "consultar_inspecciones",
            "description": "Consulta actas de inspección técnica en predios de Santa Cruz de la Sierra. Filtra por nivel de riesgo, distrito, tipo de predio, campaña, inspector, estado de extintores, fallas eléctricas o rutas obstruidas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster_riesgo": {
                        "type": "string",
                        "enum": ["Bajo", "Medio", "Critico"],
                        "description": "Nivel de riesgo del cluster",
                    },
                    "distrito": {
                        "type": "string",
                        "description": "Distrito Municipal (ej: 'Distrito Urbano 11', 'Distrito Industrial', 'Plan 3000', 'DM-1')",
                    },
                    "tipo_predio": {
                        "type": "string",
                        "description": "Categoría (Comercial, Salud, Educativo, Industrial, Mercado Distrital)",
                    },
                    "campania": {
                        "type": "string",
                        "description": "Nombre o ID de la campaña de fiscalización",
                    },
                    "inspector": {"type": "string", "description": "Nombre del inspector técnico"},
                    "estado_extintores": {
                        "type": "string",
                        "enum": ["Vigente", "Vencido", "No posee"],
                    },
                    "fallas_electricas": {
                        "type": "boolean",
                        "description": "true si tiene fallas eléctricas",
                    },
                    "rutas_obstruidas": {
                        "type": "boolean",
                        "description": "true si las rutas de evacuación están obstruidas",
                    },
                    "scoring_minimo": {
                        "type": "number",
                        "description": "Scoring de riesgo mínimo (0 a 100)",
                    },
                    "solo_ultima_por_predio": {
                        "type": "boolean",
                        "description": "true para ver solo la última acta de cada predio",
                    },
                    "orden": {
                        "type": "string",
                        "enum": ["scoring_desc", "carga_fuego_desc", "fecha_desc", "fecha_asc"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_predios",
            "description": "Consulta el catastro de predios de Santa Cruz de la Sierra con sus datos físicos, hidrante más cercano y última evaluación de riesgo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "distrito": {
                        "type": "string",
                        "description": "Distrito municipal (ej: 'Distrito Industrial', 'DM-8', etc.)",
                    },
                    "tipo_predio": {
                        "type": "string",
                        "description": "Comercial, Salud, Educativo, Industrial, Mercado Distrital",
                    },
                    "cluster_riesgo": {"type": "string", "enum": ["Bajo", "Medio", "Critico"]},
                    "con_reincidencias": {
                        "type": "boolean",
                        "description": "true si tiene infracciones reincidentes",
                    },
                    "sin_inspeccion": {
                        "type": "boolean",
                        "description": "true si nunca ha sido inspeccionado",
                    },
                    "distancia_hidrante_minima": {
                        "type": "number",
                        "description": "Distancia mínima al hidrante en metros (ej: 150 para predios desprotegidos)",
                    },
                    "nombre": {"type": "string", "description": "Búsqueda por nombre del predio"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumen_distritos",
            "description": "Compara los 16 distritos municipales de Santa Cruz de la Sierra: predios inspeccionados, predios críticos, porcentaje crítico, scoring promedio, infracciones y si tienen campaña activa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "orden": {
                        "type": "string",
                        "enum": [
                            "criticos",
                            "porcentaje_critico",
                            "scoring",
                            "infracciones",
                            "nombre",
                        ],
                    },
                    "solo_con_criticos": {
                        "type": "boolean",
                        "description": "true para omitir distritos sin predios críticos",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_infracciones",
            "description": "Consulta las infracciones detectadas en inspecciones o agrupa estadísticas por tipo de infracción, distrito, tipo de predio o mes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agrupar_por": {
                        "type": "string",
                        "enum": ["tipo_infraccion", "distrito", "tipo_predio", "mes"],
                        "description": "Si se especifica, agrupa y totaliza por esta dimensión",
                    },
                    "tipo_infraccion": {
                        "type": "string",
                        "description": "Nombre de la infracción (ej: 'Extintor vencido', 'Cableado expuesto')",
                    },
                    "distrito": {"type": "string"},
                    "tipo_predio": {"type": "string"},
                    "solo_reincidencias": {
                        "type": "boolean",
                        "description": "true para ver solo infracciones reincidentes",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_campanias",
            "description": "Consulta las campañas de fiscalización preventiva: estado, inspectores asignados, predios cubiertos y porcentaje de avance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "estado": {
                        "type": "string",
                        "enum": ["activa", "pendiente", "cerrada", "todas"],
                    },
                    "desde": {"type": "string", "description": "YYYY-MM-DD"},
                    "hasta": {"type": "string", "description": "YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_hidrantes",
            "description": "Consulta la red de hidrantes de Santa Cruz: estado operativo (activo/fuera de servicio), presión nominal, acople y predios que cubre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "estado_operativo": {
                        "type": "string",
                        "enum": ["activo", "fuera_de_servicio", "todos"],
                    },
                    "distrito": {"type": "string"},
                    "tipo_acople": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumen_tipos_predio",
            "description": "Estadísticas agregadas por rubro o tipo de predio (Industrial, Comercial, Educativo, Salud, Mercado): carga de fuego promedio, scoring y porcentaje de riesgo crítico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "distrito": {
                        "type": "string",
                        "description": "Opcional: filtrar por un distrito específico",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_inspectores",
            "description": "Rendimiento y productividad de los inspectores técnicos de la UUBR: actas cerradas, predios inspeccionados y scoring promedio.",
            "parameters": {
                "type": "object",
                "properties": {"desde": {"type": "string"}, "hasta": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "definir_presentacion",
            "description": "Define qué columnas exactas mostrar en el reporte final cuando el usuario solicita ver u ocultar ciertas columnas en su pregunta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columnas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista ordenada de claves de columnas exactas que deben mostrarse.",
                    }
                },
                "required": ["columnas"],
            },
        },
    },
]

PROMPT_SISTEMA = (
    "Eres el Agente Inteligente de Reportes del Cuerpo de Bomberos Voluntarios UUBR de Santa Cruz de la Sierra, Bolivia. "
    "Tu rol es analizar preguntas en lenguaje natural sobre prevención de incendios, fiscalización territorial, "
    "scoring de riesgo (0-100 pts), carga de fuego (NB 58005), estado de extintores, distritos del GAMSC e hidrantes. "
    "INSTRUCCIONES:\n"
    "1. Selecciona la herramienta de consulta más precisa para responder la pregunta.\n"
    "2. Si el usuario pide explícitamente qué datos ver (ej: 'solo quiero ver predio, distrito y scoring'), "
    "utiliza la herramienta 'definir_presentacion' indicando las columnas elegidas.\n"
    "3. Con los datos obtenidos, redacta una respuesta ejecutiva concisa en español (1 o 2 párrafos) con tono profesional, "
    "destacando cifras clave, hallazgos críticos y recomendaciones operativas.\n"
    "4. Nunca inventes cifras ni columnas que no existan en los resultados."
)


class ErrorLlm(Exception):
    pass


def llamar_llm(mensajes: list[dict], tools: list[dict] | None = None) -> dict:
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise ErrorLlm("GROQ_API_KEY no configurada.")

    payload = {
        "model": getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": mensajes,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    url = getattr(settings, "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "UUBR-SIG/1.0",
        },
        method="POST",
    )
    timeout = getattr(settings, "GROQ_TIMEOUT_SEGUNDOS", 30)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Error HTTP de Groq (%s): %s", exc.code, cuerpo)
        raise ErrorLlm(f"Error en proveedor LLM (HTTP {exc.code})") from exc
    except Exception as exc:
        logger.warning("Fallo al conectar con proveedor LLM: %s", exc)
        raise ErrorLlm(f"No se pudo conectar con el proveedor LLM: {exc}") from exc
