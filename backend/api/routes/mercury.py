import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.schemas.mercury import MercuryRequest, MercuryResponse
from core.deps import get_mercury_service
from services.gateway.protocol_service import MercuryProtocolService

import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["mercury"])


@router.websocket("/ws/mercury")
async def mercury_gateway_ws(
    websocket: WebSocket, service: MercuryProtocolService = Depends(get_mercury_service)
):
    """Mercury Protocol Gateway WebSocket (v3).

    Ported from OpenClaw's unified control plane + node transport.
    """
    await websocket.accept()

    # 1. Send Handshake Challenge
    challenge = service.create_challenge()
    await websocket.send_text(challenge.model_dump_json())

    try:
        # 2. Main Loop
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                frame_type = data.get("type")

                if frame_type == "req":
                    req = MercuryRequest(**data)
                    if req.method == "connect":
                        resp = await service.handle_connect(req)
                        await websocket.send_text(resp.model_dump_json())
                    else:
                        # TODO: Handle other RPC methods (health, status, etc.)
                        resp = MercuryResponse(
                            id=req.id,
                            ok=False,
                            error={
                                "code": "METHOD_NOT_IMPLEMENTED",
                                "message": f"Method {req.method} not yet ported",
                            },
                        )
                        await websocket.send_text(resp.model_dump_json())

                elif frame_type == "res":
                    # Handle responses from the node (e.g. for node.invoke)
                    pass

                elif frame_type == "event":
                    # Handle events from the node
                    pass

            except json.JSONDecodeError:
                logger.warning("mercury_invalid_json")
                continue
            except Exception:
                logger.exception("mercury_frame_error")
                continue

    except WebSocketDisconnect:
        logger.info("mercury_websocket_disconnected")
    except Exception as e:
        logger.error("mercury_websocket_error", error=str(e))
    finally:
        # TODO: Cleanup session in service
        pass
