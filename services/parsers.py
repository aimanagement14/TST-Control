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


def parse_metadata(text: str, platform: str) -> dict[str, str | list[str]]:
    out: dict[str, str | list[str]] = {
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
    cur = None
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## TITULOS") or up.startswith("## TÍTULOS"):
            cur = "titles"
        elif up.startswith("## DESCRIPCIÓN") or up.startswith("## DESCRIPCION"):
            cur = "description"
        elif up.startswith("## CAPÍTULOS") or up.startswith("## CAPITULOS"):
            cur = "chapters"
        elif up.startswith("## TAGS"):
            cur = "tags"
        elif up.startswith("## HASHTAGS"):
            cur = "hashtags"
        elif up.startswith("## CAPTION"):
            cur = "caption"
        elif up.startswith("## HOOK"):
            cur = "hook"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("## TEXTO EN PANTALLA"):
            cur = "on_screen_text"
        elif up.startswith("##") and cur:
            cur = None
        else:
            if cur == "titles":
                titles = cast(list[str], out["titles"])
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
                if m:
                    titles.append(m.group(1).strip())
            elif cur == "tags":
                tags = cast(list[str], out["tags"])
                if s and not s.startswith("#"):
                    parts = [p.strip() for p in re.split(r"[,\s]+", s) if p.strip()]
                    tags.extend(parts)
            elif cur == "hashtags":
                hashtags = cast(list[str], out["hashtags"])
                for h in re.findall(r"#\w+", s):
                    hashtags.append(h)
            elif cur == "chapters":
                chapters = cast(list[str], out["chapters"])
                if s:
                    chapters.append(s)
            elif cur == "on_screen_text":
                on_screen = cast(list[str], out["on_screen_text"])
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
                if m:
                    on_screen.append(m.group(1).strip())
            elif cur in ("description", "caption", "hook", "cta"):
                if s:
                    existing = out[cur] or ""
                    out[cur] = (existing + "\n" + s).strip() if isinstance(existing, str) else s
    return out


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
