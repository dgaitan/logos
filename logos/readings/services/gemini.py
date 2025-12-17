from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiError(RuntimeError):
    """Raised when there is a problem talking to the Gemini API."""


def _build_prompt(
    *,
    gospel_text: str,
    reference: str,
    liturgical_date: dt.date,
    language_code: str,
) -> str:
    date_str = liturgical_date.strftime("%Y-%m-%d")
    # We currently target Spanish output, but we keep language_code for future use.
    return (
        "Eres un teólogo católico fiel al Magisterio de la Iglesia inspirado por Joseph Ratzinger.\n\n"
        f"Escribe una meditación espiritual en {language_code} sobre el evangelio del día.\n"
        "La meditación debe:\n"
        "- Ayudar a la oración personal.\n"
        "- Ser fiel al sentido del texto bíblico.\n"
        "- Tener un tono cercano y pastoral.\n"
        "- Evitar opiniones políticas o polémicas.\n\n"
        f"Fecha litúrgica: {date_str}\n"
        f"Evangelio: {reference}\n\n"
        "Texto del evangelio:\n"
        f"{gospel_text}\n\n"
        "Ahora escribe solo la meditación, sin repetir el texto completo del evangelio."
    )


def generate_meditation(
    *,
    gospel_text: str,
    reference: str,
    liturgical_date: dt.date,
    language_code: str = "es",
) -> str:
    """Call Gemini to generate a meditation for the given gospel.

    Returns the meditation text, or raises GeminiError on failure.
    """
    api_key: str = getattr(settings, "GEMINI_API_KEY", "")
    model: str = getattr(settings, "GEMINI_MODEL_NAME", "gemini-1.5-pro")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not configured.")

    url = _GEMINI_URL_TEMPLATE.format(model=model)
    prompt = _build_prompt(
        gospel_text=gospel_text,
        reference=reference,
        liturgical_date=liturgical_date,
        language_code=language_code,
    )

    payload: dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ],
            }
        ]
    }
    params = {"key": api_key}

    try:
        response = requests.post(url, json=payload, params=params, timeout=30)
    except requests.RequestException as exc:  # noqa: PERF203
        msg = f"Error calling Gemini API: {exc}"
        logger.error(msg)
        raise GeminiError(msg) from exc

    if response.status_code != 200:
        msg = f"Gemini API returned HTTP {response.status_code}: {response.text}"
        logger.error(msg)
        raise GeminiError(msg)

    data: dict[str, Any] = response.json()
    try:
        candidates = data["candidates"]
        first_candidate = candidates[0]
        content = first_candidate["content"]
        parts = content["parts"]
        text = parts[0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        msg = f"Unexpected Gemini response format: {data}"
        logger.error(msg)
        raise GeminiError(msg) from exc

    return str(text).strip()
