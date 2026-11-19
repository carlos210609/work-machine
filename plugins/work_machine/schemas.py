"""LLM-facing Work Machine mission tool schema."""
WORK_MACHINE_GOAL = {
    "name": "work_machine_goal",
    "description": (
        "Manage durable, bounded, auditable goal execution for multi-step work. "
        "First create a mission with explicit acceptance criteria. Then call next "
        "to obtain or resume a step, use the normal Hermes tools to do the work, "
        "and record concrete evidence using complete_step. Record failures with "
        "fail_step; attempts are bounded. Once all steps are done, call finish "
        "with a review note. This tool does NOT independently run or verify work."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "status", "next", "complete_step",
                         "fail_step", "finish", "cancel"],
            },
            "mission_id": {"type": "string", "description": "ID returned by create."},
            "title": {"type": "string", "description": "Goal title for create."},
            "steps": {
                "type": "array",
                "description": "Ordered plan for create, each with testable acceptance.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "acceptance": {"type": "string"},
                    },
                    "required": ["title", "acceptance"],
                },
            },
            "max_attempts": {
                "type": "integer",
                "description": "Max total step attempts, default 20, hard limit 100.",
            },
            "step_id": {"type": "integer", "description": "ID returned by next."},
            "evidence": {
                "type": "string",
                "description": "Concrete artifact path, test output or user-confirmed evidence.",
            },
            "reason": {"type": "string", "description": "Explanation for a failed step."},
            "review_note": {
                "type": "string",
                "description": "Final review noting verification performed and limitations.",
            },
        },
        "required": ["action"],
    },
}
