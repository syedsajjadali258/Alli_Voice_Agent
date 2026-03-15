import os
import asyncio
from dotenv import load_dotenv

from livekit import api

load_dotenv(override=True)


async def update_dispatch_rule():

    rule_id = "SDR_Ym3s7TEdNLLo"

    attributes = {
        "caller_number": "{{from}}",
        "called_number": "{{to}}",
        "caller_name": "{{caller_name}}",
        "vicidial_call_id": "{{X-VICIdial-value}}",
        "lead_id": "{{sip.h.x-vicidial-lead-id}}",
        "campaign_id": "{{sip.h.x-vicidial-campaign-id}}",
        "phone_number": "{{sip.h.x-vicidial-phone-num}}",
    }

    livekit_api = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        print("Updating dispatch rule:", rule_id)
        print("Attributes:", attributes)

        result = await livekit_api.sip.update_sip_dispatch_rule_fields(
            rule_id=rule_id,
            attributes=attributes
        )

        print("\n✅ Successfully updated dispatch rule")
        print("Rule ID:", result.sip_dispatch_rule_id)
        print("Attributes:", dict(result.attributes))

    except api.twirp_client.TwirpError as e:
        print(f"{e.code} error: {e.message}")

    finally:
        await livekit_api.aclose()


if __name__ == "__main__":
    asyncio.run(update_dispatch_rule())