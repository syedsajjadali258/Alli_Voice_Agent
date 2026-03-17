import asyncio
import json
import os
from typing import Any, Iterable

from dotenv import load_dotenv
from fastapi import HTTPException
from livekit import api


load_dotenv(override=True)


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


LIVEKIT_URL = _env("LIVEKIT_URL")
LIVEKIT_API_KEY = _env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = _env("LIVEKIT_API_SECRET")
DEFAULT_AGENT_NAME = "AaaasadTrunk_agent123"


async def _sip_call(livekit_api: api.LiveKitAPI, *method_names: str, request: Any):
    last_exc: Exception | None = None
    for method_name in method_names:
        fn = getattr(livekit_api.sip, method_name, None)
        if not fn:
            continue

        # Different LiveKit python client versions expose different method signatures.
        # Some expect the request as a positional arg; others accept request=...
        try:
            return await fn(request)
        except TypeError as e:
            last_exc = e
            try:
                return await fn(request=request)
            except TypeError as e2:
                last_exc = e2
                continue

    if last_exc:
        raise last_exc
    raise AttributeError(
        "LiveKit SIP client missing methods: " + ", ".join(method_names)
    )


def _ensure_list(phone_numbers: Iterable[str]) -> list[str]:
    nums = [str(n).strip() for n in phone_numbers if str(n).strip()]
    if not nums:
        raise ValueError("phone_numbers must contain at least one non-empty number")
    return nums


# ----------------------------------------------------------------------
# HELPER FUNCTION: Create Inbound Trunk in LiveKit
# ----------------------------------------------------------------------
async def create_livekit_inbound_trunk(
    trunk_name: str,
    phone_numbers: Iterable[str],
    krisp_enabled: bool = True,
):
    """
    Creates an inbound SIP trunk in LiveKit.
    Returns the trunk_id from LiveKit.
    """
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        raise HTTPException(
            status_code=500, 
            detail="LiveKit credentials not configured"
        )
    
    livekit_api = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    try:
        trunk = api.SIPInboundTrunkInfo(
            name=trunk_name,
            numbers=_ensure_list(phone_numbers),
            krisp_enabled=krisp_enabled,
        )

        request = api.CreateSIPInboundTrunkRequest(trunk=trunk)

        trunk_info = await _sip_call(
            livekit_api,
            "create_inbound_trunk",
            "create_sip_inbound_trunk",
            request=request,
        )

        return trunk_info.sip_trunk_id
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create LiveKit inbound trunk: {str(e)}"
        )
    finally:
        await livekit_api.aclose()




# ----------------------------------------------------------------------
# HELPER FUNCTION: Create Dispatch Rule in LiveKit
# ----------------------------------------------------------------------
async def create_livekit_dispatch_rule(
    trunk_id: str,
    rule_name: str,
    room_prefix: str = "call-",
    agent_name: str | None = None,
    metadata: str | None = None,
):
    """
    Creates a dispatch rule for an inbound SIP trunk in LiveKit.
    Returns the dispatch_rule_id from LiveKit.
    """
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials not configured"
        )
    
    livekit_api = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    try:

        # Create dispatch rule to place each caller in a separate room
        rule = api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                room_prefix=room_prefix,
            )
        )

        resolved_agent_name = (agent_name or _env("AGENT_NAME") or DEFAULT_AGENT_NAME).strip()

        request_kwargs: dict[str, Any] = {
            "trunk_ids": [trunk_id],
            "rule": rule,
            "name": rule_name,
        }

        # Prefer modern room_config dispatch (pins worker agent) if available.
        room_config = None
        if resolved_agent_name and hasattr(api, "RoomConfiguration") and hasattr(api, "RoomAgentDispatch"):
            room_config = api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=resolved_agent_name,
                        metadata=metadata or "dispatch metadata",
                    )
                ]
            )
            request_kwargs["room_config"] = room_config
        else:
            md: dict[str, Any] = {}
            if resolved_agent_name:
                md["agent_name"] = resolved_agent_name
            if metadata:
                md["metadata"] = metadata
            request_kwargs["metadata"] = json.dumps(md) if md else ""

        request = api.CreateSIPDispatchRuleRequest(**request_kwargs)


        dispatch = await _sip_call(
            livekit_api,
            "create_sip_dispatch_rule",
            "create_dispatch_rule",
            request=request,
        )

        return dispatch.sip_dispatch_rule_id
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create LiveKit dispatch rule: {str(e)}"
        )
    finally:
        await livekit_api.aclose()


async def create_trunk_and_dispatch_rule(
    trunk_name: str,
    phone_numbers: Iterable[str],
    rule_name: str,
    room_prefix: str = "call-",
    agent_name: str | None = None,
    krisp_enabled: bool = True,
    metadata: str | None = None,
):
    trunk_id = await create_livekit_inbound_trunk(
        trunk_name=trunk_name,
        phone_numbers=phone_numbers,
        krisp_enabled=krisp_enabled,
    )
    dispatch_rule_id = await create_livekit_dispatch_rule(
        trunk_id=trunk_id,
        rule_name=rule_name,
        room_prefix=room_prefix,
        agent_name=agent_name,
        metadata=metadata,
    )
    return trunk_id, dispatch_rule_id


if __name__ == "__main__":
    trunk_name = input("Trunk name: ").strip() or "Inbound trunk"
    numbers_raw = input("Phone numbers (comma-separated, E.164): ").strip()
    phone_numbers = [n.strip() for n in numbers_raw.split(",") if n.strip()]
    rule_name = input("Dispatch rule name: ").strip() or "Dispatch rule"
    room_prefix = input("Room prefix [call-]: ").strip() or "call-"

    resolved_agent = _env("AGENT_NAME") or DEFAULT_AGENT_NAME
    print(f"Using agent_name: {resolved_agent}")

    trunk_id_out, dispatch_id_out = asyncio.run(
        create_trunk_and_dispatch_rule(
            trunk_name=trunk_name,
            phone_numbers=phone_numbers,
            rule_name=rule_name,
            room_prefix=room_prefix,
            agent_name=resolved_agent,
        )
    )
    print("Created trunk:", trunk_id_out)
    print("Created dispatch rule:", dispatch_id_out)


