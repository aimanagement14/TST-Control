"""Llamadas HTTP a proveedores LLM.

Este modulo encapsula el despacho entre proveedores. Mantiene la
misma API publica (`call_llm`, `_manual_fallback`,
`llm_output_is_manual`) y el mismo contrato:

- Devuelve texto. Si el provider es "manual" o falla, devuelve un
  bloque `## [MODO MANUAL ...]` listo para copiar/pegar.

Lee la configuracion de `CONFIG["llm"]` (provista por app.py). Para
evitar un import circular con app.py, se obtiene via local import
dentro de `call_llm`.
"""

from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)


def _manual_fallback(sys_prompt: str, user_msg: str, reason: str = "") -> str:
    """Devuelve un mensaje en formato manual cuando falla la API."""
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
    """Llama al LLM configurado o devuelve un placeholder para modo manual.

    Soporta:
    - manual: devuelve prompt formateado para copiar
    - openai: cualquier endpoint OpenAI-compatible (incluye MiniMax text API,
      LM Studio, Ollama, etc.)
    - anthropic: API de Claude (requiere SDK `anthropic`; fallback REST)
    - custom: un preset definido por el usuario en CONFIG["llm"]["presets"]
    """
    # Import local para evitar ciclo: app.py -> services.llm -> app.
    from app import CONFIG

    provider = CONFIG["llm"]["provider"]

    preset = None
    preset_name = CONFIG["llm"].get("active_preset")
    if preset_name and CONFIG["llm"].get("presets", {}).get(preset_name):
        preset = CONFIG["llm"]["presets"][preset_name]

    if provider == "manual":
        return "## [MODO MANUAL — Pega aquí la respuesta de tu LLM]\n\n" + (
            "### PROMPT DEL SISTEMA\n"
            f"```\n{sys_prompt}\n```\n\n"
            "### PROMPT DEL USUARIO\n"
            f"```\n{user_msg}\n```\n\n"
            "### INSTRUCCIONES\n"
            "1. Copia el prompt del sistema y del usuario\n"
            "2. Pégalo en tu LLM favorito (ChatGPT, Claude, Gemini, etc.)\n"
            "3. Pega la respuesta en el campo correspondiente abajo"
        )

    if provider in ("openai", "custom"):
        if preset:
            api_key = preset.get("api_key", "")
            base_url = preset.get("base_url", "https://api.openai.com/v1")
            model = preset.get("model", "gpt-4o-mini")
        else:
            api_key = CONFIG["llm"]["openai"]["api_key"]
            base_url = CONFIG["llm"]["openai"]["base_url"]
            model = CONFIG["llm"]["openai"]["model"]
        if not api_key:
            return _manual_fallback(sys_prompt, user_msg, "No hay API key configurada")
        try:
            data = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": CONFIG["llm"]["temperature"],
                "max_tokens": CONFIG["llm"]["max_tokens"],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
        except Exception as e:
            log.exception("call_llm falló contra proveedor %s", provider)
            return _manual_fallback(sys_prompt, user_msg, f"ERROR LLM ({provider}): {e}")

    if provider == "anthropic":
        if preset:
            api_key = preset.get("api_key", "")
            model = preset.get("model", "claude-3-5-sonnet-20241022")
        else:
            api_key = CONFIG["llm"]["anthropic"]["api_key"]
            model = CONFIG["llm"]["anthropic"]["model"]
        if not api_key:
            return _manual_fallback(sys_prompt, user_msg, "No hay API key de Anthropic configurada")
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=CONFIG["llm"]["max_tokens"],
                system=sys_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            return message.content[0].text
        except ImportError:
            try:
                data = json.dumps({
                    "model": model,
                    "max_tokens": CONFIG["llm"]["max_tokens"],
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": user_msg}],
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=data,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                    return payload["content"][0]["text"]
            except Exception as e:
                log.exception("call_llm falló contra Anthropic REST")
                return _manual_fallback(sys_prompt, user_msg, f"ERROR Anthropic: {e}")
        except Exception as e:
            log.exception("call_llm falló contra Anthropic SDK")
            return _manual_fallback(sys_prompt, user_msg, f"ERROR Anthropic: {e}")

    return _manual_fallback(sys_prompt, user_msg, f"Proveedor desconocido: {provider}")
