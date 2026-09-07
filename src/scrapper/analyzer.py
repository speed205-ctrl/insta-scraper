"""
LLM analysis module leveraging Google Gemini API or local Ollama for hook classification, psychology, and script generation.
"""

import json
import logging
import re
from typing import Any, Dict, Optional
import requests

from scrapper.config import settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0"

ANALYSIS_SYSTEM_PROMPT = """Eres un estratega experto de clase mundial en contenido viral para Instagram Reels y TikTok, especializado en psicología de la atención, neuromarketing y retención de audiencia.

Tu trabajo es analizar la transcripción y metadatos de un Reel que se volvió VIRAL (outlier estadístico) y desglosar con precisión científica por qué funcionó, además de crear una variación mejorada y accionable.

Debes responder ÚNICAMENTE con un objeto JSON válido que contenga exactamente los siguientes campos:

{
  "hook_text": "La frase o gancho exacto dicho o mostrado en los primeros 3 a 5 segundos del video.",
  "hook_type": "Categoría del gancho (ej. 'Pregunta provocadora', 'Dato de shock / Quiebre de patrón', 'Curiosidad / Brecha de información', 'Dolor agudo / Identificación', 'Contra-intuitivo / Polémica', 'Promesa de transformación').",
  "hook_score": 9, // Número entero del 1 al 10 que califica la efectividad del gancho.
  "psychological_trigger": "Explicación clara y profunda de los gatillos psicológicos, sesgos cognitivos y razones de retención que hicieron que la audiencia viera y compartiera el video.",
  "generated_script": "Guion estructurado y adaptado paso a paso para crear un video similar de alto impacto. Formato:\\n\\n[GANCHO (0-3s)]\\n...\\n\\n[PROBLEMA / TENSION (3-15s)]\\n...\\n\\n[SOLUCION / VALOR CENTRAL (15-45s)]\\n...\\n\\n[LLAMADO A LA ACCION (CTA)]\\n..."
}

IMPORTANTE: Devuelve SOLO el JSON sin texto introductorio ni explicaciones fuera del JSON.
"""


def _clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Extract and parse JSON object from LLM response text."""
    clean_text = raw_text.strip()

    # Strip markdown code fences if present
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
        clean_text = re.sub(r"\s*```$", "", clean_text)
        clean_text = clean_text.strip()

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        # Try extracting innermost JSON using regex
        match = re.search(r"\{.*\}", clean_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as err:
                logger.error(f"Failed to parse matched JSON substring: {err}")

        logger.error(f"Could not parse LLM output as JSON. Raw output:\n{raw_text}")
        return {
            "hook_text": "No parseable hook extracted",
            "hook_type": "General Viral Analysis",
            "hook_score": 7,
            "psychological_trigger": raw_text[:500],
            "generated_script": raw_text,
        }


def _build_user_prompt(
    transcript: str,
    caption: str,
    views: int,
    likes: int,
    comments: int,
    median_views: int,
) -> str:
    """Build standardized user prompt for both Gemini and Ollama."""
    multiplier = (views / median_views) if median_views > 0 else 1.0
    return f"""METADATOS DEL REEL VIRAL:
- Reproducciones: {views:,} (Rendimiento: {multiplier:.1f}x veces la mediana de la cuenta de {median_views:,} vistas)
- Me gusta: {likes:,}
- Comentarios: {comments:,}
- Descripción original (Caption):
\"\"\"{caption}\"\"\"

TRANSCRIPCIÓN COMPLETA DEL AUDIO:
\"\"\"{transcript}\"\"\"

Por favor, analiza este contenido y devuelve el JSON requerido.
"""


class GeminiAnalyzer:
    """Analyzer utilizing Google Gemini API for deep viral content analysis."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model_name or settings.gemini_model
        self.client = None
        self._setup_client()

    def _setup_client(self) -> None:
        """Initialize Google GenAI client."""
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Operating in mock/fallback mode.")
            return

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Gemini client initialized with model '{self.model_name}'.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self.client = None

    def analyze_viral_reel(
        self,
        transcript: str,
        caption: str = "",
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        median_views: int = 0,
    ) -> Dict[str, Any]:
        """Perform AI analysis using Gemini API."""
        user_content = _build_user_prompt(transcript, caption, views, likes, comments, median_views)

        if not self.client:
            logger.warning("Using mock analysis since Gemini API is not configured.")
            multiplier = (views / median_views) if median_views > 0 else 1.0
            return {
                "hook_text": (transcript[:120] + "...") if transcript else "Primeros segundos del video",
                "hook_type": "Hook de Retención / Curiosidad",
                "hook_score": 8,
                "psychological_trigger": (
                    f"El video generó {views:,} reproducciones ({multiplier:.1f}x la mediana) gracias a un ritmo ágil "
                    "y una estructura de quiebre de expectativas en los primeros 3 segundos."
                ),
                "generated_script": (
                    "[GANCHO (0-3s)]\n¿Sabías este secreto que pocos aplican?\n\n"
                    "[PROBLEMA (3-15s)]\nLa mayoría comete este error común al crear contenido...\n\n"
                    "[SOLUCIÓN (15-45s)]\nAplica estos 3 pasos clave...\n\n"
                    "[LLAMADO A LA ACCIÓN]\nGuarda este Reel para aplicarlo hoy mismo."
                ),
                "model_used": "mock-fallback",
                "prompt_version": PROMPT_VERSION,
            }

        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=ANALYSIS_SYSTEM_PROMPT,
                    temperature=0.7,
                ),
            )

            raw_text = response.text or ""
            parsed = _clean_and_parse_json(raw_text)
            parsed["model_used"] = self.model_name
            parsed["prompt_version"] = PROMPT_VERSION

            logger.info(f"Gemini AI analysis completed (Hook: '{parsed.get('hook_type')}', Score: {parsed.get('hook_score')}/10).")
            return parsed

        except Exception as e:
            logger.error(f"Gemini API request failed: {e}")
            return {
                "hook_text": transcript[:100] if transcript else "",
                "hook_type": "Error en API",
                "hook_score": 0,
                "psychological_trigger": f"Error al consultar Gemini API: {e}",
                "generated_script": "",
                "model_used": self.model_name,
                "prompt_version": PROMPT_VERSION,
            }


class OllamaAnalyzer:
    """Local LLM Analyzer utilizing Ollama REST API (100% offline and free)."""

    def __init__(self, base_url: Optional[str] = None, model_name: Optional[str] = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_name = model_name or settings.ollama_model

    def is_available(self) -> bool:
        """Check if local Ollama server is running and accessible."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return res.status_code == 200
        except Exception:
            return False

    def analyze_viral_reel(
        self,
        transcript: str,
        caption: str = "",
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        median_views: int = 0,
    ) -> Dict[str, Any]:
        """Perform AI analysis using local Ollama model."""
        user_content = _build_user_prompt(transcript, caption, views, likes, comments, median_views)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.7,
            },
        }

        try:
            logger.info(f"Querying local Ollama server ({self.base_url}) with model '{self.model_name}'...")
            res = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)

            if res.status_code != 200:
                logger.error(f"Ollama returned status code {res.status_code}: {res.text}")
                raise ConnectionError(f"Ollama API error ({res.status_code}): {res.text}")

            response_data = res.json()
            raw_text = response_data.get("message", {}).get("content", "")

            parsed = _clean_and_parse_json(raw_text)
            parsed["model_used"] = f"ollama/{self.model_name}"
            parsed["prompt_version"] = PROMPT_VERSION

            logger.info(f"Ollama local analysis completed (Hook: '{parsed.get('hook_type')}', Score: {parsed.get('hook_score')}/10).")
            return parsed

        except Exception as e:
            logger.error(f"Ollama execution failed ({e}). Returning fallback report.")
            multiplier = (views / median_views) if median_views > 0 else 1.0
            return {
                "hook_text": transcript[:100] if transcript else "Primeros 3 segundos",
                "hook_type": "Ollama Error / Fallback",
                "hook_score": 5,
                "psychological_trigger": f"No se pudo contactar a Ollama en {self.base_url}. Asegúrate de que Ollama esté ejecutándose (`ollama serve`). Error: {e}",
                "generated_script": (
                    "[GANCHO]\nGuion básico generado por fallback.\n\n"
                    "[DESARROLLO]\nInicia Ollama con tu modelo favorito para análisis detallado."
                ),
                "model_used": f"ollama/{self.model_name}",
                "prompt_version": PROMPT_VERSION,
            }


def get_analyzer(provider: Optional[str] = None):
    """
    Factory to obtain the configured AI Analyzer (Gemini API or Ollama Local).

    Args:
        provider: Explicit provider ('gemini' or 'ollama'). Defaults to settings.llm_provider.
    """
    selected_provider = (provider or settings.llm_provider).lower().strip()

    if selected_provider == "ollama":
        logger.info(f"Using Ollama local LLM analyzer (model: {settings.ollama_model}).")
        return OllamaAnalyzer()
    else:
        logger.info(f"Using Google Gemini API analyzer (model: {settings.gemini_model}).")
        return GeminiAnalyzer()
