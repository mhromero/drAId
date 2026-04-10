"""
Notificador al paciente tras la decisión médica.

PROTOTIPO: imprime el mensaje por consola y lo guarda en el caso.
PRODUCCIÓN: descomentar bloque Twilio SMS.

En producción el número de teléfono del paciente llega del campo `From`
de la llamada Twilio — el voice-agent lo pasa junto con los síntomas.
"""

import os

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCCIÓN: Twilio SMS
# Requiere: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
# El trial gratuito de Twilio permite enviar SMS al número verificado.
# ─────────────────────────────────────────────────────────────────────────────
# from twilio.rest import Client as TwilioClient
# _twilio = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
# _from_number = os.getenv("TWILIO_FROM_NUMBER")
#
# async def send_notification(phone: str, message: str) -> str:
#     msg = _twilio.messages.create(body=message, from_=_from_number, to=phone)
#     return msg.sid
# ─────────────────────────────────────────────────────────────────────────────


MESSAGES = {
    "call_now": (
        "SERMAS Madrid: Su médico ha revisado su llamada y se pondrá en contacto "
        "con usted en los próximos minutos. Por favor, mantenga su teléfono disponible."
    ),
    "keep_appointment": (
        "SERMAS Madrid: Su médico ha revisado los síntomas que nos indicó. "
        "Su cita se mantiene según lo previsto. Si empeora antes, llame al 112."
    ),
    "refer_emergency": (
        "SERMAS Madrid: Por los síntomas que ha descrito, le recomendamos que acuda "
        "a urgencias o llame al 112 lo antes posible. No espere a su cita."
    ),
}


async def notify_patient(phone: str | None, action: str, patient_name: str) -> dict:
    """
    Envía (o simula) una notificación al paciente.
    Devuelve dict con estado y mensaje enviado.
    """
    message = MESSAGES.get(action, "SERMAS Madrid: Su consulta ha sido atendida.")

    if not phone:
        print(f"[notifier] Sin teléfono para {patient_name} — notificación simulada")
        print(f"[notifier] Mensaje: {message}")
        return {"sent": False, "simulated": True, "message": message}

    # PROTOTIPO: simular envío
    # En producción: descomentar bloque Twilio arriba y llamar send_notification()
    print(f"[notifier] SIMULADO → {phone} ({patient_name}): {message}")

    # TODO [PRODUCCIÓN]: reemplazar simulación por:
    # sid = await send_notification(phone, message)
    # return {"sent": True, "sid": sid, "message": message}

    return {"sent": False, "simulated": True, "phone": phone, "message": message}