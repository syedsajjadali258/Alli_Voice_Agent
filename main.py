from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import os
from uuid import uuid4
from livekit.api import AccessToken, VideoGrants, LiveKitAPI
from livekit.protocol import agent as proto_agent
from google.protobuf.json_format import MessageToDict
from dotenv import load_dotenv
from livekit import api
from livekit.api import access_token as atoken
from livekit.protocol import agent_dispatch as proto_agent

load_dotenv()

# LiveKit Configuration from environment variables
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
AGENT_NAME = os.getenv("AGENT_NAME")

app = FastAPI(
    title="Alli Voice Agent API",
    description="FastAPI base project for voice agent",
    version="1.0.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Test GET endpoint"""
    return {"message": "Hello, World!", "status": "success"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


class StartCallRequest(BaseModel):
    agent_id: str


@app.post("/start_call")
async def get_livekit_token(data: StartCallRequest):
    """
    Generate LiveKit token for joining a room and dispatch agent
    
    Returns:
        - token: JWT token for LiveKit
        - url: LiveKit server URL
        - roomName: Generated room name
        - participantId: Generated participant ID
        - dispatch: Agent dispatch information
    """
    try:
        agent_id = data.agent_id

        # Generate unique room and participant identifiers
        room_name = f"room-{agent_id}-{uuid4().hex[:8]}"
        participant_id = f"participant-{agent_id}-{uuid4().hex[:8]}"

        # Create LiveKit API client
        lk = LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET
        )

        # Create agent dispatch - This tells the worker to join this room
        dispatch_request = proto_agent.CreateAgentDispatchRequest(
            agent_name=AGENT_NAME,
            room=room_name,
            metadata=json.dumps({"client": "voice-agent", "agent_id": agent_id}),
        )
        created_dispatch = await lk.agent_dispatch.create_dispatch(dispatch_request)
        
        # Convert dispatch to dict for response
        dispatch_dict = MessageToDict(created_dispatch, preserving_proto_field_name=True)

        # Generate participant token
        token_builder = AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET
        )
        token_builder = token_builder.with_identity(participant_id)
        token_builder = token_builder.with_grants(
            VideoGrants(room_join=True, room=room_name)
        )
        token_builder = token_builder.with_metadata(
            json.dumps({"client": "voice-agent", "agent_id": agent_id})
        )
        jwt_token = token_builder.to_jwt()

        return {
            "status": "success",
            "message": "Token generated and agent dispatched successfully",
            "data": {
                "token": jwt_token,
                "url": LIVEKIT_URL,
                "roomName": room_name,
                "participantId": participant_id,
                "dispatch": dispatch_dict,
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate token: {str(e)}"
        }



@app.post("/start_call2")
async def get_token2(data: StartCallRequest):
    
    # Permission check
    
    user_id = "A"
    
    agent_id = data.agent_id

    # Create LiveKit API client
    lk = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)

    # Dynamic room and participant
    # room_name = f"room-{agent_id}"
    # participant_id = f"participant-{agent_id}"

    room_name = f"room-{agent_id}-{uuid4().hex[:8]}"
    participant_id = f"participant-{agent_id}-{uuid4().hex[:8]}"

    # Create dispatch
    req = proto_agent.CreateAgentDispatchRequest(
        agent_name=AGENT_NAME,
        room=room_name,
        metadata=json.dumps({"user_id": user_id, "agent_id": agent_id}),
    )
    created_dispatch = await lk.agent_dispatch.create_dispatch(req)

    # Convert to dict for JSON response
    created_dispatch_dict = MessageToDict(created_dispatch, preserving_proto_field_name=True)

    # Generate participant token
    token_builder = atoken.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
    token_builder = token_builder.with_identity(participant_id)
    token_builder = token_builder.with_grants(atoken.VideoGrants(room_join=True, room=room_name))
    token_builder = token_builder.with_metadata(json.dumps({"client": "playground", "role": "tester"}))
    jwt_token = token_builder.to_jwt()

    # Store in DB


    return {
        "status": "success",
        "message": "Token generated successfully & dispatched the agent",
        "data": {
            "token": jwt_token,
            "url": LIVEKIT_URL,
            "roomName": room_name,
            "participantId": participant_id,
            "dispatch": created_dispatch_dict
        }
    }
    



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info"
    )
