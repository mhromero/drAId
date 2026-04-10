"""
Mapper FHIR → dict limpio para el LLM.

Extrae los recursos relevantes del Bundle FHIR y los convierte en
un diccionario estructurado que el llm-service puede procesar directamente.
"""

from datetime import date


def map_bundle(bundle: dict) -> dict:
    """
    Convierte un Bundle FHIR R4 en un dict con la información clínica relevante.
    Ignora campos técnicos y se queda solo con lo útil para el triaje.
    """
    patient_info = {}
    conditions = []
    medications = []
    allergies = []
    encounters = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")

        if rtype == "Patient":
            patient_info = _map_patient(resource)

        elif rtype == "Condition":
            c = _map_condition(resource)
            if c:
                conditions.append(c)

        elif rtype == "MedicationRequest":
            m = _map_medication(resource)
            if m:
                medications.append(m)

        elif rtype == "AllergyIntolerance":
            a = _map_allergy(resource)
            if a:
                allergies.append(a)

        elif rtype == "Encounter":
            e = _map_encounter(resource)
            if e:
                encounters.append(e)

    # Ordenar visitas por fecha descendente (las más recientes primero)
    encounters.sort(key=lambda x: x.get("fecha", ""), reverse=True)

    return {
        "paciente": patient_info,
        "diagnosticos_activos": conditions,
        "medicacion_actual": medications,
        "alergias": allergies,
        "visitas_recientes": encounters[:5],  # últimas 5 visitas
    }


def _map_patient(r: dict) -> dict:
    name = r.get("name", [{}])[0]
    given = " ".join(name.get("given", []))
    family = name.get("family", "")
    birth = r.get("birthDate", "")
    age = _calc_age(birth)
    return {
        "nombre": f"{given} {family}".strip(),
        "cip": next(
            (i["value"] for i in r.get("identifier", [])
             if "sermas" in i.get("system", "")),
            None
        ),
        "fecha_nacimiento": birth,
        "edad": age,
        "sexo": r.get("gender", ""),
    }


def _map_condition(r: dict) -> dict | None:
    status = (r.get("clinicalStatus") or {})
    status_code = ""
    for coding in status.get("coding", []):
        status_code = coding.get("code", "")
    if status_code not in ("active", ""):
        return None

    codings = r.get("code", {}).get("coding", [])
    if not codings:
        return None

    return {
        "nombre": codings[0].get("display", ""),
        "codigo_snomed": codings[0].get("code", ""),
        "desde": r.get("onsetDateTime", "")[:10] if r.get("onsetDateTime") else "",
    }


def _map_medication(r: dict) -> dict | None:
    if r.get("status") != "active":
        return None
    codings = r.get("medicationCodeableConcept", {}).get("coding", [])
    if not codings:
        return None
    dosage = r.get("dosageInstruction", [{}])[0].get("text", "")
    return {
        "nombre": codings[0].get("display", ""),
        "posologia": dosage,
    }


def _map_allergy(r: dict) -> dict | None:
    codings = r.get("code", {}).get("coding", [])
    if not codings:
        return None
    reactions = r.get("reaction", [{}])[0]
    manifestation = (reactions.get("manifestation") or [{}])[0]
    mcodings = manifestation.get("coding", [{}])
    return {
        "sustancia": codings[0].get("display", ""),
        "criticidad": r.get("criticality", ""),
        "manifestacion": mcodings[0].get("display", "") if mcodings else "",
    }


def _map_encounter(r: dict) -> dict | None:
    period = r.get("period", {})
    reason = (r.get("reasonCode") or [{}])[0].get("text", "")
    diagnosis = (r.get("diagnosis") or [{}])[0].get("condition", {}).get("display", "")
    return {
        "fecha": period.get("start", "")[:10],
        "motivo": reason,
        "resultado": diagnosis,
    }


def _calc_age(birth_date: str) -> int | None:
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(birth_date)
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except ValueError:
        return None