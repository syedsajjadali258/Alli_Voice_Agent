import asyncio
import os

from livekit.api import LiveKitAPI
from livekit.api.sip_service import (
    ListSIPInboundTrunkRequest,
    ListSIPOutboundTrunkRequest,
    ListSIPDispatchRuleRequest,
)

async def fetch_sip_resources():
    # Initialize the LiveKit client
    lk_api = LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        # List inbound SIP trunks
        inbound_resp = await lk_api.sip.list_sip_inbound_trunk(
            ListSIPInboundTrunkRequest()
        )
        print("Inbound SIP Trunks:")
        for trunk in inbound_resp.items:
            print(f"  - ID: {trunk.sip_trunk_id}, Name: {trunk.name}, Numbers: {trunk.numbers}")

        # List outbound SIP trunks
        outbound_resp = await lk_api.sip.list_sip_outbound_trunk(
            ListSIPOutboundTrunkRequest()
        )
        print("Outbound SIP Trunks:")
        for trunk in outbound_resp.items:
            print(f"  - ID: {trunk.sip_trunk_id}, Name: {trunk.name}")

        # List dispatch rules
        dispatch_resp = await lk_api.sip.list_dispatch_rule(
            ListSIPDispatchRuleRequest()
        )
        print("Dispatch Rules:")
        for rule in dispatch_resp.items:
            print(f"  - ID: {rule.sip_dispatch_rule_id}, Name: {rule.name}, Trunks: {rule.trunk_ids}")

    except Exception as e:
        print("Error fetching SIP info:", str(e))

    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    asyncio.run(fetch_sip_resources())