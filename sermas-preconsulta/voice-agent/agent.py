import json
import re
from openai import AsyncOpenAI
from schemas import ConversationState, SymptomSummary, Turn
from prompts import SYSTEM_PROMPT, GREETING_MESSAGE, URGENCY_KEYWORDS, URGENCY_REDIRECT

client = AsyncOpenAI()


class VoiceAgent:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = ConversationState.GREETING
        self.symptoms = SymptomSummary()
        self._done = False

        # Historial de conversación para GPT-4o (formato OpenAI)
        self.conversation: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def get_greeting(self) -> str:
        """Devuelve el saludo inicial y registra el primer turno del agente."""
        self.conversation.append({"role": "assistant", "content": GREETING_MESSAGE})
        self.symptoms.raw_transcript.append(
            Turn(role="assistant", content=GREETING_MESSAGE)
        )
        self.state = ConversationState.IDENTIFY_PATIENT
        return GREETING_MESSAGE

    def is_done(self) -> bool:
        return self._done

    def get_summary(self) -> SymptomSummary:
        return self.symptoms

    async def process_turn(self, user_input: str) -> dict:
        """
        Procesa un turno del paciente y devuelve la respuesta del agente.
        Retorna: {"response": str, "done": bool, "symptoms": SymptomSummary | None}
        """
        # Detección de urgencia antes de llamar al LLM
        lower_input = user_input.lower()
        for keyword in URGENCY_KEYWORDS:
            if keyword in lower_input:
                self._done = True
                self.state = ConversationState.DONE
                return {
                    "response": URGENCY_REDIRECT,
                    "done": True,
                    "symptoms": self.symptoms,
                }

        # Registrar turno del usuario
        self.conversation.append({"role": "user", "content": user_input})
        self.symptoms.raw_transcript.append(Turn(role="user", content=user_input))

        # Llamada a GPT-4o
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=self.conversation,
            temperature=0.3,
            max_tokens=400,
        )

        assistant_message = response.choices[0].message.content

        # Registrar respuesta del agente
        self.conversation.append({"role": "assistant", "content": assistant_message})
        self.symptoms.raw_transcript.append(
            Turn(role="assistant", content=assistant_message)
        )

        # Comprobar si GPT-4o ha indicado que la conversación está completa
        done, extracted = self._extract_completion(assistant_message)

        if done and extracted:
            self._done = True
            self.state = ConversationState.DONE
            self.symptoms.cip = extracted.get("cip")
            self.symptoms.chief_complaint = extracted.get("chief_complaint")
            self.symptoms.symptoms = extracted.get("symptoms", [])
            self.symptoms.duration = extracted.get("duration")
            self.symptoms.severity = extracted.get("severity")
            self.symptoms.associated_symptoms = extracted.get("associated_symptoms", [])

            # Eliminar el bloque JSON del texto hablado (el paciente no debe oírlo)
            spoken_response = re.sub(
                r"```json.*?```", "", assistant_message, flags=re.DOTALL
            ).strip()

            return {"response": spoken_response, "done": True, "symptoms": self.symptoms}

        return {"response": assistant_message, "done": False, "symptoms": None}

    def _extract_completion(self, text: str) -> tuple[bool, dict | None]:
        """
        Extrae el bloque JSON de finalización que GPT-4o incluye al terminar.
        El prompt le instruye a escribirlo en formato ```json ... ```.
        """
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if data.get("conversation_complete"):
                    return True, data
            except json.JSONDecodeError:
                pass
        return False, None