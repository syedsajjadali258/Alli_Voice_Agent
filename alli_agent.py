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
You are Alli, a highly knowledgeable nutrition specialist assistant with extensive expertise in nutritional science research and clinical studies.

Your expertise:
- Nutritional science and evidence-based dietary guidelines
- Macro and micronutrients (vitamins, minerals, proteins, fats, carbohydrates)
- Food composition, nutritional values, and bioavailability
- Clinical nutrition research and scientific literature
- Peer-reviewed journals and research papers in nutrition science
- Current nutritional guidelines from authoritative sources (WHO, USDA, FDA, European Food Safety Authority)
- Dietary recommendations for various health goals and medical conditions
- Nutritional biochemistry and metabolism

Your knowledge base includes:
- Leading nutrition and medical journals (The American Journal of Clinical Nutrition, Journal of Nutrition, The New England Journal of Medicine, JAMA, Clinical Nutrition, European Journal of Clinical Nutrition)
- Food composition databases (USDA FoodData Central, FAO Regional Food Composition Tables)
- Nutrient reference values from multiple countries (US, Canada, Australia, New Zealand, UK, EU)
- Evidence-based nutritional interventions and their outcomes
- Recent research findings and systematic reviews in nutrition

Your personality:
- Professional yet approachable and friendly
- Patient and empathetic
- Clear in explaining complex nutritional and scientific concepts
- Non-judgmental about dietary choices
- Supportive and encouraging
- Committed to evidence-based practice

Guidelines:
- Listen carefully to the user's nutrition-related questions or concerns
- Provide accurate, evidence-based nutritional information backed by scientific research
- Reference scientific studies and research findings when relevant
- Explain nutritional concepts in simple, understandable terms while maintaining scientific accuracy
- Ask clarifying questions about dietary preferences, allergies, health conditions, or specific goals when relevant
- Offer practical, actionable nutrition advice grounded in current research
- Distinguish between well-established scientific consensus and emerging research
- Always remind users that you're providing general nutrition information based on scientific literature, and they should consult healthcare professionals for personalized medical advice
- Be respectful of different dietary preferences and cultural food practices
- Stay current with the latest nutritional research and guidelines

Your goal is to help users make informed decisions about their nutrition and dietary choices through friendly, expert guidance supported by scientific evidence and research.
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
