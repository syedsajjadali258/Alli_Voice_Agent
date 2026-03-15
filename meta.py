import os
import asyncio
from dotenv import load_dotenv

from livekit import api

load_dotenv(override=True)


async def verify_dispatch_rule():

    rule_id = "SDR_Ym3s7TEdNLLo"

    livekit_api = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        print(f"\nFetching dispatch rule: {rule_id}\n")

        rules = await livekit_api.sip.list_sip_dispatch_rule(
            api.ListSIPDispatchRuleRequest()
        )

        found = False

        for rule in rules.items:

            if rule.sip_dispatch_rule_id == rule_id:
                found = True

                print("✅ Dispatch Rule Found\n")
                print("Rule ID:", rule.sip_dispatch_rule_id)
                print("Name:", rule.name)
                print("Metadata:", rule.metadata)

                print("\nAttributes:")
                for k, v in rule.attributes.items():
                    print(f"  {k} -> {v}")

                print("\nRule Type:", rule.rule)

        if not found:
            print("❌ Dispatch rule not found")

    except Exception as e:
        print("Error:", e)

    finally:
        await livekit_api.aclose()


if __name__ == "__main__":
    asyncio.run(verify_dispatch_rule())