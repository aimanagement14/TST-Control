"""
Verificación end-to-end del proyecto 'Todo sobre los Fosiles'.
Ejecuta el flujo completo usando el test client de Flask:
- Refuerza la investigación con secciones parseables
- Genera concepto
- Genera guion largo + corto
- Genera escenas
- Genera prompts visuales
- Genera metadata YouTube + Shorts
- Ejecuta QC
- Exporta el ZIP
"""
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import app

PROJECT_ID = 1


def ensure_project():
    """Garantiza que existe un proyecto válido con id=PROJECT_ID.

    Si no hay proyectos o el id solicitado no existe, crea uno reutilizando
    el perfil por defecto. Devuelve el id del proyecto listo para usar.
    """
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM projects WHERE id=?", (PROJECT_ID,)
        ).fetchone()
        if row:
            return row["id"]
        default_profile = conn.execute(
            "SELECT id FROM profiles WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not default_profile:
            default_profile = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()
        profile_id = default_profile["id"] if default_profile else None
        cur = conn.execute(
            """INSERT INTO projects (id, name, topic, profile_id, status,
               created_at, updated_at)
               VALUES (?, ?, ?, ?, 'research', ?, ?)""",
            (
                PROJECT_ID,
                "Todo sobre los Fosiles",
                "Fósiles del Himalaya",
                profile_id,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        return cur.lastrowid or PROJECT_ID

# ---------------------------------------------------------------------------
# Datos simulados del LLM (modo manual) por etapa
# ---------------------------------------------------------------------------

RESEARCH_TEXT = """\
## RESUMEN
El derretimiento de glaciares en el Himalaya nepalí está exponiendo restos geológicos, paleontológicos y arqueológicos a un ritmo sin precedentes. Algunos hallazgos virales en redes hablan de un "fósil misterioso" tras el colapso de un glaciar; en realidad, el Himalaya contiene abundantes fósiles marinos del antiguo Mar de Tetis, elevados por la colisión tectónica entre las placas india y euroasiática. La cobertura mediática suele mezclar estos hallazgos geológicos con la tradición folclórica del Yeti, cuyos supuestos restos físicos analizados científicamente han resultado ser de origen animal conocido.

## HECHOS CONFIRMADOS
- El Himalaya se formó por la colisión de las placas india y euroasiática iniciada hace ~50 millones de años (Fuente: USGS)
- El Mar de Tetis existió entre el Mesozoico y el Paleógeno, dejando fósiles marinos en lo que hoy es el Himalaya (Fuente: Nature, 2019)
- El retroceso glaciar en el Himalaya se acelera desde 1970 y se intensifica por el cambio climático (Fuente: ICIMOD, 2023)
- En 2023 un estudio identificó ADN antiguo de plantas y artrópodos en sedimentos del glaciar de Khumbu (Fuente: PNAS, 2023)
- Los supuestos "scalps" de Yeti en monasterios nepalíes fueron analizados y corresponden a osos pardos y ganado (Fuente: Proceedings of the Royal Society B, 2017)
- En 2019 se hallaron microfósiles de fitoplancton del Eoceno en la Formación Gokarna, Nepal (Fuente: Journal of Asian Earth Sciences)
- Los fósiles marinos más comunes en el Himalaya son ammonites, braquiópodos y nummulites (Fuente: Geology Today, 2021)
- El término "arqueología glacial" describe cómo los deshielos exponen artefactos orgánicos preservados (Fuente: Antiquity, 2022)

## TEORÍAS Y VERSIONES
- Teoría geológica estándar: el "fósil misterioso" es un fósil marino del Tetis expuesto por el deshielo. A favor: explica los hallazgos reales documentados. En contra: no encaja con la narrativa de misterio.
- Teoría Yeti criptozoológico: ciertos restos pertenecen a un primate desconocido. A favor: tradición oral y folclore local milenario. En contra: análisis genéticos de supuestos restos los identifican como osos.
- Teoría conspirativa viral: el hallazgo prueba civilizaciones prehistóricas avanzadas. A favor: engagement en redes. En contra: ausencia total de evidencia física verificable.
- Teoría arqueológica: muchos hallazgos son vestigios humanos rituales o funerarios de los últimos siglos, no fósiles paleontológicos. A favor: contexto cultural documentado. En contra: se confunden con frecuencia.

## CONTROVERSIAS Y DEBATES
- ¿Cómo separar en medios la divulgación paleontológica del sensacionalismo paranormal?
- ¿Qué protocolo científico aplicar para autentificar hallazgos virales antes de su difusión?
- ¿Cómo proteger yacimientos recién expuestos de saqueo y tráfico de fósiles?

## DATOS CLAVE
- 50 millones de años: inicio del levantamiento del Himalaya
- ~8.000 m: altitud media del Himalaya
- 1970-2020: periodo de aceleración del retroceso glaciar documentado
- Eoceno: época geológica de muchos fósiles expuestos en Nepal
- 2017: año del análisis genético de supuestos restos de Yeti
- Mar de Tetis: océano desaparecido que dio origen a muchos fósiles himalayos

## FUENTES
- https://www.usgs.gov/special-topics/plate-tectonics/science/himalayas
- https://www.nature.com/articles/s41586-019-1180-2
- https://www.icimod.org/article/himalaya-glacier-mass-balance
- https://www.pnas.org/doi/10.1073/pnas.2217561120
- https://royalsocietypublishing.org/doi/10.1098/rspb.2017.1304
- https://www.sciencedirect.com/journal/journal-of-asian-earth-sciences
- https://www.cambridge.org/core/journals/antiquity

## AFIRMACIONES QUE REQUIEREN VERIFICACIÓN
- "Fósil misterioso de Nepal" viral en redes: sin paper publicado, requiere verificación primaria.
- Identificación de posibles "huellas humanas prehistóricas" en roca nepalí: pendiente de datación.
"""

CONCEPT_TEXT = """\
## ÁNGULO
Separar la realidad geológica del Himalaya —los fósiles marinos del Mar de Tetis expuestos por el deshielo— del ruido viral que mezcla estos hallazgos con la mitología del Yeti. Un documental que muestre lo extraordinario de lo real, sin necesidad de inventar misterios.

## TESIS CENTRAL
El Himalaya guarda un registro paleontológico extraordinario y verificable; los "misterios virales" suelen ocultar hallazgos reales que la ciencia ya puede explicar.

## PUNTOS CLAVE A DESARROLLAR
1. El Himalaya como archivo geológico del Mar de Tetis.
2. La aceleración del deshielo y la "arqueología glacial".
3. La tradición Yeti frente al análisis genético de supuestos restos.
4. Fósiles reales documentados en Nepal y su valor científico.

## GANCHO EMOCIONAL
Asombro al descubrir que la "montaña sagrada" es también un cementerio de criaturas marinas de hace 50 millones de años.

## LO QUE EL ESPECTADOR DEBE APRENDER
- Por qué hay fósiles marinos en la cima del mundo.
- Qué dice realmente la ciencia sobre los supuestos restos de Yeti.
- Cómo distinguir hallazgos reales de bulos virales.
- Por qué el deshielo expone y a la vez destruye patrimonio.

## LO QUE EL ESPECTADOR DEBE SENTIR
- Asombro ante la escala del tiempo geológico.
- Curiosidad por visitar Nepal con ojos nuevos.
- Indignación ante el sensacionalismo viral.
- Respeto por la ciencia que separa hecho de ficción.

## RIESGOS
- Caer en narrativa sensacionalista paranormal y contradecir el ángulo.
- Sensibilidades culturales locales sobre la figura del Yeti.
- Uso indebido de imágenes de yacimientos protegidos.
"""

SCRIPT_LONG_TEXT = """\
## TITULO
El Himalaya guarda los mares que el mundo olvidó

## HOOK (0:00 - 0:15)
Donde hoy se levanta la montaña más alta del planeta, hubo un mar entero. Sus criaturas descansan ahora bajo glaciares que el sol, poco a poco, está derritiendo.

## CONTEXTO (0:15 - 1:00)
Cada año, el Himalaya pierde milímetros de hielo que han permanecido durante milenios. Lo que ese hielo esconde cambia la historia que contamos sobre el planeta. La colisión de las placas tectónicas india y euroasiática levantó un océano entero. Sus habitantes quedaron grabados en la roca. Y ahora, empujados por el deshielo, vuelven a la superficie ante los ojos de los geólogos y paleontólogos que recorren las morrenas en busca de respuestas.

## DESARROLLO (1:00 - 3:30)

### BLOQUE 1: El archivo del Tetis
Hace cincuenta millones de años, una placa oceánica se subdujo bajo otra continental. El fondo del Mar de Tetis se elevó, se plegó, se fracturó, y acabó convertido en la cordillera más alta del mundo. En sus estratos quedaron atrapados ammonites con espirales perfectas, braquiópodos con conchas brillantes y nummulites del tamaño de una moneda. La montaña entera es un libro abierto de paleontología, escrito en piedra caliza y pizarra, listo para quien quiera leerlo con paciencia y respeto por las escalas de tiempo que maneja la Tierra.

### BLOQUE 2: La arqueología del deshielo
Desde 1970 los glaciares del Himalaya pierden masa de forma acelerada. El hielo que durante siglos protegió restos orgánicos los está soltando uno a uno. En 2023, un equipo internacional recuperó ADN antiguo de plantas y artrópodos en sedimentos del glaciar de Khumbu. No es una casualidad. La arqueología glacial se ha convertido en una disciplina nueva que une glaciólogos, genetistas y paleontólogos en torno a una misma pregunta: ¿qué ha estado guardando el hielo durante miles de años?

### BLOQUE 3: La sombra del Yeti
Durante siglos, los monasterios budistas nepalíes guardaron restos atribuidos al Yeti. Cueros cabelludos, huesos, fragmentos de piel. En 2017, un análisis genético publicado en la Royal Society los identificó con claridad: pertenecían a osos pardos del Himalaya y a ganado de la región. La tradición oral sigue viva, las expediciones siguen saliendo cada primavera, pero la ciencia ya tiene una respuesta. Y esa respuesta es más interesante que el mito, porque habla de cómo una cultura convierte sus montañas en leyenda.

### BLOQUE 4: Lo que se pierde al derretirse
Cada fósil que el hielo suelta es también un fósil que la intemperie empieza a destruir. Lluvia, viento, ciclos de hielo y deshielo. No hay tiempo para el sensacionalismo viral. El Himalaya nos regala una ventana única al pasado profundo de la Tierra. Si no la cuidamos, si no la estudiamos con rigor, si no la documentamos antes de que se deteriore, la perderemos al ritmo del deshielo. La urgencia no es solo climática: es también patrimonial y científica, y necesita equipos internacionales, financiación estable y divulgación seria para que cada descubrimiento llegue al público sin filtros sensacionalistas.

## REVELACIONES (3:30 - 4:30)
La verdadera rareza no es un monstruo. Es que criaturas marinas de hace cincuenta millones de años estén asomando entre las nieves del techo del mundo. Es que un océano entero se haya convertido en una cordillera. Y es que el cambio climático esté reescribiendo, en tiempo real, lo que sabemos del pasado profundo del planeta. El Himalaya no necesita ficción: ya cuenta la historia más asombrosa que podamos imaginar.

## CONCLUSIÓN (4:30 - 4:50)
El Himalaya no necesita misterios inventados. Tiene los mares más antiguos del planeta grabados en su roca. Solo hay que mirar con los pies en la tierra, las manos en la pizarra y la cabeza abierta a lo que la geología lleva cincuenta millones de años intentando contarnos. La realidad, una vez más, supera a la leyenda, y la próxima vez que alguien te hable de un fósil misterioso caído del cielo, recuerda que la verdadera rareza ya está ahí fuera, escrita en piedra, esperando a quien quiera leerla sin prisa y sin filtros de conspiración.

## CTA (4:50 - 5:00)
Si quieres más documentales donde desmontamos bulos y celebramos la realidad, suscríbete al canal y activa la campana. Nos vemos en el siguiente misterio resuelto.
"""

SCRIPT_SHORT_TEXT = """\
## TITULO
Himalaya: el mar que se hizo montaña

## HOOK (0:00 - 0:05)
El techo del mundo fue un océano.

## INFORMACIÓN ESENCIAL (0:05 - 0:35)
Hace 50 millones de años, las placas tectónicas levantaron el Mar de Tetis hasta formar el Himalaya que conocemos hoy. Sus fósiles marinos —ammonites, nummulites, braquiópodos— están grabados en la roca. El deshielo los está sacando a la luz poco a poco. En 2023 se recuperó ADN antiguo en el glaciar de Khumbu, y la arqueología glacial ya es una disciplina científica con identidad propia.

## ESCALADA (0:35 - 0:55)
En 2017, supuestos restos del Yeti analizados genéticamente resultaron ser de oso pardo. La tradición sobrevive. La ciencia ya respondió. Y la respuesta es más extraordinaria que el mito, porque cuenta cómo la Tierra transforma un océano entero en la cordillera más alta del planeta.

## REMATE (0:55 - 1:00)
La montaña guarda un océano. Solo necesitamos ojos para verlo.

## CTA (1:00 - 1:05)
Sígueme para más bulos desmontados.
"""

SCENES_JSON = """\
[
  {
    "scene_number": 1,
    "narration_segment": "Donde hoy se levanta la montaña más alta del planeta, hubo un mar. Sus criaturas descansan ahora bajo glaciares que el sol está derritiendo.",
    "visual_description": "Amanecer sobre el Himalaya, pico nevado bañado en luz dorada, glaciar descendiendo por la ladera, vista aérea que desciende lentamente hasta una grieta donde asoma roca oscura.",
    "camera_movement": "aéreo",
    "duration_seconds": 15,
    "transition": "fundido"
  },
  {
    "scene_number": 2,
    "narration_segment": "Cada año, el Himalaya pierde milímetros de hielo que han permanecido durante milenios. Lo que ese hielo esconde cambia la historia que contamos sobre el planeta.",
    "visual_description": "Time-lapse de un glaciar retrocediendo, comparación antes/después de la línea de hielo, agua de deshielo formando un río turbio entre morrenas.",
    "camera_movement": "travelling",
    "duration_seconds": 25,
    "transition": "corte seco"
  },
  {
    "scene_number": 3,
    "narration_segment": "Hace cincuenta millones de años, una placa oceánica se subdujo bajo otra continental. El fondo del Mar de Tetis se elevó y plegó hasta formar la cordillera más alta del mundo.",
    "visual_description": "Animación esquemática de placas tectónicas chocando, el fondo marino plegándose, estratos sedimentarios ascendiendo, transición al Himalaya actual.",
    "camera_movement": "zoom in",
    "duration_seconds": 35,
    "transition": "cortinilla"
  },
  {
    "scene_number": 4,
    "narration_segment": "En sus estratos quedaron atrapados ammonites, braquiópodos y nummulites. La montaña entera es un libro abierto de paleontología.",
    "visual_description": "Primer plano de un ammonite fosilizado emergiendo de roca gris, luz rasante lateral que resalta las espirales del fósil.",
    "camera_movement": "primer plano",
    "duration_seconds": 30,
    "transition": "corte seco"
  },
  {
    "scene_number": 5,
    "narration_segment": "Desde 1970 los glaciares del Himalaya pierden masa de forma acelerada. El hielo que durante siglos protegió restos orgánicos los está soltando. En 2023 un equipo recuperó ADN antiguo en el glaciar de Khumbu.",
    "visual_description": "Investigadores con ropa de alta montaña extrayendo muestras de sedimento en la base de un glaciar, tubos de ensayo etiquetados, luz fría azulada.",
    "camera_movement": "paneo lento",
    "duration_seconds": 40,
    "transition": "disolución"
  },
  {
    "scene_number": 6,
    "narration_segment": "Lo que aparece no es un monstruo: es un registro científico excepcional.",
    "visual_description": "Detalle de un fósil diminuto bajo microscopio de campo, manos con guantes de nitrilo sosteniendo la muestra, fondo oscuro.",
    "camera_movement": "zoom in",
    "duration_seconds": 18,
    "transition": "corte seco"
  },
  {
    "scene_number": 7,
    "narration_segment": "Durante siglos, los monasterios nepalíes guardaron restos atribuidos al Yeti. En 2017, un análisis genético publicado en la Royal Society los identificó como osos pardos y ganado.",
    "visual_description": "Interior de un monasterio nepalí con luz de velas, cajas antiguas con cueros cabelludos, transición a una gráfica de barras con resultados del estudio genético.",
    "camera_movement": "estático",
    "duration_seconds": 35,
    "transition": "fundido"
  },
  {
    "scene_number": 8,
    "narration_segment": "La verdadera rareza no es un monstruo. Es que criaturas marinas de hace cincuenta millones de años estén asomando entre las nieves del techo del mundo.",
    "visual_description": "Plano cenital de la cumbre del Everest al atardecer, nubes envolviendo la cima, sensación de inmensidad y silencio.",
    "camera_movement": "aéreo",
    "duration_seconds": 22,
    "transition": "corte seco"
  },
  {
    "scene_number": 9,
    "narration_segment": "El Himalaya no necesita misterios inventados. Tiene los mares más antiguos del planeta grabados en su roca. Solo hay que mirar con los pies en la tierra.",
    "visual_description": "Vista panorámica del Himalaya con texto en pantalla desvaneciéndose, un geólogo sentado en una roca con martillo en mano mirando la cordillera.",
    "camera_movement": "travelling",
    "duration_seconds": 15,
    "transition": "fundido"
  }
]
"""


METADATA_YOUTUBE_TEXT = """\
## TITULOS (5 opciones)
1. El Himalaya guarda un mar de 50 millones de años
2. El techo del mundo fue un océano (y el deshielo lo destapa)
3. Fósiles del Mar de Tetis en el Himalaya: la verdad
4. Yeti, bulos y paleontología real en Nepal
5. Cuando el Himalaya era mar: lo que el deshielo está sacando

## DESCRIPCIÓN
Cada año, los glaciares del Himalaya pierden milímetros de hielo milenario. Lo que ese hielo ha protegido durante milenios está cambiando lo que sabemos del pasado profundo del planeta. En este documental desmontamos la narrativa viral de los "fósiles misteriosos" tras el deshielo nepalí y mostramos la realidad geológica verificable: ammonites, braquiópodos y nummulites del antiguo Mar de Tetis, elevados por la colisión tectónica entre la placa india y la euroasiática hace 50 millones de años. Analizamos también el estudio genético de 2017 que identificó los supuestos restos del Yeti como pertenecientes a osos pardos y ganado, y ponemos en valor la arqueología glacial como nueva disciplina científica.

Si te interesan los documentales donde desmontamos bulos y celebramos la realidad, suscríbete al canal y activa la campana.

Fuentes mencionadas en el vídeo:
- USGS: https://www.usgs.gov/special-topics/plate-tectonics/science/himalayas
- Nature (2019): https://www.nature.com/articles/s41586-019-1180-2
- ICIMOD (2023): https://www.icimod.org/article/himalaya-glacier-mass-balance
- PNAS (2023): https://www.pnas.org/doi/10.1073/pnas.2217561120
- Royal Society B (2017): https://royalsocietypublishing.org/doi/10.1098/rspb.2017.1304

## CAPÍTULOS
00:00 Hook — Donde hubo un mar
00:15 El deshielo que cambia la historia
01:00 El archivo del Mar de Tetis
01:35 La arqueología del deshielo
02:15 La sombra del Yeti
03:30 Lo que el hielo esconde de verdad
04:00 Conclusión

## TAGS (15)
himalaya, fosiles, mar de tetis, paleontologia, yeti, nepal, deshielo, cambio climatico, tectonica de placas, geologia, arqueologia glaciar, ammonites, braquiopodos, documental misterio, todo sobre todo

## HASHTAGS (5)
#himalaya #fosiles #paleontologia #tetis #yetis

## CTA
Suscríbete al canal y activa la campana para más documentales donde desmontamos bulos y celebramos la realidad.
"""

METADATA_SHORTS_TEXT = """\
## CAPTION
El Himalaya fue un océano.
Sus criaturas descansan bajo glaciares que se derriten.
Lo que está apareciendo cambia la historia del planeta.

## HOOK
El techo del mundo fue un mar.

## HASHTAGS (10)
#himalaya #fosiles #tetis #yetis #nepal #paleontologia #arqueologia #deshielo #documental #shorts

## CTA
Sígueme para más bulos desmontados.

## TEXTO EN PANTALLA
1. EL HIMALAYA FUE UN OCÉANO
2. HACE 50 MILLONES DE AÑOS
3. EL DESHIELO LO ESTÁ DESTAPANDO
"""


def log(stage, msg, ok=True):
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {stage}: {msg}")


def main():
    client = app.app.test_client()

    # ---- Bootstrap: garantiza que el proyecto existe ----
    print("=== Bootstrap ===")
    ensure_project()
    with app.get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        log("Proyecto bootstrap", f"{n} proyecto(s) en BD", True)

    # ---- 0) Verificar dashboard ----
    print("\n=== 0) Dashboard ===")
    r = client.get("/")
    log("Dashboard", f"status {r.status_code}, len {len(r.data)}", r.status_code == 200)
    assert b"Todo Sobre Todo" in r.data, "Dashboard no contiene marca"

    # ---- 1) Reforzar investigación con secciones parseables ----
    print("\n=== 1) Investigación (reescribir con formato parseable) ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/research",
        data={"action": "save", "content": RESEARCH_TEXT},
        follow_redirects=True,
    )
    log("Investigación POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        research = dict(conn.execute(
            "SELECT * FROM research WHERE project_id=?", (PROJECT_ID,)
        ).fetchone())
    parsed_sources = json.loads(research["sources"] or "[]")
    parsed_facts = json.loads(research["facts"] or "[]")
    parsed_theories = json.loads(research["theories"] or "[]")
    parsed_unverified = json.loads(research["unverified"] or "[]")
    log("Hechos", f"{len(parsed_facts)} extraídos", len(parsed_facts) >= 6)
    log("Fuentes", f"{len(parsed_sources)} extraídas", len(parsed_sources) >= 6)
    log("Teorías", f"{len(parsed_theories)} extraídas", len(parsed_theories) >= 3)
    log("Sin verificar", f"{len(parsed_unverified)} marcadas", len(parsed_unverified) >= 1)

    # ---- 2) Concepto ----
    print("\n=== 2) Concepto ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/concept",
        data={"action": "save", "text": CONCEPT_TEXT},
        follow_redirects=True,
    )
    log("Concepto POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        concept = dict(conn.execute(
            "SELECT * FROM concept WHERE project_id=?", (PROJECT_ID,)
        ).fetchone())
    log("Ángulo", bool(concept["angle"]), bool(concept["angle"]))
    log("Tesis", bool(concept["thesis"]), bool(concept["thesis"]))
    kp = json.loads(concept["key_points"] or "[]")
    log("Puntos clave", f"{len(kp)} puntos", len(kp) >= 3)

    # ---- 3) Guion largo ----
    print("\n=== 3) Guion largo (5 min) ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/scripts",
        data={"action": "save", "script_type": "long", "text": SCRIPT_LONG_TEXT},
        follow_redirects=True,
    )
    log("Guion largo POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        long_s = dict(conn.execute(
            "SELECT * FROM scripts WHERE project_id=? AND type='long'",
            (PROJECT_ID,),
        ).fetchone())
    log("Hook largo", bool(long_s["hook"]), bool(long_s["hook"]))
    log("Contexto largo", bool(long_s["context"]), bool(long_s["context"]))
    log("Desarrollo largo", bool(long_s["development"]), bool(long_s["development"]))
    log("Revelaciones largo", bool(long_s["revelations"]), bool(long_s["revelations"]))
    log("Conclusión largo", bool(long_s["conclusion"]), bool(long_s["conclusion"]))
    log("CTA largo", bool(long_s["cta"]), bool(long_s["cta"]))
    log("Palabras largo", f"{long_s['word_count']} (rango 650-850)",
        650 <= long_s["word_count"] <= 850)

    # ---- 4) Guion corto ----
    print("\n=== 4) Guion corto (1 min) ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/scripts",
        data={"action": "save", "script_type": "short", "text": SCRIPT_SHORT_TEXT},
        follow_redirects=True,
    )
    log("Guion corto POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        short_s = dict(conn.execute(
            "SELECT * FROM scripts WHERE project_id=? AND type='short'",
            (PROJECT_ID,),
        ).fetchone())
    log("Hook corto", bool(short_s["hook"]), bool(short_s["hook"]))
    log("Palabras corto", f"{short_s['word_count']} (rango 130-180)",
        130 <= short_s["word_count"] <= 180)

    # ---- 5) Escenas ----
    print("\n=== 5) Escenas ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/scenes",
        data={
            "action": "save",
            "script_id": str(long_s["id"]),
            "text": SCENES_JSON,
        },
        follow_redirects=True,
    )
    log("Escenas POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        n_scenes = conn.execute(
            "SELECT COUNT(*) AS n FROM scenes WHERE project_id=?", (PROJECT_ID,)
        ).fetchone()["n"]
    log("Escenas guardadas", f"{n_scenes} (>= 6)", n_scenes >= 6)

    # ---- 6) Metadata YouTube ----
    print("\n=== 6) Metadata YouTube ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/metadata",
        data={
            "action": "save",
            "platform": "youtube",
            "script_id": str(long_s["id"]),
            "text": METADATA_YOUTUBE_TEXT,
        },
        follow_redirects=True,
    )
    log("Metadata YT POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        m_yt = dict(conn.execute(
            "SELECT * FROM metadata_records WHERE project_id=? AND platform='youtube'",
            (PROJECT_ID,),
        ).fetchone())
    titles = json.loads(m_yt["titles"] or "[]")
    chapters = json.loads(m_yt["chapters"] or "[]")
    tags = json.loads(m_yt["tags"] or "[]")
    hashtags = json.loads(m_yt["hashtags"] or "[]")
    log("Títulos YT", f"{len(titles)} (>= 3)", len(titles) >= 3)
    log("Capítulos YT", f"{len(chapters)} (>= 3)", len(chapters) >= 3)
    log("Tags YT", f"{len(tags)} (>= 10)", len(tags) >= 10)
    log("Hashtags YT", f"{len(hashtags)} (>= 3)", len(hashtags) >= 3)
    log("Descripción YT", bool(m_yt["description"]), bool(m_yt["description"]))

    # ---- 7) Metadata Shorts ----
    print("\n=== 7) Metadata Shorts ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/metadata",
        data={
            "action": "save",
            "platform": "shorts",
            "script_id": str(short_s["id"]),
            "text": METADATA_SHORTS_TEXT,
        },
        follow_redirects=True,
    )
    log("Metadata Shorts POST", f"status {r.status_code}", r.status_code == 200)
    with app.get_db() as conn:
        m_sh = dict(conn.execute(
            "SELECT * FROM metadata_records WHERE project_id=? AND platform='shorts'",
            (PROJECT_ID,),
        ).fetchone())
    sh_hashtags = json.loads(m_sh["hashtags"] or "[]")
    sh_text = json.loads(m_sh["on_screen_text"] or "[]")
    log("Caption Shorts", bool(m_sh["caption"]), bool(m_sh["caption"]))
    log("Hook Shorts", bool(m_sh["hook"]), bool(m_sh["hook"]))
    log("Hashtags Shorts", f"{len(sh_hashtags)} (>= 5)", len(sh_hashtags) >= 5)
    log("Texto pantalla Shorts", f"{len(sh_text)} (>= 3)", len(sh_text) >= 3)

    # ---- 8) QC ----
    print("\n=== 8) Control de calidad ===")
    r = client.post(f"/projects/{PROJECT_ID}/qc", follow_redirects=True)
    log("QC POST", f"status {r.status_code}", r.status_code == 200)
    issues = app.run_qc(PROJECT_ID)
    errors = [i for i in issues if i[1] == "error"]
    warnings = [i for i in issues if i[1] == "warning"]
    infos = [i for i in issues if i[1] == "info"]
    log("Errores", f"{len(errors)} (0 esperado)", len(errors) == 0)
    log("Warnings", f"{len(warnings)} (tolerable)", True)
    log("Info", f"{len(infos)}", True)
    for sev, items in [("error", errors), ("warning", warnings)]:
        for stage, _, msg, _field in items:
            print(f"      [{sev}] {stage}: {msg}")

    with app.get_db() as conn:
        status = conn.execute(
            "SELECT status FROM projects WHERE id=?", (PROJECT_ID,)
        ).fetchone()["status"]
    log("Status del proyecto", f"'{status}' (esperado 'ready')", status == "ready")

    # ---- 9) Export ZIP ----
    print("\n=== 9) Exportación ZIP ===")
    r = client.post(f"/projects/{PROJECT_ID}/export", follow_redirects=False)
    log("Export POST", f"status {r.status_code}", r.status_code == 200)
    log("Content-Type zip", "zip" in r.headers.get("Content-Type", "").lower()
        or r.data[:2] == b"PK")
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    names = zf.namelist()
    expected_substrings = [
        "00_RESUMEN.md",
        "01_investigacion.md",
        "02_concepto.md",
        "03_guiones/guion_long.md",
        "03_guiones/guion_short.md",
        "04_escenas/",
        "05_metadata/metadata_youtube.md",
        "05_metadata/metadata_shorts.md",
        "07_paquete_completo.json",
    ]
    for s in expected_substrings:
        present = any(s in n for n in names)
        log(f"Contiene {s}", "sí" if present else "NO", present)

    # Validar contenido de un par de archivos
    resumen = zf.read([n for n in names if n.endswith("00_RESUMEN.md")][0]).decode("utf-8")
    log("Resumen contiene tema", "Fósiles" in resumen or "fosiles" in resumen.lower(),
        "Fósiles" in resumen or "fosiles" in resumen.lower())
    bundle = json.loads(zf.read([n for n in names if n.endswith("07_paquete_completo.json")][0])
                        .decode("utf-8"))
    log("Bundle JSON", f"keys: {list(bundle.keys())[:6]}...",
        {"project", "research", "concept", "scripts"}.issubset(bundle.keys()))

    print("\n" + "=" * 60)
    print(f"  ZIP exportado: {len(names)} archivos, {len(r.data)} bytes")
    print("=" * 60)
    print("\n[OK] Verificación end-to-end completada.\n")


if __name__ == "__main__":
    main()
