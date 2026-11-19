"""Work Machine: opt-in Mission Control plugin for Hermes Agent."""
from __future__ import annotations

import json

from .mission import MissionError, MissionStore
from .schemas import WORK_MACHINE_GOAL


def work_machine_goal(args: dict, **kwargs) -> str:
    """Hermes tool handler. State is scoped to a stable conversation ID."""
    try:
        if not isinstance(args, dict):
            raise MissionError("Tool input must be an object")
        owner = str(kwargs.get("conversation_id") or kwargs.get("session_id") or "")
        if not owner:
            raise MissionError("A conversation/session context is required")
        # Import the official profile-scoped storage only at tool invocation.
        from plugins.plugin_storage import plugin_data_dir

        store = MissionStore(plugin_data_dir("work-machine") / "missions.sqlite3")
        action = args.get("action")
        mid = args.get("mission_id")
        if action == "create":
            output = store.create(
                owner, args.get("title"), args.get("steps"),
                args.get("max_attempts", 20),
            )
        elif action == "list":
            output = store.list_missions(owner)
        elif action in {"status", "next", "complete_step", "fail_step", "finish", "cancel"}:
            if not isinstance(mid, str) or len(mid) != 32:
                raise MissionError("A valid mission_id is required")
            if action == "status":
                output = store.status(owner, mid)
            elif action == "next":
                output = store.next_step(owner, mid)
            elif action == "complete_step":
                output = store.complete_step(owner, mid, args.get("step_id"), args.get("evidence"))
            elif action == "fail_step":
                output = store.fail_step(owner, mid, args.get("step_id"), args.get("reason"))
            elif action == "finish":
                output = store.finish(owner, mid, args.get("review_note"))
            else:
                output = store.cancel(owner, mid)
        else:
            raise MissionError("Unknown action")
        return json.dumps({"ok": True, "result": output}, ensure_ascii=False)
    except (MissionError, TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception:
        # Avoid leaking file paths and other internal details to the model.
        return json.dumps({"ok": False, "error": "Mission store unavailable"})


def register(ctx) -> None:
    ctx.register_tool(
        name="work_machine_goal",
        toolset="work_machine",
        schema=WORK_MACHINE_GOAL,
        handler=work_machine_goal,
    )
