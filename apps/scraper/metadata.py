"""Clasificación de documentos: tipo, año y programa a partir de URL y título."""

import re

_YEAR = re.compile(r"\b(19|20)\d{2}\b")

DOC_TYPES = (
    ("reglamento", ("reglamento", "estatuto")),
    ("acuerdo", ("acuerdo",)),
    ("resolucion", ("resolucion", "resolución")),
    ("plan_estudios", ("plan de estudios", "pensum", "malla")),
    ("pep", ("proyecto educativo", "pep")),
    ("acreditacion", ("acreditacion", "autoevaluacion", "mejoramiento")),
    ("trabajo_grado", ("trabajo de grado", "tesis", "monografia")),
    ("pasantia", ("pasantia", "practica")),
    ("monitoria", ("monitoria",)),
    ("matricula", ("matricula", "derechos academicos")),
    ("admision", ("admision", "inscripcion", "aspirante")),
    ("posgrado", ("posgrado", "maestria", "doctorado", "especializacion")),
    ("pregrado", ("pregrado",)),
    ("bienestar", ("bienestar", "convivencia")),
    ("disciplinario", ("disciplinario", "disciplina")),
    ("grado", ("grado", "diploma", "acta de grado")),
    ("egresado", ("egresado",)),
    ("docente", ("docente", "profesor", "carrera profesoral")),
    ("calendario", ("calendario", "horario")),
    ("programa", ("programa", "curricular")),
    ("informe", ("informe", "acta", "circular", "oficio", "comunicado")),
)

PROGRAMS = (
    ("sistemas", ("sistemas", "computacion")),
    ("industrial", ("industrial",)),
)


def classify(url: str, title: str = "") -> dict:
    hay = f"{url} {title}".lower()
    doc_type = "documento"
    for name, keys in DOC_TYPES:
        if any(k in hay for k in keys):
            doc_type = name
            break

    program = None
    for name, keys in PROGRAMS:
        if any(k in hay for k in keys):
            program = name
            break

    years = _YEAR.findall(hay)
    year = int(years[0]) if years else None

    return {"doc_type": doc_type, "program": program, "year": year}
