"""Parsers puros de respuestas LLM.

Funciones puras: solo operan sobre el texto recibido y devuelven
dicts/listas. No tocan Flask, ni `CONFIG`, ni la DB.

Cada parser es responsable de un único formato de salida:
- `parse_research`: investigación con secciones ## (RESUMEN, HECHOS
  CONFIRMADOS, TEORÍAS, FUENTES, …).
- `parse_concept`: concepto con secciones ## (ÁNGULO, TESIS, …).
- `parse_script`: guion largo o corto con secciones ## (HOOK,
  CONTEXTO, DESARROLLO, REVELACIONES, CONCLUSIÓN, CTA).
- `parse_scenes_json`: extrae una lista JSON de escenas.
- `parse_scenes_tst`: extrae escenas en formato TST Scene Director
  (ESCENA N + TEXTO AUDIO + IMAGEN).
- `parse_scenes`: dispatcher TST → JSON.
- `parse_prompt_json`: extrae un dict JSON de un prompt.
- `parse_metadata`: metadata por plataforma (titles, description,
  chapters, tags, hashtags, caption, hook, cta, on_screen_text).
- `parse_thumbnail`: extrae el bloque `## MINIATURA`.

Más dos helpers de utilidad para QC: `count_words` y
`estimate_duration_seconds`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import cast

# Logger del modulo: usa el namespace 'tst.services.parsers' para que
# el basicConfig del arranque (T0.4) lo canalice por el handler global.
log = logging.getLogger(__name__)


def count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def estimate_duration_seconds(text: str | None, wpm: int = 150) -> int:
    """Estima la duración de narración en segundos según palabras por minuto."""
    words = count_words(text)
    if wpm <= 0:
        wpm = 150
    return int(words / wpm * 60)


def parse_research(text: str) -> dict[str, str | list[str]]:
    """Parsea una respuesta de investigación en el formato estructurado."""
    sections: dict[str, str | list[str]] = {
        "content": "",
        "sources": [],
        "facts": [],
        "theories": [],
        "unverified": [],
    }
    sections_map = {
        "RESUMEN": "content",
        "HECHOS CONFIRMADOS": "facts",
        "TEORÍAS Y VERSIONES": "theories",
        "TEORIAS Y VERSIONES": "theories",
        "CONTROVERSIAS Y DEBATES": "theories",
        "DATOS CLAVE": "facts",
        "FUENTES": "sources",
        "AFIRMACIONES QUE REQUIEREN VERIFICACIÓN": "unverified",
        "AFIRMACIONES QUE REQUIEREN VERIFICACION": "unverified",
    }
    cur = "content"
    buf: list[str] = []

    def flush():
        nonlocal cur, buf
        if cur in ("sources", "facts", "theories", "unverified"):
            pass  # already accumulated
        else:
            if cur and buf:
                existing = sections.get(cur) or ""
                if isinstance(existing, str) and existing:
                    sections[cur] = (existing + "\n" + "\n".join(buf).strip()).strip()
                else:
                    sections[cur] = "\n".join(buf).strip()

    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            flush()
            buf = []
            cur = matched
        else:
            if cur in ("sources", "facts", "theories", "unverified"):
                target = cast(list[str], sections[cur])
                if s.startswith(("-", "•", "*")):
                    target.append(s.lstrip("-•* ").strip())
                elif s:
                    target.append(s)
            else:
                buf.append(line)
    flush()
    return sections


def parse_concept(text: str) -> dict[str, str | list[str]]:
    sections: dict[str, str | list[str]] = {
        "angle": "",
        "thesis": "",
        "key_points": [],
        "emotional_hook": "",
        "what_they_learn": [],
        "what_they_feel": [],
        "risks": [],
    }
    sections_map = {
        "ÁNGULO": "angle",
        "ANGULO": "angle",
        "TESIS": "thesis",
        "PUNTOS CLAVE": "key_points",
        "GANCHO": "emotional_hook",
        "LO QUE EL ESPECTADOR DEBE APRENDER": "what_they_learn",
        "LO QUE EL ESPECTADOR DEBE SENTIR": "what_they_feel",
        "RIESGOS": "risks",
    }
    cur = None
    buf: list[str] = []

    def flush_text():
        if cur and cur not in ("key_points", "what_they_learn", "what_they_feel", "risks"):
            existing = sections.get(cur) or ""
            if isinstance(existing, str):
                if buf:
                    sections[cur] = (existing + "\n" + "\n".join(buf).strip()).strip()
        elif cur in ("key_points", "what_they_learn", "what_they_feel", "risks"):
            pass

    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            flush_text()
            buf = []
            cur = matched
        else:
            if cur in ("key_points", "what_they_learn", "what_they_feel", "risks"):
                target = cast(list[str], sections[cur])
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s) or re.match(r"^[-•*]\s*(.+)", s)
                if m:
                    target.append(m.group(1).strip())
                elif s:
                    target.append(s)
            elif cur:
                buf.append(line)
    flush_text()
    return sections


def parse_script(text: str, script_type: str) -> dict[str, str]:
    """Parsea un guion largo o corto en sus secciones."""
    out: dict[str, str] = {
        "title": "",
        "hook": "",
        "context": "",
        "development": "",
        "revelations": "",
        "conclusion": "",
        "cta": "",
        "body_full": "",
    }
    sections_map = {
        "TITULO": "title",
        "TÍTULO": "title",
        "HOOK": "hook",
        "CONTEXTO": "context",
        "DESARROLLO": "development",
        "REVELACIONES": "revelations",
        "CONCLUSION": "conclusion",
        "CONCLUSIÓN": "conclusion",
        "CTA": "cta",
        "INFORMACIÓN ESENCIAL": "context",
        "INFORMACION ESENCIAL": "context",
        "ESCALADA": "revelations",
        "REMATE": "conclusion",
    }
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            if cur:
                out[cur] = (out.get(cur) or "").strip()
            target_key = cur or matched
            out[target_key] = (out.get(target_key, "") + "\n" + "\n".join(buf).strip()).strip()
            buf = []
            cur = matched
        else:
            buf.append(line)
    if cur:
        out[cur] = (out.get(cur, "") + "\n" + "\n".join(buf).strip()).strip()
    parts = []
    for k in ("hook", "context", "development", "revelations", "conclusion", "cta"):
        if out.get(k):
            parts.append(out[k])
    out["body_full"] = "\n\n".join(parts).strip()
    return out


def parse_scenes_json(text: str) -> list[dict] | None:
    """Intenta extraer un JSON de una respuesta que podría tener prosa alrededor."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except Exception as e:
        # expected: el candidato entre [ y ] no es JSON valido. Caemos
        # al siguiente intento (bloque markdown). El parser es best-effort.
        log.debug("parse_scenes_json: candidato [..] no es JSON valido: %s", e)
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            log.debug("parse_scenes_json: bloque markdown no es JSON valido: %s", e)
            return None
    return None


def parse_scenes_tst(text: str) -> list[dict]:
    """Parsea la salida TST Scene Director en bloques ESCENA N / TEXTO AUDIO / IMAGEN."""
    if not text:
        return []
    scenes: list[dict] = []
    current: dict | None = None
    field = None
    scene_re = re.compile(r"^\s*ESCENA\s+(\d+)\s*[:.]?\s*$", re.IGNORECASE)
    field_re = re.compile(r"^\s*(TEXTO\s+AUDIO|IMAGEN)\s*:\s*(.*)$", re.IGNORECASE)

    def flush():
        if current and current.get("narration_segment") and current.get("image_prompt"):
            scenes.append(current)

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        m_scene = scene_re.match(line)
        if m_scene:
            flush()
            current = {"scene_number": int(m_scene.group(1))}
            field = None
            continue
        if current is None:
            continue
        m_field = field_re.match(line)
        if m_field:
            label = m_field.group(1).upper().replace(" ", "")
            key = "narration_segment" if label == "TEXTOAUDIO" else "image_prompt"
            current[key] = m_field.group(2).strip()
            field = key
            continue
        if field and stripped:
            current[field] = (current.get(field, "") + " " + stripped).strip()
    flush()
    return scenes


def parse_scenes(text: str) -> list[dict] | None:
    """Parsea una respuesta de escenas: intenta primero TST, luego JSON."""
    tst = parse_scenes_tst(text)
    if tst:
        return tst
    j = parse_scenes_json(text)
    if j:
        return j
    return None


def parse_prompt_json(text: str) -> dict | None:
    """Intenta extraer el JSON de un prompt."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            log.debug("parse_prompt_json: bloque markdown no es JSON valido: %s", e)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception as e:
            log.debug("parse_prompt_json: candidato {..} no es JSON valido: %s", e)
            return None
    return None


def _canonical_metadata_dict() -> dict[str, str | list[str]]:
    """Devuelve el dict con todos los campos que la UI/DB espera, vacíos por defecto."""
    return {
        "titles": [],
        "description": "",
        "chapters": [],
        "tags": [],
        "hashtags": [],
        "caption": "",
        "hook": "",
        "cta": "",
        "on_screen_text": [],
    }


def parse_metadata(text: str, platform: str) -> dict[str, str | list[str]]:
    """Dispatcher: enruta a la rama específica por plataforma.

    Plataformas soportadas: ``youtube_long``, ``youtube_short``,
    ``facebook_long``, ``reels_short``. Si la plataforma no se reconoce,
    cae a ``youtube_long`` (la más completa y retrocompatible). Siempre
    devuelve el dict canónico con todos los campos rellenos (los no
    rellenados por el parser específico quedan vacíos).
    """
    parser_name = PLATFORM_PARSERS.get(platform)
    if parser_name is None:
        parser_name = "youtube_long"
    parser = _METADATA_PARSERS_BY_NAME[parser_name]
    parsed = parser(text)
    out = _canonical_metadata_dict()
    out.update({k: v for k, v in parsed.items() if k in out})
    return out


def _parse_youtube_long(text: str) -> dict[str, str | list[str]]:
    partial: dict[str, str | list[str]] = {
        "titles": [],
        "description": "",
        "tags": [],
        "cta": "",
    }
    cur = None
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## TITULOS") or up.startswith("## TÍTULOS"):
            cur = "titles"
        elif up.startswith("## DESCRIPCIÓN") or up.startswith("## DESCRIPCION"):
            cur = "description"
        elif up.startswith("## TAGS"):
            cur = "tags"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("##"):
            cur = None
        elif cur == "titles":
            m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
            if m:
                cast(list[str], partial["titles"]).append(m.group(1).strip())
        elif cur == "tags" and s and not s.startswith("#"):
            cast(list[str], partial["tags"]).extend(
                p for p in (q.strip() for q in re.split(r"[,\s]+", s) if q.strip())
            )
        elif cur in ("description", "cta") and s:
            existing = partial[cur] or ""
            if isinstance(existing, str):
                partial[cur] = f"{existing}\n{s}".strip()
    return partial


def _parse_youtube_short(text: str) -> dict[str, str | list[str]]:
    partial: dict[str, str | list[str]] = {
        "titles": [],
        "description": "",
        "tags": [],
        "hashtags": [],
        "cta": "",
    }
    cur = None
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## TITULOS") or up.startswith("## TÍTULOS"):
            cur = "titles"
        elif up.startswith("## DESCRIPCIÓN") or up.startswith("## DESCRIPCION"):
            cur = "description"
        elif up.startswith("## TAGS"):
            cur = "tags"
        elif up.startswith("## HASHTAGS"):
            cur = "hashtags"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("##"):
            cur = None
        elif cur == "titles":
            m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
            if m:
                cast(list[str], partial["titles"]).append(m.group(1).strip())
        elif cur == "tags" and s and not s.startswith("#"):
            cast(list[str], partial["tags"]).extend(
                p for p in (q.strip() for q in re.split(r"[,\s]+", s) if q.strip())
            )
        elif cur == "hashtags":
            cast(list[str], partial["hashtags"]).extend(re.findall(r"#\w+", s))
        elif cur in ("description", "cta") and s:
            existing = partial[cur] or ""
            if isinstance(existing, str):
                partial[cur] = f"{existing}\n{s}".strip()
    return partial


def _parse_facebook_long(text: str) -> dict[str, str | list[str]]:
    """Solo descripción + hashtags + CTA; Facebook no usa títulos."""
    partial: dict[str, str | list[str]] = {"description": "", "hashtags": [], "cta": ""}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## DESCRIPCION") or up.startswith("## DESCRIPCIÓN"):
            cur = "description"
        elif up.startswith("## HASHTAGS"):
            cur = "hashtags"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("##"):
            cur = None
        elif cur in ("description", "cta") and s:
            existing = partial[cur] or ""
            if isinstance(existing, str):
                partial[cur] = f"{existing}\n{s}".strip()
        elif cur == "hashtags":
            cast(list[str], partial["hashtags"]).extend(re.findall(r"#\w+", s))
    return partial


def _parse_reels_short(text: str) -> dict[str, str | list[str]]:
    """Reels: descripción corta + hashtags + CTA, sin títulos ni tags."""
    partial: dict[str, str | list[str]] = {"description": "", "hashtags": [], "cta": ""}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## DESCRIPCION") or up.startswith("## DESCRIPCIÓN"):
            cur = "description"
        elif up.startswith("## HASHTAGS"):
            cur = "hashtags"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("##"):
            cur = None
        elif cur in ("description", "cta") and s:
            existing = partial[cur] or ""
            if isinstance(existing, str):
                partial[cur] = f"{existing}\n{s}".strip()
        elif cur == "hashtags":
            cast(list[str], partial["hashtags"]).extend(re.findall(r"#\w+", s))
    return partial


PLATFORM_PARSERS = {
    "youtube_long": "youtube_long",
    "youtube_short": "youtube_short",
    "facebook_long": "facebook_long",
    "reels_short": "reels_short",
}


_METADATA_PARSERS_BY_NAME = {
    "youtube_long": _parse_youtube_long,
    "youtube_short": _parse_youtube_short,
    "facebook_long": _parse_facebook_long,
    "reels_short": _parse_reels_short,
}


def parse_thumbnail(text: str, script_type: str) -> dict[str, str]:
    """Extrae el bloque `## MINIATURA` de la respuesta del LLM."""
    out = {"prompt": ""}
    if not text:
        return out
    cur = None
    buf: list[str] = []

    def flush():
        nonlocal out, cur, buf
        if cur == "miniatura" and buf:
            chunk = "\n".join(buf).strip()
            existing = out["prompt"]
            out["prompt"] = (existing + "\n" + chunk).strip() if existing else chunk
        buf = []

    for raw in text.splitlines():
        line = raw.rstrip()
        up = re.sub(r"\s+", " ", line.strip().upper())
        if up.startswith("## "):
            flush()
            cur = "miniatura" if up.startswith("## MINIATURA") else None
            continue
        if cur == "miniatura" and line.strip():
            buf.append(line.strip())
    flush()
    return out
