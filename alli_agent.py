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
from livekit.plugins import deepgram, openai, silero, elevenlabs

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
    
    try:
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "56AoDkrOh6qfVPDXZ7Pt")
        proc.userdata["tts"] = elevenlabs.TTS(
            model="eleven_flash_v2_5",
            voice_id=voice_id
        )
        logger.info("✅ ElevenLabs TTS prewarmed (voice: %s)", voice_id)
    except Exception as e:
        logger.exception("❌ Failed to prewarm ElevenLabs TTS: %s", e)
    
    logger.info("🎉 Prewarm complete")

# -------------------------
# Entrypoint
# -------------------------
async def entrypoint(ctx: JobContext):
    """
    Main entrypoint for the voice agent:
      - Connects to the LiveKit room
      - Initializes AgentSession with Deepgram STT, OpenAI LLM, and ElevenLabs TTS
      - Waits for participant to join
      - Starts the conversation
    """
    logger.info("🚀 Entrypoint starting for room: %s", ctx.room.name)
    await ctx.connect()
    
    room_name = ctx.room.name
    logger.info("✅ Connected to room: %s", room_name)

    # -------------------------
    # AgentSession: Deepgram STT + OpenAI LLM + ElevenLabs TTS
    # -------------------------
    
    # Use prewarmed models from process userdata (loaded by prewarm function)
    logger.info("🔥 Loading models from prewarmed cache...")
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    stt = ctx.proc.userdata.get("stt") or deepgram.STT(model="nova-3")
    tts = ctx.proc.userdata.get("tts") or elevenlabs.TTS(
        model="eleven_flash_v2_5",
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "56AoDkrOh6qfVPDXZ7Pt")
    )
    logger.info("✅ Models loaded successfully")
    
    session = AgentSession(
        stt=stt,
        llm=openai.LLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        ),
        tts=tts,
        vad=vad,
    )

    ctx.session = session

    # Create agent instance
    agent = AlliAgent()
    
    # Start session
    logger.info("🎬 Starting agent session...")
    session_task = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
        )
    )

    await session_task
    logger.info("✅ AgentSession started; waiting for participant in room: %s", room_name)

    try:
        # Wait for participant to join the room
        participant = await ctx.wait_for_participant()
        logger.info("👤 Participant joined: %s", getattr(participant, "identity", "<no-identity>"))

        # Greet the user
        await session.say("Hi! I'm Alli. How can I help you today?", allow_interruptions=True)
        logger.info("💬 Greeted the participant")

        # Keep the session alive until the participant leaves or the session ends
        await asyncio.sleep(float('inf'))
        
    except asyncio.CancelledError:
        logger.info("Session cancelled")
    except Exception as e:
        logger.exception("Error during session: %s", e)
    finally:
        logger.info("👋 Entrypoint leaving for room: %s", room_name)

# -------------------------
# Worker bootstrap
# -------------------------
if __name__ == "__main__":
    # Run the agent with worker options
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=os.getenv("AGENT_NAME", "voice-agent"),
            # Enable auto-subscribe to all rooms
            num_idle_processes=1,
        )
    )
