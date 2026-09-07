"""
Unit tests for AI Analyzer parser and mock analysis.
"""

from scrapper.analyzer import _clean_and_parse_json, GeminiAnalyzer


def test_clean_and_parse_json_raw():
    raw = '{"hook_text": "Atención creadores", "hook_type": "Pregunta", "hook_score": 9, "psychological_trigger": "Curiosidad", "generated_script": "Guion"}'
    parsed = _clean_and_parse_json(raw)
    assert parsed["hook_text"] == "Atención creadores"
    assert parsed["hook_score"] == 9
    assert parsed["hook_type"] == "Pregunta"


def test_clean_and_parse_json_with_code_fences():
    raw = """```json
{
  "hook_text": "¿Sabías esto?",
  "hook_type": "Dato de Shock",
  "hook_score": 10,
  "psychological_trigger": "Dopamina inmediata",
  "generated_script": "[GANCHO]\\nTest"
}
```"""
    parsed = _clean_and_parse_json(raw)
    assert parsed["hook_text"] == "¿Sabías esto?"
    assert parsed["hook_score"] == 10
    assert parsed["hook_type"] == "Dato de Shock"


def test_clean_and_parse_json_fallback_on_invalid():
    raw = "Este es un texto libre sin formato JSON válido pero con contenido."
    parsed = _clean_and_parse_json(raw)
    assert "hook_score" in parsed
    assert "generated_script" in parsed


def test_analyzer_fallback_without_api_key():
    analyzer = GeminiAnalyzer(api_key="")
    result = analyzer.analyze_viral_reel(
        transcript="En este video te enseño cómo multiplicar tus vistas.",
        caption="Secretos de viralidad",
        views=50000,
        median_views=10000,
    )
    assert result["model_used"] == "mock-fallback"
    assert "hook_text" in result
    assert "generated_script" in result


def test_ollama_analyzer_fallback():
    from scrapper.analyzer import OllamaAnalyzer
    analyzer = OllamaAnalyzer(base_url="http://127.0.0.1:9999", model_name="llama3.1:8b")
    # Should handle offline gracefully with fallback structure
    result = analyzer.analyze_viral_reel(
        transcript="Este es un reel viral para probar Ollama offline.",
        caption="Caption de prueba",
        views=30000,
        median_views=5000,
    )
    assert result["model_used"] == "ollama/llama3.1:8b"
    assert "hook_score" in result
    assert "generated_script" in result


def test_get_analyzer_factory():
    from scrapper.analyzer import get_analyzer, GeminiAnalyzer, OllamaAnalyzer
    gemini_instance = get_analyzer("gemini")
    assert isinstance(gemini_instance, GeminiAnalyzer)

    ollama_instance = get_analyzer("ollama")
    assert isinstance(ollama_instance, OllamaAnalyzer)

