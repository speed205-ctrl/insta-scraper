Stack Tecnológico
El stack está optimizado para desarrollo ágil en Python, ejecución local eficiente y alta capacidad de procesamiento de IA.

Lenguaje Core: Python 3.10+ (Estándar de la industria para scripting, manejo de datos y pipelines de IA).

Extracción de Datos (Scraping):

Opción A: Apify API (apify-client) — Recomendado para evitar bloqueos complejos de infraestructura IP en Instagram.

Opción B: Instaloader / Playwright — Alternativa open source local para control total sin pasarelas de pago de terceros.

Procesamiento de Audio & Transcripción (STT):

OpenAI Whisper (faster-whisper) — Ejecución local ultrarrápida para transcribir los audios de los Reels con alta precisión directamente en hardware local (GPU compatible con CUDA).

Manipulación y Análisis de Datos:

Pandas — Para limpiar, calcular medianas y estructurar dataframes de métricas.

Inteligencia Artificial y Razonamiento (LLMs):

Google Gemini API (google-genai) o modelos locales vía Ollama (ej. Gemma / Llama) — Para ejecutar los prompts de análisis de ganchos, estructuración de guiones y redacción creativa.

Persistencia de Datos:

SQLite (con ORM opcional como SQLAlchemy o nativo vía sqlite3) — Almacenamiento local ultrarrápido y sin dependencias de servidores externos.

Automatización y Alertas (Opcional):

Python requests + Telegram Bot API — Para enviar notificaciones automáticas al teléfono cada vez que se detecte un nuevo video viral analizado.