"""
Google Cloud Text-to-Speech (Gemini TTS) integration for LiveKit Agents
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from google.cloud import texttospeech_v1 as texttospeech
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)


@dataclass
class GoogleTTSOptions:
    """Configuration options for Google TTS"""
    voice_name: str = "en-AU-Chirp-HD-O"
    language_code: str = "en-AU"
    speaking_rate: float = 1.0
    pitch: float = 0.0
    volume_gain_db: float = 0.0
    sample_rate_hertz: int = 24000  # LiveKit typically uses 24kHz


class GoogleTTS(tts.TTS):
    """
    Google Cloud Text-to-Speech integration for LiveKit.
    Uses Gemini's advanced Chirp HD voices.
    """

    def __init__(
        self,
        *,
        voice_name: str | None = None,
        language_code: str | None = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        volume_gain_db: float = 0.0,
        sample_rate_hertz: int = 24000,
        api_key: str | None = None,
    ):
        """
        Initialize Google TTS.

        Args:
            voice_name: Google TTS voice name (e.g., "en-AU-Chirp-HD-O")
            language_code: Language code (e.g., "en-AU")
            speaking_rate: Speaking rate/speed (0.25 to 4.0)
            pitch: Voice pitch (-20.0 to 20.0)
            volume_gain_db: Volume gain in dB (-96.0 to 16.0)
            sample_rate_hertz: Audio sample rate (24000 for LiveKit)
            api_key: Google Cloud API key (or set GOOGLE_API_KEY env var)
        """
        super().__init__(
            capabilities=tts.TTSCapabilities(
                streaming=False,  # Google TTS doesn't support streaming synthesis
            ),
            sample_rate=sample_rate_hertz,
            num_channels=1,
        )

        # Get API key from parameter or environment
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Google API key is required. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Extract language code from voice name if not provided
        if language_code is None and voice_name:
            # Voice names like "en-AU-Chirp-HD-O" start with language code
            language_code = "-".join(voice_name.split("-")[:2])

        # Set configuration
        self._voice_name = voice_name or os.getenv("GOOGLE_VOICE_ID", "en-AU-Chirp-HD-O")
        self._language_code = language_code or "en-AU"
        self._speaking_rate = speaking_rate
        self._pitch = pitch
        self._volume_gain_db = volume_gain_db
        self._sample_rate = sample_rate_hertz

        # Set the API key as an environment variable for the client
        os.environ["GOOGLE_API_KEY"] = self._api_key

        # Initialize the Text-to-Speech client
        try:
            self._client = texttospeech.TextToSpeechClient(
                client_options={"api_key": self._api_key}
            )
            logger.info(
                f"✅ Google TTS initialized with voice: {self._voice_name}, "
                f"language: {self._language_code}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google TTS client: {e}")
            raise

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "ChunkedStream":
        """
        Synthesize text to speech.

        Args:
            text: The text to synthesize

        Returns:
            ChunkedStream containing the synthesized audio
        """
        return ChunkedStream(
            tts=self,
            text=text,
            conn_options=conn_options,
        )


class ChunkedStream(tts.ChunkedStream):
    """Stream for Google TTS synthesis"""

    def __init__(
        self,
        *,
        tts: GoogleTTS,
        text: str,
        conn_options: APIConnectOptions,
    ):
        super().__init__(
            tts=tts,
            input_text=text,
            conn_options=conn_options,
        )
        self._tts = tts
        self._text = text

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """
        Run the synthesis and yield audio chunks.
        Google TTS doesn't support streaming, so we synthesize the entire text at once.
        """
        try:
            # Prepare the synthesis input
            synthesis_input = texttospeech.SynthesisInput(text=self._text)

            # Configure the voice parameters
            voice = texttospeech.VoiceSelectionParams(
                name=self._tts._voice_name,
                language_code=self._tts._language_code,
            )

            # Configure the audio output
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=self._tts._sample_rate,
                speaking_rate=self._tts._speaking_rate,
                pitch=self._tts._pitch,
                volume_gain_db=self._tts._volume_gain_db,
            )

            # Perform the text-to-speech request on a separate thread
            # to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._tts._client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config,
                ),
            )

            output_emitter.initialize(
                request_id=os.urandom(16).hex(),
                sample_rate=self._tts._sample_rate,
                num_channels=1,
                mime_type="audio/pcm",
                stream=False,
            )

            # The response's audio_content is binary audio data.
            # Push as a single PCM chunk because Google TTS here is non-streaming.
            if response.audio_content:
                output_emitter.push(response.audio_content)
                output_emitter.flush()

                logger.debug(
                    f"Synthesized {len(response.audio_content)} bytes of audio "
                    f"for text: {self._text[:50]}..."
                )

        except Exception as e:
            logger.exception(f"Error during Google TTS synthesis: {e}")
            raise
