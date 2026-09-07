"""
Main pipeline orchestrator for Instagram Viral Scraper & AI Analyzer.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.logging import RichHandler
from sqlalchemy import select

from scrapper.config import settings
from scrapper.db import (
    AIAnalysis,
    Competitor,
    Reel,
    ScrapeRun,
    get_db,
    init_db,
)
from scrapper.scraper import InstagramScraper
from scrapper.outlier import detect_outliers
from scrapper.transcriber import WhisperTranscriber, download_audio
from scrapper.analyzer import get_analyzer
from scrapper.telegram import send_viral_alert

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup rich console with UTF-8 safe configuration
console = Console(force_terminal=True, legacy_windows=False)


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging using RichHandler."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=False)],
    )


def get_or_create_competitor(session, username: str) -> Competitor:
    """Fetch competitor by username or create a new entry."""
    clean_username = username.lstrip("@").strip().lower()
    stmt = select(Competitor).where(Competitor.username == clean_username)
    competitor = session.scalars(stmt).first()

    if not competitor:
        competitor = Competitor(
            username=clean_username,
            platform="instagram",
            median_views=0,
        )
        session.add(competitor)
        session.commit()
        session.refresh(competitor)
        console.print(f"[green]✓ Registrado nuevo competidor:[/green] @{clean_username} (ID: {competitor.id})")
    else:
        console.print(f"[blue]ℹ Competidor encontrado:[/blue] @{clean_username} (Mediana previa: {competitor.median_views:,} vistas)")

    return competitor


def run_pipeline(
    target_username: str,
    max_posts: Optional[int] = None,
    multiplier: Optional[float] = None,
    provider: Optional[str] = None,
    skip_transcription: bool = False,
) -> None:
    """
    Execute full end-to-end viral discovery and analysis pipeline.

    Args:
        target_username: Instagram account handle to monitor.
        max_posts: Maximum posts to fetch.
        multiplier: Outlier threshold multiplier.
        provider: AI Provider ('gemini' or 'ollama').
        skip_transcription: If True, only perform scraping and outlier detection.
    """
    clean_username = target_username.lstrip("@").strip().lower()
    limit = max_posts or settings.max_posts_per_account
    mult = multiplier or settings.outlier_multiplier
    selected_provider = (provider or settings.llm_provider).lower()
    active_model = settings.ollama_model if selected_provider == "ollama" else settings.gemini_model

    console.print(Panel.fit(
        f"[bold cyan]🎯 Instagram Viral Content Scraper & AI Analyzer[/bold cyan]\n"
        f"[dim]Monitoreando:[/dim] [yellow]@{clean_username}[/yellow] | "
        f"[dim]Límite:[/dim] {limit} posts | [dim]Multiplicador:[/dim] {mult}x\n"
        f"[dim]Motor IA:[/dim] [magenta]{selected_provider.upper()}[/magenta] ([dim]{active_model}[/dim])",
        border_style="cyan",
    ))

    # Step 1: Initialize Database
    init_db()
    
    with next(get_db()) as session:
        competitor = get_or_create_competitor(session, clean_username)

        # Create audit run
        run_record = ScrapeRun(
            competitor_id=competitor.id,
            status="running",
            posts_fetched=0,
            outliers_found=0,
        )
        session.add(run_record)
        session.commit()

        try:
            # Step 2: Scrape Posts
            console.print("\n[bold]1. Extrayendo posts de Instagram...[/bold]")
            scraper = InstagramScraper()
            posts = scraper.fetch_posts(clean_username, max_posts=limit)

            if not posts:
                console.print("[yellow]⚠ No se encontraron posts o la cuenta es privada/inaccesible.[/yellow]")
                run_record.status = "completed"
                run_record.finished_at = datetime.now(timezone.utc)
                session.commit()
                return

            run_record.posts_fetched = len(posts)

            # Step 3: Detect Outliers & Calculate Median
            console.print("\n[bold]2. Analizando métricas y detectando Outliers...[/bold]")
            computed_median, outliers, classified_posts = detect_outliers(
                posts=posts,
                multiplier=mult,
                historical_median=competitor.median_views,
            )

            # Update competitor median
            competitor.median_views = computed_median
            competitor.updated_at = datetime.now(timezone.utc)
            run_record.outliers_found = len(outliers)

            # Step 4: Persist or Update Reels in DB
            reels_by_shortcode = {}
            for p in classified_posts:
                stmt = select(Reel).where(Reel.shortcode == p["shortcode"])
                reel_obj = session.scalars(stmt).first()

                if not reel_obj:
                    reel_obj = Reel(
                        competitor_id=competitor.id,
                        shortcode=p["shortcode"],
                        url=p["url"],
                        views=p["views"],
                        likes=p["likes"],
                        comments=p["comments"],
                        shares=p["shares"],
                        duration_secs=p["duration_secs"],
                        caption=p["caption"],
                        is_outlier=p["is_outlier"],
                        published_at=p["published_at"],
                    )
                    session.add(reel_obj)
                else:
                    # Update metrics
                    reel_obj.views = p["views"]
                    reel_obj.likes = p["likes"]
                    reel_obj.comments = p["comments"]
                    reel_obj.is_outlier = p["is_outlier"]

                reels_by_shortcode[p["shortcode"]] = reel_obj

            session.commit()

            # Display Results Table
            table = Table(title=f"Resultados de @{clean_username} (Mediana: {computed_median:,} vistas)")
            table.add_column("Shortcode", style="cyan")
            table.add_column("Vistas", justify="right")
            table.add_column("Ratio Mediana", justify="right")
            table.add_column("Likes", justify="right")
            table.add_column("Comentarios", justify="right")
            table.add_column("Viral/Outlier", justify="center")

            for p in classified_posts:
                is_out = p["is_outlier"]
                status_str = "[bold green]🔥 SÍ[/bold green]" if is_out else "[dim]No[/dim]"
                table.add_row(
                    p["shortcode"],
                    f"{p['views']:,}",
                    f"{p.get('median_ratio', 1.0):.1f}x",
                    f"{p['likes']:,}",
                    f"{p['comments']:,}",
                    status_str,
                )

            console.print(table)

            if not outliers:
                console.print("[yellow]ℹ No se detectaron posts que superen el umbral de viralidad configurado.[/yellow]")
                run_record.status = "completed"
                run_record.finished_at = datetime.now(timezone.utc)
                session.commit()
                return

            console.print(f"\n[bold green]🔥 Se detectaron {len(outliers)} Reels Virales para procesar con IA.[/bold green]")

            if skip_transcription:
                console.print("[dim]Transcripción y análisis con IA omitidos (--skip-transcription activado).[/dim]")
                run_record.status = "completed"
                run_record.finished_at = datetime.now(timezone.utc)
                session.commit()
                return

            # Step 5: Audio Download, STT Transcription, & AI Analysis
            console.print(f"\n[bold]3. Descarga de audio, Transcripción (Whisper) y Análisis de IA ({selected_provider.capitalize()})...[/bold]")
            
            # Lazy initialize expensive AI models
            transcriber = None
            analyzer = get_analyzer(provider=selected_provider)

            for idx, out_post in enumerate(outliers, 1):
                shortcode = out_post["shortcode"]
                reel_db = reels_by_shortcode.get(shortcode)
                
                if not reel_db:
                    stmt = select(Reel).where(Reel.shortcode == shortcode)
                    reel_db = session.scalars(stmt).first()

                # Check if analysis already exists
                stmt_an = select(AIAnalysis).where(AIAnalysis.reel_id == reel_db.id)
                existing_analysis = session.scalars(stmt_an).first()

                if existing_analysis:
                    console.print(f"[blue]ℹ [{idx}/{len(outliers)}] Reel {shortcode} ya cuenta con análisis previo. Omitiendo.[/blue]")
                    continue

                console.print(f"\n[bold cyan]─── Procesando Outlier [{idx}/{len(outliers)}]: {shortcode} ({out_post['views']:,} vistas) ───[/bold cyan]")

                # A. Download Audio
                audio_file = download_audio(out_post["url"], shortcode=shortcode)
                if not audio_file:
                    console.print(f"[red]✗ No se pudo descargar el audio para {shortcode}.[/red]")
                    continue

                reel_db.audio_path = str(audio_file)
                session.commit()

                # B. Transcribe with Whisper
                if transcriber is None:
                    transcriber = WhisperTranscriber()

                stt_result = transcriber.transcribe(audio_file)
                transcript_text = stt_result.get("transcript", "")
                console.print(f"[green]✓ Transcripción:[/green] \"{transcript_text[:150]}...\"")

                # C. LLM Reasoning (Gemini or Ollama)
                console.print(f"[dim]Consultando {selected_provider.upper()} para análisis cognitivo de gancho y guion...[/dim]")
                ai_result = analyzer.analyze_viral_reel(
                    transcript=transcript_text,
                    caption=out_post.get("caption", ""),
                    views=out_post.get("views", 0),
                    likes=out_post.get("likes", 0),
                    comments=out_post.get("comments", 0),
                    median_views=computed_median,
                )

                # D. Save Analysis to Database
                analysis_entry = AIAnalysis(
                    reel_id=reel_db.id,
                    transcript=transcript_text,
                    hook_text=ai_result.get("hook_text"),
                    hook_type=ai_result.get("hook_type"),
                    hook_score=ai_result.get("hook_score"),
                    psychological_trigger=ai_result.get("psychological_trigger"),
                    generated_script=ai_result.get("generated_script"),
                    model_used=ai_result.get("model_used", active_model),
                    prompt_version=ai_result.get("prompt_version", "v1.0"),
                )
                session.add(analysis_entry)
                session.commit()

                # Show Summary Box
                console.print(Panel(
                    f"[bold]Tipo de Gancho:[/bold] {ai_result.get('hook_type')} (Score: ⭐ {ai_result.get('hook_score')}/10)\n"
                    f"[bold]Frase Inicial:[/bold] \"{ai_result.get('hook_text')}\"\n\n"
                    f"[bold]Gatillo Psicológico:[/bold]\n{ai_result.get('psychological_trigger')}\n\n"
                    f"[bold]Guion Adaptado:[/bold]\n{ai_result.get('generated_script')[:300]}...",
                    title=f"Inteligencia Generada: {shortcode} ({ai_result.get('model_used')})",
                    border_style="green",
                ))

                # E. Telegram Notification Alert
                if settings.telegram_bot_token and settings.telegram_chat_id:
                    console.print("[dim]Enviando alerta a Telegram...[/dim]")
                    send_viral_alert(
                        competitor_username=clean_username,
                        reel=out_post,
                        analysis=ai_result,
                        median_views=computed_median,
                    )

            # Finalize Audit Run
            run_record.status = "completed"
            run_record.finished_at = datetime.now(timezone.utc)
            session.commit()
            console.print("\n[bold green]✨ ¡Pipeline completado con éxito! Inteligencia almacenada en base de datos.[/bold green]\n")

        except Exception as e:
            console.print(f"\n[bold red]✗ Error durante la ejecución del pipeline:[/bold red] {e}")
            if "429" in str(e) or "login" in str(e).lower() or "checkpoint" in str(e).lower():
                console.print(
                    "\n[bold yellow]💡 Instagram bloqueó la petición o requiere autenticación.[/bold yellow]\n"
                    "[bold green]Solución:[/bold green] Inicia sesión de forma manual con tu navegador ejecutando:\n"
                    "   [bold cyan]python -m scrapper --login[/bold cyan]\n"
                )
            run_record.status = "failed"
            run_record.error_message = str(e)
            run_record.finished_at = datetime.now(timezone.utc)
            session.commit()
            raise


def main() -> None:
    """CLI Entry point for direct execution."""
    parser = argparse.ArgumentParser(
        description="Instagram Viral Content Scraper & AI Analyzer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "username",
        nargs="?",
        default="cuenta_de_ejemplo",
        help="Target Instagram username (e.g. cuenta_de_ejemplo)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open visible browser to log into Instagram manually and save session",
    )
    parser.add_argument(
        "-p", "--posts",
        type=int,
        default=settings.max_posts_per_account,
        help="Number of recent posts to scrape",
    )
    parser.add_argument(
        "-m", "--multiplier",
        type=float,
        default=settings.outlier_multiplier,
        help="Outlier multiplier threshold over historical median views",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "ollama"],
        default=settings.llm_provider,
        help="AI Provider for cognitive and script analysis (gemini or ollama)",
    )
    parser.add_argument(
        "--skip-transcription",
        action="store_true",
        help="Only scrape and detect outliers without downloading audio and running AI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug verbose logging",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if args.login:
        from scrapper.browser_auth import interactive_browser_login
        interactive_browser_login(
            target_username=args.username if args.username != "cuenta_de_ejemplo" else None
        )
        return

    run_pipeline(
        target_username=args.username,
        max_posts=args.posts,
        multiplier=args.multiplier,
        provider=args.provider,
        skip_transcription=args.skip_transcription,
    )


if __name__ == "__main__":
    main()

