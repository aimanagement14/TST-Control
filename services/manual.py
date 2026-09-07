"""Modo manual exclusivo.

Esta build (>= 2.0) elimina la integración con OpenAI, Anthropic y los
presets personalizados. La herramienta siempre devuelve un bloque
``## [MODO MANUAL ...]`` con los prompts SYS + USER listos para copiar
a cualquier LLM externo (ChatGPT, Claude, Gemini, etc.).

API publica:
- ``call_llm(sys_prompt, user_msg)``: siempre manual.
- ``llm_output_is_manual(text)``: True si la respuesta es el prompt
  para copiar y no contenido generado.

``_manual_fallback`` queda como helper privado; ya no representa un
fallback de error sino la única salida posible.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _manual_fallback(sys_prompt: str, user_msg: str, reason: str = "") -> str:
    """Devuelve un mensaje en formato manual.

    ``reason`` se conserva por compatibilidad con callers que podrían
    anotar el motivo ("ERROR LLM", etc.); en esta build no se usa pero
    sigue presente para no romper firmas externas durante la migración.
    """
    prefix = f"## [MODO MANUAL — {reason}]\n\n" if reason else "## [MODO MANUAL]\n\n"
    return prefix + (
        "### PROMPT DEL SISTEMA\n"
        f"```\n{sys_prompt}\n```\n\n"
        "### PROMPT DEL USUARIO\n"
        f"```\n{user_msg}\n```\n\n"
        "Copia y pega en tu LLM favorito, luego vuelve aquí con la respuesta."
    )


def llm_output_is_manual(text: str) -> bool:
    """True si la respuesta es el prompt para copiar y no contenido generado."""
    return bool(text) and text.lstrip().startswith("## [MODO MANUAL")


def call_llm(sys_prompt: str, user_msg: str) -> str:
    """Devuelve los prompts formateados para copiar al LLM externo.

    Modo manual exclusivo (>= 2.0): no hace llamadas HTTP, no lee
    credenciales. El usuario copia el bloque resultante en su LLM y
    pega la respuesta de vuelta en el formulario de la etapa.
    """
    return (
        "## [MODO MANUAL — Pega aquí la respuesta de tu LLM]\n\n"
        "### PROMPT DEL SISTEMA\n"
        f"```\n{sys_prompt}\n```\n\n"
        "### PROMPT DEL USUARIO\n"
        f"```\n{user_msg}\n```\n\n"
        "### INSTRUCCIONES\n"
        "1. Copia el prompt del sistema y del usuario\n"
        "2. Pégalo en tu LLM favorito (ChatGPT, Claude, Gemini, etc.)\n"
        "3. Pega la respuesta en el campo correspondiente abajo"
    )
