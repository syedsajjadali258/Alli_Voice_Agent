# livekit_inbound_worker_openai_deepgram.py
from __future__ import annotations

import asyncio
import logging
import os
import requests
import json
from datetime import datetime
from typing import Any
import re
from dotenv import load_dotenv

# LiveKit SDK imports
from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    JobProcess,
    function_tool,
    cli,
    WorkerOptions,
    RoomInputOptions,
    UserStateChangedEvent,
)
from livekit.agents import AgentServer
from livekit.plugins import deepgram, openai, silero, noise_cancellation, elevenlabs, inworld
from livekit import api as lk_api
from livekit.agents import get_job_context
import os
import asyncio
from whispey import LivekitObserve

# from livekit.plugins.turn_detector.english import EnglishModel

import random

load_dotenv(override=True)


# # Set the LiveKit credentials statically in the code
LIVEKIT_API_KEY = os.environ['LIVEKIT_API_KEY'] = 'APIoALHYwLCMgJh'
LIVEKIT_API_SECRET = os.environ['LIVEKIT_API_SECRET'] = '5XjgalUcAD9mr3ksUPGeiKJweJkqV93oSeRgiIPVu8YB'
LIVEKIT_URL= os.environ['LIVEKIT_URL'] = 'wss://tgs-g8ihpbv8.livekit.cloud'


whispey = LivekitObserve(
    # agent_id="34338a36-6c05-465c-a7c0-b7329299b82a",
    agent_id ="ea97bf57-288d-4151-b1db-fa3f81ece832",
    apikey=os.getenv("WHISPEY_API_KEY")
)


# -------------------------
# Logging
# -------------------------
logger = logging.getLogger("livekit-inbound-openai-deepgram")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(ch)

# -------------------------
# Helpers Function for Vicidial

# -------------------------

def _normalize_phone(raw: str | None) -> str | None:
    """Return normalized phone like +123456789 or digits-only string if no +."""
    if not raw:
        return None
    raw = str(raw).strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    return ("+" if has_plus else "") + digits


def _extract_phone_from_room_name(room_name: str | None) -> str | None:
    if not room_name:
        return None
    m = re.search(r"call__(\+?\d{6,15})_", room_name)
    if not m:
        return None
    return _normalize_phone(m.group(1))

# -------------------------
# -------------------------
@function_tool()
async def vicidial_hangup_call(vicidial_call_id: str | None = None) -> dict:
    """
    Ends the call by triggering a HANGUP stage via the VICIdial AGC API.
    Called automatically if the user remains silent after 3 re-engagement attempts.
    """
    import requests, urllib3, os
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    if not vicidial_call_id:
        return {"ok": False, "error": "Missing vicidial_call_id"}

    def _call_hangup():
        try:
            r = requests.post(
                "https://tranxglobal.com/agc/api.php",
                params={
                    "source": "test",
                    "user": os.getenv("VICIDIAL_USER", "6666"),
                    "pass": os.getenv("VICIDIAL_PASS", "M$_SbqCyber101"),
                    "agent_user": os.getenv("VICIDIAL_AGENT_USER", "414"),
                    "function": "ra_call_control",
                    "stage": "HANGUP",
                    "ingroup_choices": os.getenv("VICIDIAL_INGROUP", "HUMAN_CB"),
                    "value": vicidial_call_id,
                },
                timeout=10,
                verify=False,
            )
            r.raise_for_status()
            return {"ok": True, "status": r.status_code, "text": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return await asyncio.to_thread(_call_hangup)


@function_tool()
async def vicidial_transfer_and_send_lead() -> str:
    """
    1) Calls ra_call_control (agc/api.php) using vicidial_call_id (transfer).
    2) Calls vicidial/non_agent_api.php to update/send lead (lead_id, vendor_source_code, phone_number, comments).
       Comments are built from captured session metadata.
    Extraction of fields uses participant attributes, remote_participants, and job metadata fallbacks.
    NOTE: This implementation uses verify=False (insecure) for HTTPS to match your testing environment.
    """
    try:
        ctx = get_job_context()

        # --- Extract values (same robust logic you've been using) ---
        vicidial_call_id = None
        lead_id = None
        vendor_source_code = None
        phone_number = None

        agent = getattr(ctx.session, "_inbound_agent", None)

        # helper to read attrs dict safely
        def read_attrs(d, *keys):
            for k in keys:
                v = d.get(k)
                if v:
                    return v
            return None

        # 1) participant attributes
        if agent and getattr(agent, "participant", None):
            attrs = getattr(agent.participant, "attributes", {}) or {}
            logger.info("vicidial_transfer_and_send_lead: participant attrs: %s", attrs)

            vicidial_call_id = read_attrs(attrs, "vicidial_call_id", "X-VICIdial-value", "sip.h.x-vicidial-value")
            lead_id = read_attrs(attrs, "lead_id", "X-lead-id", "sip.h.x-vicidial-lead-id")
            vendor_source_code = read_attrs(attrs, "vendor_source_code", "X-vendor-source-code", "sip.h.x-vicidial-campaign-id")
            phone_number = read_attrs(attrs, "phone_number", "X-phone-number", "sip.phoneNumber", "sip.h.x-vicidial-phone-num")

        # 2) fallback: remote participants
        if not (vicidial_call_id and lead_id and phone_number):
            try:
                room_obj = getattr(ctx, "room", None)
                if room_obj:
                    for rp in getattr(room_obj, "remote_participants", {}).values():
                        rp_attrs = getattr(rp, "attributes", {}) or {}
                        if not rp_attrs:
                            continue
                        if not vicidial_call_id:
                            vicidial_call_id = read_attrs(rp_attrs, "vicidial_call_id", "X-VICIdial-value", "sip.h.x-vicidial-value")
                        if not lead_id:
                            lead_id = read_attrs(rp_attrs, "lead_id", "X-lead-id", "sip.h.x-vicidial-lead-id")
                        if not vendor_source_code:
                            vendor_source_code = read_attrs(rp_attrs, "vendor_source_code", "X-vendor-source-code", "sip.h.x-vicidial-campaign-id")
                        if not phone_number:
                            phone_number = read_attrs(rp_attrs, "phone_number", "X-phone-number", "sip.phoneNumber", "sip.h.x-vicidial-phone-num")
                        if vicidial_call_id and lead_id and phone_number:
                            break
            except Exception:
                logger.exception("vicidial_transfer_and_send_lead: error scanning remote_participants")

        # 3) fallback: job metadata
        if not (vicidial_call_id and (lead_id or phone_number)):
            try:
                raw_meta = getattr(ctx.job, "metadata", None)
                print(raw_meta, "********** raw_meta in vicidial_transfer_and_send_lead")
                if raw_meta:
                    meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                    print(meta, "********** raw_meta in vicidial_transfer_and_send_lead")
                    vicidial_call_id = vicidial_call_id or meta.get("vicidial_call_id") or meta.get("VICIdialCallId") or meta.get("value")
                    lead_id = lead_id or meta.get("lead_id")
                    vendor_source_code = vendor_source_code or meta.get("vendor_source_code")
                    phone_number = phone_number or meta.get("phone_number") or meta.get("C_Number") or meta.get("From")
                    logger.debug("vicidial_transfer_and_send_lead: job metadata used: %s", meta)
            except Exception:
                logger.exception("vicidial_transfer_and_send_lead: failed to parse job metadata")

        # 4) fetch session metadata (answers captured by the agent)
        session_meta = {}
        try:
            raw_meta = getattr(ctx.session, "metadata", {}) or {}
            print(raw_meta, "********** raw_meta")
            if isinstance(raw_meta, str):
                session_meta = json.loads(raw_meta)
            elif isinstance(raw_meta, dict):
                session_meta = raw_meta
            else:
                session_meta = json.loads(str(raw_meta))
        except Exception:
            logger.warning("vicidial_transfer_and_send_lead: could not parse ctx.session.metadata")
            session_meta = {}

        print(session_meta, "********** session_meta")
        # Build readable comment string for VICIdial
        comments_parts = []

        for key, val in session_meta.items():
            if val:
                comments_parts.append(f"{key.replace('_', ' ').title()}: {val}")
        comments_text = " | ".join(comments_parts) if comments_parts else "No additional comments"
        logger.info("vicidial_transfer_and_send_lead: built comments: %s", comments_text)

        # --- Logs ---
        print("=== Extracted VICIdial Fields ===")
        print(f"vicidial_call_id: {vicidial_call_id}")
        print(f"lead_id: {lead_id}")
        print(f"vendor_source_code: {vendor_source_code}")
        print(f"phone_number: {phone_number}")
        print(f"comments: {comments_text}")
        print("=================================")

        # --- Step A: AGC API transfer ---
        agc_result = {"ok": False, "error": "no vicidial_call_id"}
        if vicidial_call_id:
            def _call_agc():
                import requests, urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                try:
                    r = requests.post(
                        "https://tranxglobal.com/agc/api.php",
                        params={
                            "source": "test",
                            "user": os.getenv("VICIDIAL_USER", "6666"),
                            "pass": os.getenv("VICIDIAL_PASS", "M$_SbqCyber101"),
                            "agent_user": os.getenv("VICIDIAL_AGENT_USER", "414"),
                            "function": "ra_call_control",
                            "stage": "INGROUPTRANSFER",
                            "ingroup_choices": os.getenv("VICIDIAL_INGROUP", "HUMAN_CB"),
                            "value": vicidial_call_id,
                        },
                        timeout=10,
                        verify=False,
                    ) 
                    r.raise_for_status()
                    return {"ok": True, "status": r.status_code, "text": r.text}
                except Exception as e:
                    return {"ok": False, "error": str(e)}

            agc_result = await asyncio.to_thread(_call_agc)
            logger.info("vicidial_transfer_and_send_lead: agc result: %s", agc_result)

        # --- Step B: non_agent_api update lead ---
        lead_result = {"ok": False, "error": "missing lead_id or phone_number"}
        if lead_id and phone_number:
            def _call_non_agent():
                import requests, urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                try:
                    r = requests.post(
                        "https://tranxglobal.com/vicidial/non_agent_api.php",
                        params={
                            "source": "test",
                            "user": os.getenv("VICIDIAL_USER", "6666"),
                            "pass": os.getenv("VICIDIAL_PASS", "M$_SbqCyber101"),
                            "function": "update_lead",
                            "lead_id": lead_id,
                            "vendor_source_code": vendor_source_code or "",
                            "phone_number": phone_number,
                            "comments": comments_text,
                        },
                        timeout=10,
                        verify=False,
                    )
                    r.raise_for_status()
                    return {"ok": True, "status": r.status_code, "text": r.text}
                except Exception as e:
                    return {"ok": False, "error": str(e)}

            lead_result = await asyncio.to_thread(_call_non_agent)
            logger.info("vicidial_transfer_and_send_lead: non_agent result: %s", lead_result)

        # --- Build combined response summary ---
        parts = []
        if agc_result:
            parts.append(f"AGC_{'OK' if agc_result.get('ok') else 'ERR'}:{agc_result.get('status', agc_result.get('error'))}")
        if lead_result:
            parts.append(f"LEAD_{'OK' if lead_result.get('ok') else 'ERR'}:{lead_result.get('status', lead_result.get('error'))}")
        summary = " | ".join(parts)

        return f"✅ Completed operations. Summary: {summary}"

    except Exception as e:
        logger.exception("vicidial_transfer_and_send_lead: unhandled exception")
        return f"❌ Exception: {e}"


@function_tool()
async def set_session_metadata(
    coverage_status: str | None = None,
    coverage_expiring: str | None = None,
    mileage: str | None = None,
    vehicle_issues: str | None = None,
    address: str | None = None,
    modifications: str | None = None,
):
    """
    Store caller’s answers in the session metadata.
    Each parameter is optional; only provided fields will be stored.
    """
    ctx = get_job_context()
    meta = getattr(ctx.session, "metadata", {}) or {}

    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    updates = {
        "coverage_status": coverage_status,
        "coverage_expiring": coverage_expiring,
        "mileage": mileage,
        "vehicle_issues": vehicle_issues,
        "address": address,
        "modifications": modifications,
    }

    for k, v in updates.items():
        if v is not None:
            meta[k] = v

    ctx.session.metadata = meta
    return {"ok": True, "updated": updates}




@function_tool()
async def get_session_metadata() -> dict:
    """
    Returns the current session metadata (dict) for debugging/to show in the conversation.
    """
    try:
        ctx = get_job_context()
        existing = getattr(ctx.session, "metadata", {}) or {}
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except Exception:
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        return existing
    except Exception as e:
        logger.exception("get_session_metadata failed")
        return {"error": str(e)}


# -------------------------
# Agent class
# -------------------------
class InboundAgent(Agent):
    def __init__(self, *, customer_name: str = "Caller", dial_info: dict[str, Any] | None = None):
        instructions = (
            f"""
You are Cassidy, a vehicle insurance specialist who CALLED THE CUSTOMER to inform them about extended warranty eligibility. You initiated this call - they didn't reach out to you.

YOUR GOAL: Qualify them for coverage by asking key questions, then transfer to a specialist.

---

OPENING (Natural & Warm):
"Hi, is this [Name]? Hey, this is Cassidy from the vehicle processing department. How's it going today?"

[Wait for response, match their energy]

"Good to hear. I'm reaching out because your [Year/Make/Model if available] is currently eligible for extended warranty coverage, and I need to verify a few things real quick. Do you have a minute?"

---

CORE RULES:
- Stay conversational and human
- Vary your language - NEVER repeat the same redirect phrase
- Acknowledge what they say, then smoothly transition back
- Sound natural, not scripted
- **CRITICAL: If user says they don't own a vehicle or don't have a car, STOP IMMEDIATELY and follow the NO VEHICLE protocol below**
- **CRITICAL: If you detect an answering machine or voicemail system, call detected_answering_machine() tool AFTER hearing the full greeting**

---

VOICEMAIL DETECTION:
If you hear signs of an automated system such as:
- "You have reached the voicemail of..."
- "Please leave a message after the beep"
- "I'm not available right now..."
- Long pause followed by beep sound
- Generic robotic greeting

→ IMMEDIATELY call detected_answering_machine() tool AFTER the greeting finishes

DO NOT leave a message manually. The tool will handle it.

---

NO VEHICLE PROTOCOL:
If the user indicates they don't own a vehicle, don't have a car, or sold their vehicle:

1. Respond warmly: "Oh, I apologize for the confusion. It looks like we reached out in error. Thanks for letting me know, and sorry to have bothered you. Have a great day!"

2. IMMEDIATELY call set_session_metadata() with coverage_status="no_vehicle"

3. IMMEDIATELY call vicidial_hangup_call() to end the call

DO NOT ask any further questions. DO NOT try to salvage the conversation. Just apologize and hang up.

---

REDIRECT PHRASES (Rotate these, never repeat):
- "Anyway, [question]"
- "So [question]"
- "Quick question - [question]"
- "Let me ask you - [question]"
- "I'm curious - [question]"
- "Just need to know - [question]"
- "Before I forget - [question]"
- "One more thing - [question]"

NEVER say "But real quick" more than once per conversation.

---

QUALIFICATION FLOW (Stay on track):
1. **FIRST: Confirm they own a vehicle** - "Just to confirm, you do own a vehicle currently, right?"
   - If NO → Follow NO VEHICLE PROTOCOL above
   - If YES → Continue to question 2

2. "Do you currently have any extended warranty or service plan?"
3. (If yes) "Is it expiring soon?"
4. "What's the mileage on your vehicle right now?"
5. "Any check engine lights or fluid leaks?"
6. "Can you confirm your address?" (Skip if resistant)
7. "Have you made any major modifications?"

---

HANDLING OBJECTIONS:

"I don't have a vehicle" / "I don't own a car" / "I sold my car"
→ Follow NO VEHICLE PROTOCOL (apologize, set metadata, hangup)

"What's your name?"
→ "Oh sorry, should've said that upfront - I'm Cassidy with the vehicle processing department."

"How did you get my number?"
→ "You're in our system from previous inquiries or manufacturer records. We reach out when there's an eligibility update."

"Are you a robot?"
→ [Light tone] "Nah, I'm real. I get that question a lot though. Anyway, [next question]"

"Which company are you with?"
→ "I'm with the vehicle processing department - we work with multiple warranty providers."

"I'm not interested."
→ "I totally understand. This is about eligibility that won't last forever. Takes 2 minutes. Do you currently have any warranty?"

"I'm busy right now."
→ "No problem, super quick. Do you currently have any extended warranty?"

When they notice you're following a script:
→ "Yeah, I do have a few standard questions to cover - just to see if you qualify. [next question]"

After 2-3 deflections/refusals:
→ "I hear you. If anything changes, feel free to reach back out. Have a good one." [Call vicidial_hangup_call()]

---

DATA CAPTURE:
After EVERY customer response to a qualification question, IMMEDIATELY call:
set_session_metadata() with this structure:


  "coverage_status": "yes/no/declined/no_vehicle/voicemail",
  "coverage_expiring": "yes/no/n/a",
  "mileage": "number or declined",
  "vehicle_issues": "none/check engine light/leaks/declined",
  "address": "full address or declined",
  "modifications": "yes/no/declined"


---

AFTER QUALIFYING:
"Alright, based on what you've told me, you do qualify for some low-cost warranty options. What I'm gonna do is connect you with one of our coverage specialists who can walk you through the actual plans and pricing. Just stay on the line for a sec, okay?"

[Call vicidial_transfer_and_send_lead()]

---

HANGUP IMMEDIATELY (using vicidial_hangup_call) when:
1. User says they don't own a vehicle
2. Customer says: "goodbye," "bye," "I gotta go," "not interested" (after 2 attempts)
3. Customer is hostile/abusive
4. You've redirected 3 times and they won't engage

TRANSFER (using vicidial_transfer_and_send_lead) when:
1. All qualification questions are answered successfully
2. User qualifies for coverage

---

TONE:
- Friendly but purposeful
- "I called you because..." not "I'm here if you need..."
- Brief on deflections, persistent on qualification
- Match their energy but stay on mission
- **Be respectful and quick to apologize if you reached the wrong person**

  """
        )
        super().__init__(instructions=instructions, tools=[vicidial_hangup_call, vicidial_transfer_and_send_lead, set_session_metadata, get_session_metadata])

        self.customer_name = customer_name
        self.dial_info = dial_info or {}
        self.participant: rtc.RemoteParticipant | None = None

        # 🧠 Data memory for captured user answers
        self.user_data = {
            "coverage_status": None,
            "coverage_expiring": None,
            "mileage": None,
            "vehicle_issues": None,
            "address": None,
            "modifications": None,
        }

    @function_tool
    async def detected_answering_machine(self):
        """
        Call this tool if you have detected a voicemail system or answering machine,
        AFTER hearing the voicemail greeting or beep.
        """
        logger.info("[voicemail] Answering machine detected, leaving message and hanging up")
        
        try:
            # Leave a brief voicemail message
            await self.session.generate_reply(
                instructions="Leave a brief professional voicemail message: 'Hi, this is Cassidy from the Vehicle Processing Department regarding your vehicle warranty eligibility. I'll give you a call back another time. Thanks.'"
            )
            
            # Natural pause before hanging up
            await asyncio.sleep(0.5)
            
            # Save metadata indicating voicemail was reached
            await set_session_metadata(coverage_status="voicemail")
            
            # Get vicidial_call_id and hang up
            vicidial_call_id = None
            try:
                ctx = get_job_context()
                if hasattr(ctx, "session"):
                    agent = getattr(ctx.session, "_inbound_agent", None)
                    if agent and getattr(agent, "participant", None):
                        attrs = getattr(agent.participant, "attributes", {}) or {}
                        vicidial_call_id = attrs.get("vicidial_call_id") or attrs.get("X-VICIdial-value")
            except Exception:
                logger.exception("[voicemail] Failed to extract vicidial_call_id")
            
            if vicidial_call_id:
                result = await vicidial_hangup_call(vicidial_call_id)
                logger.info("[voicemail] Hangup result: %s", result)
            else:
                logger.warning("[voicemail] No vicidial_call_id found; hanging up session only")
            
            # Shutdown the session
            await self.session.shutdown()
            
        except Exception as e:
            logger.exception("[voicemail] Error in detected_answering_machine: %s", e)


    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

# -------------------------
# Prewarm function for AgentServer
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
            model="eleven_flash_v2",
            voice_id=voice_id
        )
        logger.info("✅ ElevenLabs TTS prewarmed (voice: %s)", voice_id)
    except Exception as e:
        logger.exception("❌ Failed to prewarm ElevenLabs TTS: %s", e)
    
    logger.info("🎉 Prewarm complete")

# -------------------------
# Create AgentServer with prewarm function
# -------------------------
server = AgentServer(setup_fnc=prewarm)

@server.rtc_session(agent_name=os.getenv("AGENT_NAME", "tgs2-agent"))
async def rtc_session_handler(ctx: JobContext):
    """RTC session handler - calls the main entrypoint function."""
    await entrypoint(ctx)

# -------------------------
# Entrypoint
# -------------------------
async def entrypoint(ctx: JobContext):
    """
    Inbound-only entrypoint:
      - Parses any job metadata (if dispatch populated it)
      - Starts AgentSession (Deepgram STT/TTS + OpenAI LLM)
      - Waits for inbound participant created by LiveKit (from Twilio Elastic SIP)
      - Attaches agent to participant, greets, and keeps session alive
      - On shutdown writes a transcript
    """
    logger.info("Entrypoint starting for room: %s", ctx.room.name)
    await ctx.connect()
    room_name = ctx.room.name

    # Parse metadata (if dispatch set it)
    dial_info: dict[str, Any] = {}
    try:
        raw_meta = getattr(ctx.job, "metadata", None)
        if raw_meta:
            if isinstance(raw_meta, str):
                dial_info = json.loads(raw_meta)
            elif isinstance(raw_meta, dict):
                dial_info = raw_meta
            else:
                dial_info = json.loads(str(raw_meta))
    except Exception:
        logger.exception("Failed to parse ctx.job.metadata; continuing without it")
        dial_info = {}

    phone_number = None

    if not phone_number or phone_number in (None, "Unknown"):
        m = re.search(r"call__(\+?\d{6,15})_", room_name or "")
        if m:
            phone_number = m.group(1)
            logger.info("Extracted phone number from room_name: %s", phone_number)

    customer_name = dial_info.get("C_Name", "Caller")
    # phone_number = dial_info.get("C_Number", "Unknown")
    phone_number = phone_number
    print("*********** customer_name AND phone_number:  ", customer_name, phone_number)

    ctx.customer_name = customer_name

    # -------------------------
    # AgentSession: Deepgram + OpenAI
    # -------------------------
    
    # Use prewarmed models from process userdata (loaded by prewarm function)
    logger.info("🔥 Loading models from prewarmed cache...")
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    stt = ctx.proc.userdata.get("stt") or deepgram.STT(model="nova-3")
    tts = ctx.proc.userdata.get("tts") or elevenlabs.TTS(
        model="eleven_flash_v2",
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "56AoDkrOh6qfVPDXZ7Pt")
    )
    logger.info("✅ Models loaded successfully")
    
    session = AgentSession(
        user_away_timeout=10.0,
        stt=stt,
        # llm=openai.LLM(
        #     model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        #     temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
        # ),
        llm=openai.LLM(
        model="openai/gpt-oss-120b:de-d058483d541a2bf3",
        api_key="sk_vjeS7FAstT0vKelTOQVQm6PnnLiK9k95_0-ADVTl7LI",
        base_url="https://api.novita.ai/dedicated/v1/openai",
        temperature=0.3,
        max_tokens=800,
        ),
        tts=tts,
        vad=vad,
        turn_detection=None
    )

    ctx.session = session

    # -------------------------
    # Inactivity detection (natural re-engagement)
    # -------------------------
    inactivity_task: asyncio.Task | None = None
    conversation_paused = {"value": False}

    async def user_presence_task():
        """Politely re-engage the user during silence, with varied prompts."""
        logger.info("[inactivity] User marked 'away' — starting user presence task.")
        try:
            conversation_paused["value"] = True
            session.llm_enabled = False  # 🚫 Pause scripted question flow

            reengagement_prompts = [
                "Hello? Are you still there?",
                "Just checking in — are you still with me?",
                "I want to make sure we’re still connected. Can you hear me okay?",
            ]

            for attempt in range(3):
                prompt = random.choice(reengagement_prompts)
                logger.info("[inactivity] Attempt %d: %s", attempt + 1, prompt)
                
                # Check if session is still running before trying to speak
                if not hasattr(session, '_agent_activity') or session._agent_activity is None:
                    logger.warning("[inactivity] Session ended during presence check. Exiting.")
                    return
                
                try:
                    await session.say(prompt)
                except RuntimeError as e:
                    logger.warning("[inactivity] Session no longer running: %s", e)
                    return
                    
                await asyncio.sleep(10)

                # if user came back mid-loop
                if not conversation_paused["value"]:
                    logger.info("[inactivity] User resumed during presence check. Exiting task.")
                    return

            logger.info("[inactivity] No response after multiple attempts. Ending call.")
            
            # Check if session is still running before final message
            try:
                await session.say("Since I haven't heard back, I'll go ahead and end this call. Goodbye.")
            except RuntimeError:
                logger.info("[inactivity] Session already closed, skipping goodbye message.")
            
            # await session.shutdown()
            try:
                # Try to find vicidial_call_id from session or metadata
                vicidial_call_id = None
                ctx = get_job_context()
                if hasattr(ctx, "session"):
                    agent = getattr(ctx.session, "_inbound_agent", None)
                    if agent and getattr(agent, "participant", None):
                        attrs = getattr(agent.participant, "attributes", {}) or {}
                        vicidial_call_id = attrs.get("vicidial_call_id") or attrs.get("X-VICIdial-value")

                if vicidial_call_id:
                    result = await vicidial_hangup_call(vicidial_call_id)
                    logger.info("[inactivity] Hangup triggered via VICIdial API: %s", result)
                else:
                    logger.warning("[inactivity] No vicidial_call_id found; skipping hangup.")
            except Exception:
                logger.exception("[inactivity] Failed to trigger VICIdial hangup")

            await session.shutdown()

        except asyncio.CancelledError:
            logger.info("[inactivity] Presence task cancelled — user became active again.")
        except Exception:
            logger.exception("[inactivity] Error in presence task.")
        finally:
            conversation_paused["value"] = False
            session.llm_enabled = True
            logger.info("[inactivity] Conversation resumed.")

    @session.on("user_state_changed")
    def _user_state_changed(ev: UserStateChangedEvent):
        """Triggered whenever user changes state (speaking, listening, away, etc.)."""
        nonlocal inactivity_task
        logger.info("[inactivity] user_state_changed -> %s", ev.new_state)

        if ev.new_state == "away":
            if inactivity_task is None or inactivity_task.done():
                inactivity_task = asyncio.create_task(user_presence_task())
            return

        # User is back — cancel inactivity timer and resume script
        if inactivity_task is not None:
            inactivity_task.cancel()
            inactivity_task = None

        conversation_paused["value"] = False
        session.llm_enabled = True
        logger.info("[inactivity] User returned — resuming conversation.")



    # Whispey integration: start session ID (if SDK available)
    # -------------------------
    whispey_session_id = None
    print(whispey_session_id, "********** whispey_session_id")
    try:
        if hasattr(whispey, "start_session"):
            # start_session may be synchronous or return an asyncio coroutine; handle both
            maybe = whispey.start_session(session, phone_number=phone_number)
            print("phone number is ",phone_number)
            if asyncio.iscoroutine(maybe):
                whispey_session_id = await maybe
            else:
                whispey_session_id = maybe
            logger.info("Whispey session started: %s", whispey_session_id)
        else:
            logger.info("Whispey SDK does not expose start_session; skipping start.")
    except Exception:
        logger.exception("Failed to start whispey session (continuing without observability)")

    # Export monitoring data when session ends
    async def whispey_shutdown():
        try:
            if whispey_session_id and hasattr(whispey, "export"):
                maybe = whispey.export(whispey_session_id)
                if asyncio.iscoroutine(maybe):
                    await maybe
                logger.info("Whispey export complete for session: %s", whispey_session_id)
        except Exception:
            logger.exception("Whispey export failed")

    ctx.add_shutdown_callback(whispey_shutdown)


    # Shutdown / transcript writer
    async def write_transcript():
        try:
            now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            os.makedirs("transcripts", exist_ok=True)
            fname = f"transcripts/transcript_{room_name}_{now}.json"
            data = {
                "room": room_name,
                "customer_name": customer_name,
                "phone_number": phone_number,
                "metadata": dial_info,
                "history": session.history.to_dict(),
            }
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved transcript to %s", fname)
        except Exception:
            logger.exception("Failed to write transcript")

    ctx.add_shutdown_callback(write_transcript)

    

    # Create agent and attach it to the session (safe; avoids JobContext property)
    agent = InboundAgent(customer_name=customer_name, dial_info=dial_info)
    # attach to session for tool access (use a unique name to avoid collisions)
    session._inbound_agent = agent

    # Start session early
    session_task = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony()
            ),
        )
    )


    await session_task
    logger.info("AgentSession started; waiting for inbound participant in room: %s", room_name)

    try:
        # Wait for the SIP caller participant LiveKit creates from Twilio
        participant = await ctx.wait_for_participant()
        logger.info("Inbound participant joined: %s", getattr(participant, "identity", "<no-identity>"))

        # attach participant
        agent.set_participant(participant)
        logger.info("✅ Attached SIP participant: %s, attrs=%s", getattr(participant, "identity", "<no-id>"), getattr(participant, "attributes", {}))


        # debug/log metadata and participant object
        logger.info("ctx.job.metadata: %s", getattr(ctx.job, "metadata", None))
        logger.info("participant repr: %r", participant)

        # greet user
        try:
            await session.say(f"Hello there! This is the Vehicle Processing Department. This call is in regards to your vehicle's extended insurance without inspection.")
        except Exception:
            logger.exception("Failed to say greeting")

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
    except Exception as e:
        logger.exception("Error handling inbound participant: %s", e)
    finally:
        logger.info("Entrypoint leaving for room: %s", room_name)

# -------------------------
# Worker bootstrap with AgentServer
# -------------------------
if __name__ == "__main__":
    # Run the agent server
    cli.run_app(server)
