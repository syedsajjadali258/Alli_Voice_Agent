# import asyncio
# from livekit import api
# from livekit.protocol.sip import SIPHeaderOptions
# import os
# from dotenv import load_dotenv

# load_dotenv(override=True)

# async def main():
#     trunk_id = "ST_bbM2PaCoUbMg"
#     livekit_api = api.LiveKitAPI(
#         url=os.environ["LIVEKIT_URL"],
#         api_key=os.environ["LIVEKIT_API_KEY"],
#         api_secret=os.environ["LIVEKIT_API_SECRET"],
#     )

#     trunk = await livekit_api.sip.update_inbound_trunk_fields(
#         trunk_id=trunk_id,
#         include_headers=SIPHeaderOptions.SIP_X_HEADERS,  # value = 1, maps all X-* headers
#     )

#     print("Successfully updated trunk:")
#     print(trunk)
#     await livekit_api.aclose()

# asyncio.run(main())



import asyncio
from livekit import api
from livekit.protocol.sip import (
    SIPInboundTrunkInfo,
    SIPHeaderOptions,
    GetSIPInboundTrunkRequest,
)
import os
from dotenv import load_dotenv

load_dotenv(override=True)

async def main():
    trunk_id = "ST_xFrQyMmoMry9"
    livekit_api = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    # Step 1: fetch existing trunk to preserve all current fields
    response = await livekit_api.sip._client.request(
        "SIP",
        "GetSIPInboundTrunk",
        GetSIPInboundTrunkRequest(sip_trunk_id=trunk_id),
        livekit_api.sip._admin_headers(),
        api.GetSIPInboundTrunkResponse,
    )
    existing: SIPInboundTrunkInfo = response.trunk

    # Step 2: full replace, preserving fields + setting include_headers
    updated = await livekit_api.sip.update_inbound_trunk(
        trunk_id=trunk_id,
        trunk=SIPInboundTrunkInfo(
            name=existing.name,
            numbers=existing.numbers,
            allowed_addresses=existing.allowed_addresses,
            allowed_numbers=existing.allowed_numbers,
            auth_username=existing.auth_username,
            auth_password=existing.auth_password,
            metadata=existing.metadata,
            include_headers=SIPHeaderOptions.SIP_X_HEADERS,  # all X-* headers → sip.h.*
        ),
    )

    print("Successfully updated trunk:")
    print(updated)
    await livekit_api.aclose()

asyncio.run(main())