"""
Clasificador de intención del usuario.
Recibe un mensaje en lenguaje natural y devuelve la intención estructurada.
"""
import json
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from agents.prompts import INTENT_SYSTEM_PROMPT, extract_text
from config.object_types import type_names

load_dotenv()


def detect_intent(message: str, history: list[dict] | None = None) -> dict:
    """
    Clasifica la intención del mensaje del usuario.

    Args:
        message: el mensaje actual
        history: lista de {"role": "user"|"assistant", "content": "..."} (últimos N turnos)

    Devuelve un dict con:
    - intent: "generate" | "consult" | "update" | "audit" | "list" | "unclear"
    - object_type: "table" | "view" | "dashboard" | "stored_procedure" | None
    - object_name: str | None
    - question: str | None (para intent=consult)
    """
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    valid = ", ".join(f'"{t}"' for t in type_names())

    history_context = ""
    if history:
        lines = []
        for msg in history[-6:]:  # últimos 3 intercambios
            role = "Usuario" if msg["role"] == "user" else "Asistente"
            # Truncar mensajes largos para no inflar el prompt
            text = msg["content"][:300].replace("\n", " ")
            lines.append(f"{role}: {text}")
        history_context = "Historial reciente:\n" + "\n".join(lines) + "\n\n"

    prompt = INTENT_SYSTEM_PROMPT.format(
        message=message,
        valid_types=valid,
        history_context=history_context,
    )
    response = llm.invoke(prompt)
    text = extract_text(response)

    # Limpiar bloque de código markdown si está presente
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    try:
        result = json.loads(text)
        # Normalizar valores
        result.setdefault("intent", "unclear")
        result.setdefault("object_type", None)
        result.setdefault("object_name", None)
        result.setdefault("question", None)
        return result
    except (json.JSONDecodeError, ValueError):
        return {
            "intent": "unclear",
            "object_type": None,
            "object_name": None,
            "question": None,
        }
