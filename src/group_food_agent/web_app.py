"""Same-origin ASGI application for the ORDERLY hackathon demo."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from .application import run_group_food_agent
from .config import load_project_dotenv
from .contracts import MealRequestCandidateV2
from .full_cli import FixtureInterpreter
from .multimodal import (
    ExistingFoodCreditV1,
    MultimodalContextV1,
    MultimodalMealRequestCandidateV1,
    MultimodalMealRequestInterpreter,
    ObservationEvidenceV1,
    SceneAnalysisV1,
    calculate_existing_food_credit,
    merge_multimodal_candidate,
    normalize_image,
    seeded_demo_history,
)
from .run_payload import build_run_payload
from .restaurant import load_live_restaurant_source, load_restaurant_source
from .service import PlanningService
from .validation import ValidationContextV2


MAX_REQUEST_BYTES = 10 * 1024 * 1024
RUN_TIMEOUT_SECONDS = 120
STATIC_DIR = Path(__file__).with_name("web_static")
RUN_LOCK = asyncio.Lock()

# Keep accepted uploads in RAM. The parser would otherwise spool files larger
# than 1 MiB to disk before our image normalizer can discard the raw bytes.
MultiPartParser.spool_max_size = MAX_REQUEST_BYTES + 1


class RequestBodyTooLarge(Exception):
    """Raised while streaming a request that exceeds the total body limit."""


class RequestGuardMiddleware:
    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                declared_length = int(raw_length)
            except ValueError:
                response = _error(400, "invalid_content_length", "Content-Length가 올바르지 않습니다.", "요청을 다시 전송해 주세요.")
                await response(scope, receive, send)
                return
            if declared_length > self.max_bytes:
                response = _error(413, "request_too_large", "요청이 10 MiB 제한을 초과했습니다.", "사진 크기를 줄인 뒤 다시 제출해 주세요.")
                await response(scope, receive, send)
                return
        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge
            return message

        await self.app(scope, limited_receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        async def guarded_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"content-security-policy", b"default-src 'self'; img-src 'self' blob: data:; connect-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, guarded_send)


def _event(event_type: str, stage: str, case_id: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "stage": stage,
        "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "case_id": case_id,
        "schema_version": "1.0",
        "detail": detail,
    }


def _error(status: int, code: str, reason: str, action: str) -> JSONResponse:
    return JSONResponse(
        {
            "status": "error",
            "error": {
                "code": code,
                "reason": reason,
                "corrective_action": action,
            },
        },
        status_code=status,
    )


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return parsed


def _offline_scene() -> SceneAnalysisV1:
    return SceneAnalysisV1(
        image_id="image:offline-reviewed-fixture",
        image_provided=True,
        visible_people=15,
        visible_people_confidence=1.0,
        visible_people_evidence=ObservationEvidenceV1(
            evidence_id="offline-visible-people",
            modality="application_context",
            status="explicit",
            confidence=1.0,
            note="Prepared, manually reviewed multimodal fixture; no live image call was made.",
        ),
        additional_people=0,
        explicit_total_people=15,
        existing_food=[],
        meal_context="dinner",
        meal_context_confidence=1.0,
        environment_label="준비된 단체 식사 데모",
        warnings=["simulated reviewed scene fixture"],
    )


async def _parse_request(request: Request) -> dict[str, Any]:
    length = request.headers.get("content-length")
    if length and int(length) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds the 10 MiB limit")
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("request exceeds the 10 MiB limit")
        data = json.loads(body or b"{}")
        return {
            "notes": data.get("text", ""),
            "run_mode": data.get("run_mode", "live"),
            "captured_at": data.get("captured_at"),
            "timezone_offset_minutes": data.get("timezone_offset_minutes", 0),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "location_permission": data.get("location_permission", "unavailable"),
            "photo": None,
        }
    if not (
        content_type.startswith("multipart/form-data")
        or content_type.startswith("application/x-www-form-urlencoded")
    ):
        raise ValueError("use application/json or form data")
    async with request.form(max_files=1, max_fields=8, max_part_size=8 * 1024 * 1024) as form:
        photo = form.get("photo")
        photo_bytes = await photo.read() if isinstance(photo, UploadFile) else None
        return {
            "notes": str(form.get("notes") or ""),
            "run_mode": str(form.get("run_mode") or "live"),
            "captured_at": str(form.get("captured_at") or "") or None,
            "timezone_offset_minutes": int(form.get("timezone_offset_minutes") or 0),
            "latitude": float(form["latitude"]) if form.get("latitude") not in (None, "") else None,
            "longitude": float(form["longitude"]) if form.get("longitude") not in (None, "") else None,
            "location_permission": str(form.get("location_permission") or "unavailable"),
            "photo": photo_bytes,
        }


async def _execute(data: dict[str, Any]) -> dict[str, Any]:
    notes = data["notes"]
    if not isinstance(notes, str):
        raise ValueError("text/notes must be a string")
    if len(notes) > 5_000:
        raise ValueError("notes exceed the 5,000 character limit")
    run_mode = data["run_mode"]
    if run_mode not in {"live", "offline_canonical"}:
        raise ValueError("run_mode must be live or offline_canonical")
    if not notes.strip() and not data["photo"] and run_mode != "offline_canonical":
        raise ValueError("provide a photo or special notes")

    request_id = f"request-{uuid4().hex}"
    case_id = f"case-{uuid4().hex}"
    context = ValidationContextV2(request_id=request_id, case_id=case_id)
    history = seeded_demo_history() if run_mode == "offline_canonical" else None
    app_context = MultimodalContextV1(
        captured_at=_parse_datetime(data["captured_at"]),
        timezone_offset_minutes=data["timezone_offset_minutes"],
        latitude=data["latitude"],
        longitude=data["longitude"],
        location_permission="granted" if data["latitude"] is not None else data["location_permission"],
        history=history,
    )
    multimodal_events: list[dict[str, Any]] = []
    scene: SceneAnalysisV1 | None = None
    credit: ExistingFoodCreditV1 | None = None
    conflicts: list[dict[str, Any]] = []
    interpreter: Any = None

    if run_mode == "offline_canonical":
        root = Path(__file__).resolve().parents[2]
        notes = (root / "fixtures" / "canonical_15_request.txt").read_text(encoding="utf-8")
        candidate = MealRequestCandidateV2.model_validate_json(
            (root / "fixtures" / "canonical_15_candidate.json").read_text(encoding="utf-8")
        )
        scene = _offline_scene()
        interpreter = FixtureInterpreter(candidate)
        multimodal_events.append(_event("stage_completed", "multimodal_interpreter", case_id, {
            "status": "prepared_fixture", "image_id": scene.image_id,
        }))
    elif data["photo"]:
        multimodal_events.append(_event("stage_started", "image_preflight", case_id, {
            "received_bytes": len(data["photo"]),
        }))
        image = normalize_image(data["photo"])
        multimodal_events.append(_event("stage_completed", "image_preflight", case_id, {
            "image_id": image.image_id, "width": image.width, "height": image.height,
            "normalized_media_type": image.media_type,
        }))
        multimodal_events.append(_event("agent_started", "multimodal_interpreter", case_id, {
            "output_type": "MultimodalMealRequestCandidateV1", "image_detail": "high",
        }))
        interpreted = await MultimodalMealRequestInterpreter().interpret(notes, image, app_context)
        if interpreted.scene_analysis.image_id != image.image_id:
            interpreted = interpreted.model_copy(
                update={"scene_analysis": interpreted.scene_analysis.model_copy(update={"image_id": image.image_id})}
            )
        scene = interpreted.scene_analysis
        conflicts = [item.model_dump(mode="json") for item in interpreted.conflict_resolutions]
        candidate = merge_multimodal_candidate(interpreted, app_context, raw_notes=notes)
        interpreter = FixtureInterpreter(candidate)
        multimodal_events.append(_event("agent_completed", "multimodal_interpreter", case_id, {
            "visible_people": scene.visible_people,
            "visible_people_confidence": scene.visible_people_confidence,
            "existing_food_observations": len(scene.existing_food),
        }))
        multimodal_events.append(_event("stage_completed", "multimodal_merge", case_id, {
            "conflict_resolutions": len(conflicts),
            "candidate_total_people": candidate.party.total_count,
            "total_count_evidence_ids": [
                evidence.evidence_id
                for evidence in candidate.evidence
                if evidence.field_path == "/party/total_count"
            ],
        }))

    planning_source = (
        load_restaurant_source()
        if run_mode == "offline_canonical"
        else load_live_restaurant_source()
    )
    if scene is not None:
        credit = calculate_existing_food_credit(
            scene,
            restaurant_source=planning_source,
            load_default_source=False,
        )
        multimodal_events.append(_event("stage_completed", "existing_food_normalization", case_id, {
            "credited_servings_milli": credit.total_credited_servings_milli,
            "protected_demand_credit_milli": 0,
            "policy": credit.policy,
        }))

    service = PlanningService(
        restaurant_source=planning_source,
        load_default_source=False,
        source_policy="demo" if run_mode == "offline_canonical" else "live",
        initial_existing_food_credits={
            case_id: credit.total_credited_servings_milli if credit else 0
        },
        initial_demand_multipliers={
            case_id: history.demand_multiplier_basis_points if history else 10_000
        },
    )
    trace_path = Path(__file__).resolve().parents[2] / ".traces" / f"{case_id}-{uuid4().hex[:8]}.jsonl"
    run = await run_group_food_agent(
        notes or "사진 기반 단체 식사 요청",
        context,
        interpreter=interpreter,
        service=service,
        live_planner=run_mode == "live",
        trace_file=trace_path,
    )
    payload = build_run_payload(
        run,
        public=True,
        additions={
            "scene_analysis": scene.model_dump(mode="json") if scene else None,
            "existing_food_credit": credit.model_dump(mode="json") if credit else None,
            "context_used": app_context.model_dump(mode="json"),
            "conflict_resolutions": conflicts,
        },
    )
    payload["pipeline_events"] = [*multimodal_events, *payload["pipeline_events"]]
    return payload


async def run_endpoint(request: Request) -> Response:
    if RUN_LOCK.locked():
        return _error(429, "agent_busy", "다른 주문 계산이 진행 중입니다.", "현재 실행이 끝난 뒤 다시 시도해 주세요.")
    try:
        data = await _parse_request(request)
    except RequestBodyTooLarge:
        return _error(413, "request_too_large", "요청이 10 MiB 제한을 초과했습니다.", "사진 크기를 줄인 뒤 다시 제출해 주세요.")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return _error(400, "invalid_request", str(exc), "사진과 특별사항 입력을 확인해 주세요.")
    async with RUN_LOCK:
        try:
            payload = await asyncio.wait_for(_execute(data), timeout=RUN_TIMEOUT_SECONDS)
            return JSONResponse(payload)
        except asyncio.TimeoutError:
            return _error(504, "run_timeout", "주문 계산이 제한 시간 안에 끝나지 않았습니다.", "잠시 후 다시 시도하거나 준비된 데모를 실행해 주세요.")
        except RuntimeError as exc:
            if "OPENAI_API_KEY" in str(exc):
                return _error(503, "configuration_required", "라이브 AI 설정이 필요합니다.", "서버의 OPENAI_API_KEY를 확인하거나 준비된 데모를 실행해 주세요.")
            return _error(500, "runtime_error", type(exc).__name__, "서버 로그를 확인해 주세요.")
        except ValueError as exc:
            return _error(400, "invalid_input", str(exc), "문제 필드를 수정한 뒤 다시 제출해 주세요.")
        except Exception as exc:  # no payload or secret leakage
            return _error(500, "unexpected_error", type(exc).__name__, "다시 시도하고 계속 실패하면 서버 로그를 확인해 주세요.")


async def index(_: Request) -> Response:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


async def asset(request: Request) -> Response:
    name = request.path_params["name"]
    if name not in {"app.css", "app.js"}:
        return Response(status_code=404)
    media_type = "text/css" if name.endswith(".css") else "text/javascript"
    return FileResponse(STATIC_DIR / name, media_type=media_type)


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "orderly-web"})


app = Starlette(
    routes=[
        Route("/", index),
        Route("/assets/{name}", asset),
        Route("/api/runs", run_endpoint, methods=["POST"]),
        Route("/health", health),
    ]
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestGuardMiddleware, max_bytes=MAX_REQUEST_BYTES)


def main() -> None:
    load_project_dotenv()
    import uvicorn

    uvicorn.run("group_food_agent.web_app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
