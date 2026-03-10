import os
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

from livekit.api import LiveKitAPI
from livekit.api.sip_service import ListSIPInboundTrunkRequest

async def get_sip_trunk_uri():
    """Get the SIP URI for your LiveKit trunk"""
    lk_api = LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        response = await lk_api.sip.list_inbound_trunk(
            ListSIPInboundTrunkRequest()
        )
        
        trunks = response.items if hasattr(response, 'items') else []
        
        if not trunks:
            print("❌ No trunks found. Run trunk_creation.py first.")
            return

        for trunk in trunks:
            print("\n" + "=" * 70)
            print(f"📞 Trunk: {trunk.name}")
            print("=" * 70)
            print(f"Trunk ID: {trunk.sip_trunk_id}")
            print(f"Numbers: {trunk.numbers}")
            
            # Extract LiveKit domain from LIVEKIT_URL
            lk_url = os.environ["LIVEKIT_URL"]
            # Remove protocol (ws:// or wss://)
            domain = lk_url.replace("ws://", "").replace("wss://", "")
            # Remove port if present
            if ":" in domain:
                domain = domain.split(":")[0]
            
            # For self-hosted, the SIP URI format is:
            # sip:trunk-id@sip-domain:port
            sip_uri = f"sip:{trunk.sip_trunk_id}@{domain}:5060"
            
            print(f"\n⚠️  IMPORTANT: Update your SignalWire SWML script:")
            print(f"\nOLD (Incorrect):")
            print(f'  "to": "sip:+12013659231@13.50.173.79:5060;transport=udp"')
            print(f"\nNEW (Correct):")
            print(f'  "to": "{sip_uri}"')
            
            print(f"\n📋 Full SWML Script:")
            print("=" * 70)
            swml = f'''{{
  "version": "1.0.0",
  "sections": {{
    "main": [
      {{
        "connect": {{
          "to": "{sip_uri}"
        }}
      }}
    ]
  }}
}}'''
            print(swml)
            print("=" * 70)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    asyncio.run(get_sip_trunk_uri())
