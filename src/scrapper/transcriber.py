"""
Audio extraction (yt-dlp) and local Speech-To-Text transcription (faster-whisper).
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yt_dlp

from scrapper.config import settings

logger = logging.getLogger(__name__)


def download_audio(url: str, shortcode: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Download audio track of an Instagram Reel as MP3 using yt-dlp.

    Args:
        url: Reel URL (e.g. 'https://www.instagram.com/p/Cxyz123/').
        shortcode: Unique post identifier for clean naming.
        output_dir: Target directory to save audio. Defaults to settings.absolute_audio_dir.

    Returns:
        Path to downloaded .mp3 file, or None if download failed.
    """
    target_dir = output_dir or settings.absolute_audio_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    final_mp3_path = target_dir / f"{shortcode}.mp3"

    # Reuse existing download if available
    if final_mp3_path.exists() and final_mp3_path.stat().st_size > 0:
        logger.info(f"Reusing existing audio cache: {final_mp3_path.name}")
        return final_mp3_path

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(target_dir / f"{shortcode}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    logger.info(f"Downloading audio for Reel {shortcode} from {url}...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if final_mp3_path.exists() and final_mp3_path.stat().st_size > 0:
            logger.info(f"Audio downloaded successfully: {final_mp3_path.name}")
            return final_mp3_path

        # Fallback search if extension didn't match expected
        for candidate in target_dir.glob(f"{shortcode}.*"):
            if candidate.is_file() and candidate.stat().st_size > 0:
                logger.info(f"Found downloaded audio file: {candidate.name}")
                return candidate

        logger.warning(f"yt-dlp finished but audio file was not found for {shortcode}.")
        return None

    except Exception as e:
        logger.error(f"Failed to download audio for Reel {shortcode}: {e}")
        return None


class WhisperTranscriber:
    """Wrapper around faster-whisper with automatic CUDA GPU and CPU fallback."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        self.model_name = model_name or settings.whisper_model
        self.device = (device or settings.whisper_device).lower()
        self.compute_type = compute_type or settings.whisper_compute_type
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Initialize faster-whisper model on GPU with fallback to CPU."""
        from faster_whisper import WhisperModel

        try:
            logger.info(
                f"Loading faster-whisper model '{self.model_name}' on device='{self.device}', "
                f"compute_type='{self.compute_type}'..."
            )
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(f"faster-whisper model '{self.model_name}' successfully loaded on {self.device.upper()}.")
        except Exception as e:
            if self.device == "cuda":
                logger.warning(
                    f"Failed to initialize Whisper on CUDA ({e}). Falling back to CPU with int8 quantization..."
                )
                try:
                    self.device = "cpu"
                    self.compute_type = "int8"
                    self.model = WhisperModel(
                        self.model_name,
                        device="cpu",
                        compute_type="int8",
                    )
                    logger.info("faster-whisper loaded successfully on CPU fallback.")
                except Exception as cpu_err:
                    logger.error(f"Failed to load Whisper model on CPU fallback: {cpu_err}")
                    raise
            else:
                logger.error(f"Failed to load Whisper model: {e}")
                raise

    def transcribe(self, audio_path: Path) -> Dict[str, Any]:
        """
        Transcribe the spoken audio from an audio file.

        Args:
            audio_path: Path to MP3/WAV audio file.

        Returns:
            Dict containing full transcribed text, detected language, and segments.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing audio: {audio_path.name}...")
        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segment_list = []
        full_text_chunks = []

        for segment in segments:
            full_text_chunks.append(segment.text.strip())
            segment_list.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
            })

        full_transcript = " ".join(full_text_chunks).strip()
        logger.info(
            f"Transcription complete ({len(full_text_chunks)} segments, language='{info.language}', "
            f"probability={info.language_probability:.2f})."
        )

        return {
            "transcript": full_transcript,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": round(info.duration, 2),
            "segments": segment_list,
        }
