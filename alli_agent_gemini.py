# alli_agent.py - Simplified LiveKit Voice Agent
from __future__ import annotations

import asyncio
import logging
import os
from dotenv import load_dotenv

# LiveKit SDK imports
from livekit import rtc
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    JobProcess,
    cli,
    WorkerOptions,
)
from livekit.plugins import deepgram, openai, silero  # elevenlabs

# Import custom Google TTS
from google_tts import GoogleTTS

load_dotenv(override=True)

# -------------------------
# Logging
# -------------------------
logger = logging.getLogger("alli-voice-agent")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(ch)

# -------------------------
# Agent class
# -------------------------
class AlliAgent(Agent):
    def __init__(self):
        instructions = """
You are Alli, a friendly and helpful conversational assistant.

Your personality:
- Warm, approachable, and patient
- Clear and concise in your responses
- Eager to help with any questions or tasks
- Professional yet personable

Guidelines:
- Listen carefully to what the user says
- Provide helpful, accurate responses
- Ask clarifying questions when needed
- Keep the conversation natural and flowing
- Be respectful and courteous at all times

Your goal is to have a pleasant conversation and assist the user with whatever they need.
"""
        super().__init__(instructions=instructions)

# -------------------------
# Prewarm function
# -------------------------
def prewarm(proc: JobProcess):
    """
    Prewarm function to load models before job assignment.
    This runs once per process to warm up models, improving performance.
    """
    logger.info("🔥 Prewarming process with models...")
    
    # Load and cache models in process userdata
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("✅ Silero VAD prewarmed")
    except Exception as e:
        logger.exception("❌ Failed to prewarm Silero VAD: %s", e)
    
    try:
        proc.userdata["stt"] = deepgram.STT(model="nova-3")
        logger.info("✅ Deepgram STT prewarmed")
    except Exception as e:
        logger.exception("❌ Failed to prewarm Deepgram STT: %s", e)
    
    # Google/Gemini TTS with Chirp HD voice
    try:
        voice_id = os.getenv("GOOGLE_VOICE_ID", "en-AU-Chirp-HD-O")
        api_key = os.getenv("GOOGLE_API_KEY")
        proc.userdata["tts"] = GoogleTTS(
            voice_name=voice_id,
            api_key=api_key,
            speaking_rate=1.0,  # Adjust speed if needed (0.25 to 4.0)
            pitch=0.0,          # Adjust pitch if needed (-20.0 to 20.0)
        )
        logger.info("✅ Google TTS prewarmed (voice: %s)", voice_id)
    except Exception as e:
        logger.exception("❌ Failed to prewarm Google TTS: %s", e)
    
    logger.info("🎉 Prewarm complete")



async def entrypoint(ctx: JobContext):
    logger.info("🚀 Entrypoint starting for room: %s", ctx.room.name)

    await ctx.connect()
    logger.info("✅ Connected to room")

    # Load prewarmed models
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    stt = ctx.proc.userdata.get("stt") or deepgram.STT(model="nova-3")
    tts = ctx.proc.userdata.get("tts") or GoogleTTS(
        voice_name=os.getenv("GOOGLE_VOICE_ID", "en-AU-Chirp-HD-O"),
        api_key=os.getenv("GOOGLE_API_KEY"),
    )

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        ),
        tts=tts,
        vad=vad,
    )

    # Start agent session (handles participants automatically)
    await session.start(
        agent=AlliAgent(),
        room=ctx.room,
    )

    # Greeting
    await session.say(
        "Hi! I'm Alli. How can I help you today?",
        allow_interruptions=True,
    )

    await asyncio.sleep(float("inf"))

# -------------------------
# Worker bootstrap
# -------------------------
if __name__ == "__main__":
    # Run the agent with worker options
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=os.getenv("AGENT_NAME"),
            # Enable auto-subscribe to all rooms
            # num_idle_processes=1,
            # load_threshold=0.95, 
            num_idle_processes=2,
            load_threshold=1.0, 
        )
    )
