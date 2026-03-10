import os
import asyncio
import json
from dotenv import load_dotenv


load_dotenv(override=True)

from livekit.api import LiveKitAPI
from livekit.api.sip_service import (
    CreateSIPInboundTrunkRequest,
    CreateSIPDispatchRuleRequest,
)
from livekit.api import SIPInboundTrunkInfo, SIPDispatchRule, SIPDispatchRuleIndividual

async def create_sip_trunk_and_rule(phone_number: str, room_prefix: str = "call-"):
    # Initialize client
    lk_api = LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        # Create inbound trunk
        print(f"Creating inbound trunk for number: {phone_number} ...")
        trunk_req = CreateSIPInboundTrunkRequest(
            trunk=SIPInboundTrunkInfo(
                name=f"Inbound trunk {phone_number}",
                numbers=[phone_number],
            )
        )
        trunk_resp = await lk_api.sip.create_inbound_trunk(trunk_req)
        inbound_trunk = trunk_resp

        print("Inbound trunk created:")
        print(f"  ID           : {inbound_trunk.sip_trunk_id}")
        print(f"  Numbers      : {inbound_trunk.numbers}")
        print(f"  Name         : {inbound_trunk.name}")

        # Create dispatch rule
        print(f"\nCreating dispatch rule with prefix '{room_prefix}' ...")
        agent_name = os.environ.get("AGENT_NAME")
        
        # Add metadata to pin specific agent if AGENT_NAME is set
        metadata = {}
        if agent_name:
            metadata["agent_name"] = agent_name
        
        dispatch_req = CreateSIPDispatchRuleRequest(
            trunk_ids=[inbound_trunk.sip_trunk_id],
            rule=SIPDispatchRule(
                dispatch_rule_individual=SIPDispatchRuleIndividual(
                    room_prefix=room_prefix,
                )
            ),
            name=f"Dispatch for {phone_number}",
            metadata=json.dumps(metadata) if metadata else "",
        )
        dispatch_resp = await lk_api.sip.create_sip_dispatch_rule(dispatch_req)
        dispatch_rule = dispatch_resp

        print("Dispatch rule created:")
        print(f"  ID           : {dispatch_rule.sip_dispatch_rule_id}")
        print(f"  Name         : {dispatch_rule.name}")
        print(f"  Trunk IDs    : {dispatch_rule.trunk_ids}")
        print(f"  Room Prefix  : {room_prefix}")
        
        agent_name = os.environ.get("AGENT_NAME", "Not set")
        print(f"\n✅ Configuration complete!")
        print(f"  Phone Number : {phone_number}")
        print(f"  Agent Name   : {agent_name}")
        print(f"\nTo handle calls, start your agent with:")
        print(f"  python alli_agent.py start")
        return {
            "inbound_trunk": inbound_trunk,
            "dispatch_rule": dispatch_rule
        }

    except Exception as e:
        print("Error:", str(e))
        return None

    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    phone_number = input("Enter your phone number (E.164 format, e.g. +1234567890): ")
    asyncio.run(create_sip_trunk_and_rule(phone_number))
    