# Alli Voice Agent Setup

## Overview
This project contains a simplified LiveKit voice agent that connects to rooms and has conversations with users.

## Files
- `main.py` - FastAPI server for generating LiveKit tokens
- `alli_agent.py` - LiveKit voice agent worker
- `.env` - Environment configuration

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Update `.env` file with your API keys:
- `LIVEKIT_URL` - Your LiveKit server URL
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret
- `DEEPGRAM_API_KEY` - Deepgram API key (for speech-to-text)
- `ELEVENLABS_API_KEY` - ElevenLabs API key (for text-to-speech)
- `ELEVENLABS_VOICE_ID` - ElevenLabs voice ID (default: 56AoDkrOh6qfVPDXZ7Pt)
- `OPENAI_API_KEY` - OpenAI API key (for LLM)
- `AGENT_NAME` - Agent name (must be "voice-agent")

### 3. Run the FastAPI Server
```bash
python main.py
```
The API will be available at `http://localhost:8000`

### 4. Run the Voice Agent Worker
In a separate terminal:
```bash
python alli_agent.py dev
```

## Usage Flow

1. **Get Token**: Call `POST /start_call` with `agent_id` to get:
   - LiveKit token
   - WebSocket URL
   - Room name
   - Participant ID

2. **Connect**: Use the returned token and URL to connect to the LiveKit room from your client

3. **Talk**: The Alli agent will join the room and start a conversation

## API Endpoints

### POST /start_call
Generate LiveKit token and create agent dispatch.

**Request:**
```json
{
  "agent_id": "test-agent-1"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Token generated successfully",
  "data": {
    "token": "eyJhbGc...",
    "url": "wss://...",
    "roomName": "room-test-agent-1-a1b2c3d4",
    "participantId": "participant-test-agent-1-a1b2c3d4",
    "dispatch": {
      "id": "...",
      "agent_name": "voice-agent",
      "room": "room-test-agent-1-a1b2c3d4"
    }
  }
}
```

## Testing

1. Start both the FastAPI server and the agent worker
2. Call the `/start_call` endpoint to get credentials
3. Use a LiveKit client (web, mobile, or SDK) to join the room
4. The Alli agent will greet you and engage in conversation

## Features

- **Simple Architecture**: Minimal setup, no complex tools or integrations
- **Deepgram STT**: High-quality speech recognition
- **OpenAI LLM**: Natural language understanding and generation
- **ElevenLabs TTS**: Natural-sounding voice synthesis
- **Model Prewarming**: Faster response times with cached models
- **Easy Configuration**: All settings via environment variables
