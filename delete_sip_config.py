import os
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from livekit.api import LiveKitAPI
from livekit.api.sip_service import (
    ListSIPDispatchRuleRequest,
    ListSIPInboundTrunkRequest,
    DeleteSIPDispatchRuleRequest,
    DeleteSIPTrunkRequest,
)

async def delete_sip_config():
    """Delete existing SIP trunk and dispatch rules"""
    lk_api = LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        # List all dispatch rules
        print("Fetching dispatch rules...")
        dispatch_response = await lk_api.sip.list_dispatch_rule(
            ListSIPDispatchRuleRequest()
        )
        dispatch_rules = dispatch_response.items if hasattr(dispatch_response, 'items') else []
        
        if dispatch_rules:
            print(f"\nFound {len(dispatch_rules)} dispatch rule(s):")
            for rule in dispatch_rules:
                print(f"  - {rule.sip_dispatch_rule_id}: {rule.name}")
            
            # Delete each dispatch rule
            for rule in dispatch_rules:
                print(f"\nDeleting dispatch rule: {rule.sip_dispatch_rule_id} ({rule.name})")
                delete_req = DeleteSIPDispatchRuleRequest(
                    sip_dispatch_rule_id=rule.sip_dispatch_rule_id
                )
                await lk_api.sip.delete_dispatch_rule(delete_req)
                print("  ✅ Deleted")
        else:
            print("No dispatch rules found.")

        # List all inbound trunks
        print("\nFetching inbound trunks...")
        trunk_response = await lk_api.sip.list_inbound_trunk(
            ListSIPInboundTrunkRequest()
        )
        trunks = trunk_response.items if hasattr(trunk_response, 'items') else []
        
        if trunks:
            print(f"\nFound {len(trunks)} trunk(s):")
            for trunk in trunks:
                print(f"  - {trunk.sip_trunk_id}: {trunk.name} ({trunk.numbers})")
            
            # Delete each trunk
            for trunk in trunks:
                print(f"\nDeleting trunk: {trunk.sip_trunk_id} ({trunk.name})")
                delete_req = DeleteSIPTrunkRequest(
                    sip_trunk_id=trunk.sip_trunk_id
                )
                await lk_api.sip.delete_sip_trunk(delete_req)
                print("  ✅ Deleted")
        else:
            print("No trunks found.")
        
        print("\n✅ All SIP configurations deleted!")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    print("This will delete ALL SIP trunks and dispatch rules from your LiveKit project.")
    confirmation = input("Are you sure? Type 'yes' to continue: ")
    
    if confirmation.lower() == "yes":
        asyncio.run(delete_sip_config())
    else:
        print("Cancelled.")
