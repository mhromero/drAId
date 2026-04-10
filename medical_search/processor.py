from __future__ import annotations

from dataclasses import dataclass
import re

import spacy

import scispacy  # Registers scispaCy factories such as abbreviation_detector.
from scispacy.abbreviation import AbbreviationDetector


SYMPTOM_HINTS = {
    "pain",
    "fever",
    "cough",
    "dyspnea",
    "shortness of breath",
    "nausea",
    "vomiting",
    "fatigue",
    "headache",
    "dizziness",
}
DIAGNOSIS_HINTS = {
    "infarction",
    "embolism",
    "pneumonia",
    "diabetes",
    "hypertension",
    "failure",
    "syndrome",
    "disease",
    "infection",
}
MEDICATION_HINTS = {
    "aspirin",
    "ibuprofen",
    "metformin",
    "insulin",
    "heparin",
    "warfarin",
    "statin",
    "acetaminophen",
    "paracetamol",
    "amoxicillin",
}

QUERY_SYNONYMS = {
    "heart attack": "myocardial infarction",
    "mi": "myocardial infarction",
}


@dataclass(slots=True)
class ProcessedClinicalText:
    original_text: str
    expanded_text: str
    symptoms: list[str]
    diagnoses: list[str]
    medications: list[str]


def initialize_nlp(model_name: str = "en_core_sci_md"):
    nlp = spacy.load(model_name)

    # Keep abbreviation resolution in-document to disambiguate terms like PE.
    if "abbreviation_detector" not in nlp.pipe_names:
        nlp.add_pipe("abbreviation_detector")

    # Keep negation if available, but do not hard-fail in lightweight hackathon mode.
    if "negex" not in nlp.pipe_names:
        try:
            from negspacy.negation import Negex  # noqa: F401

            nlp.add_pipe("negex", config={"ent_types": []})
        except Exception:
            pass

    return nlp


def process_clinical_text(text: str, nlp) -> ProcessedClinicalText:
    normalized_text = _normalize_query_text(text)
    doc = nlp(normalized_text)

    expanded_text = expand_abbreviations(doc)

    symptoms: list[str] = []
    diagnoses: list[str] = []
    medications: list[str] = []

    for ent in doc.ents:
        if getattr(ent._, "negex", False):
            continue

        candidate = ent.text.strip()
        if not candidate:
            continue

        category = _classify_entity_text(candidate)
        if category == "symptom":
            symptoms.append(candidate)
        elif category == "diagnosis":
            diagnoses.append(candidate)
        elif category == "medication":
            medications.append(candidate)

    return ProcessedClinicalText(
        original_text=text,
        expanded_text=expanded_text,
        symptoms=sorted(set(symptoms)),
        diagnoses=sorted(set(diagnoses)),
        medications=sorted(set(medications)),
    )


def expand_abbreviations(doc) -> str:
    abbreviations = sorted(doc._.abbreviations, key=lambda span: span.start_char)
    if not abbreviations:
        return doc.text

    parts: list[str] = []
    cursor = 0

    for abbr in abbreviations:
        long_form = str(abbr._.long_form).strip()
        if not long_form:
            continue

        parts.append(doc.text[cursor : abbr.start_char])
        parts.append(f"{abbr.text} ({long_form})")
        cursor = abbr.end_char

    parts.append(doc.text[cursor:])
    return "".join(parts)


def preprocess_query(query: str) -> str:
    return _normalize_query_text(query)


def _normalize_query_text(text: str) -> str:
    normalized = text
    for source, target in QUERY_SYNONYMS.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized, flags=re.IGNORECASE)
    return normalized


def _classify_entity_text(entity_text: str) -> str | None:
    value = entity_text.lower()

    if any(token in value for token in MEDICATION_HINTS):
        return "medication"
    if any(token in value for token in DIAGNOSIS_HINTS):
        return "diagnosis"
    if any(token in value for token in SYMPTOM_HINTS):
        return "symptom"

    return None
