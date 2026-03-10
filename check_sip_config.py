import os
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from livekit.api import LiveKitAPI
from livekit.api.sip_service import (
    ListSIPDispatchRuleRequest,
    ListSIPInboundTrunkRequest,
)

async def check_sip_config():
    """Check SIP trunk and dispatch configuration"""
    lk_api = LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        # List inbound trunks
        print("=" * 60)
        print("INBOUND TRUNKS")
        print("=" * 60)
        trunk_response = await lk_api.sip.list_inbound_trunk(
            ListSIPInboundTrunkRequest()
        )
        trunks = trunk_response.items if hasattr(trunk_response, 'items') else []
        
        if trunks:
            for trunk in trunks:
                print(f"\n📞 Trunk: {trunk.name}")
                print(f"   ID: {trunk.sip_trunk_id}")
                print(f"   Numbers: {trunk.numbers}")
                print(f"   Metadata: {trunk.metadata}")
                print(f"\n   ⚠️  SIP ENDPOINT INFO:")
                print(f"   To receive calls, configure your SIP provider to forward")
                print(f"   calls to LiveKit's SIP endpoint for trunk: {trunk.sip_trunk_id}")
        else:
            print("No trunks found.")

        # List dispatch rules
        print("\n" + "=" * 60)
        print("DISPATCH RULES")
        print("=" * 60)
        dispatch_response = await lk_api.sip.list_dispatch_rule(
            ListSIPDispatchRuleRequest()
        )
        dispatch_rules = dispatch_response.items if hasattr(dispatch_response, 'items') else []
        
        if dispatch_rules:
            for rule in dispatch_rules:
                print(f"\n🔀 Rule: {rule.name}")
                print(f"   ID: {rule.sip_dispatch_rule_id}")
                print(f"   Trunk IDs: {rule.trunk_ids}")
                print(f"   Metadata: {rule.metadata}")
                if hasattr(rule, 'rule') and rule.rule:
                    if hasattr(rule.rule, 'dispatch_rule_individual'):
                        individual = rule.rule.dispatch_rule_individual
                        if individual:
                            print(f"   Room Prefix: {individual.room_prefix}")
        else:
            print("No dispatch rules found.")

        print("\n" + "=" * 60)
        print(f"Agent Name: {os.getenv('AGENT_NAME', 'Not set')}")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    asyncio.run(check_sip_config())
