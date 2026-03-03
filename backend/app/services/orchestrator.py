"""Sprint Orchestrator - Agentic coach that guides users through sprint lifecycle.

This orchestrator provides intelligent, context-aware guidance through:
1. Pre-sprint: Clarify vague tasks, generate microsteps, pick best next action
2. Active sprint: Monitor and respond to distractions/blocks
3. Post-sprint: Auto-write reflection, propose next sprint

Key principles:
- Bounded: Only acts within the app (no external actions)
- Conversational: Max 2 clarifying questions
- Action-oriented: Always suggests single best next step
- Data-driven: Uses sprint history for personalization
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint
from app.db.models.sprint_reflection import SprintReflection
from app.db.models.task import Task
from app.services.llm import LLMError, _chat_completion_json
from app.services.sprints import get_recent_sprint_stats

logger = logging.getLogger(__name__)


class OrchestratorPhase(str, Enum):
    """Sprint orchestrator lifecycle phases."""

    PRE_SPRINT = "pre_sprint"
    ACTIVE_SPRINT = "active_sprint"
    POST_SPRINT = "post_sprint"


class OrchestratorAction(str, Enum):
    """Actions the orchestrator can recommend."""

    ASK_CLARIFICATION = "ask_clarification"
    GENERATE_MICROSTEPS = "generate_microsteps"
    SUGGEST_NEXT_ACTION = "suggest_next_action"
    HANDLE_DISTRACTION = "handle_distraction"
    HANDLE_BLOCKER = "handle_blocker"
    WRITE_REFLECTION = "write_reflection"
    PROPOSE_NEXT_SPRINT = "propose_next_sprint"


async def _get_user_context(*, db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    """Get user's sprint history and patterns for personalization."""
    stats = await get_recent_sprint_stats(db=db, user_id=user_id, days=30)
    
    # Get recent sprints for pattern analysis
    recent_sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id)
        .order_by(Sprint.started_at.desc())
        .limit(10)
    )
    recent_sprints = list(recent_sprints_result.scalars().all())
    
    # Get reflections for those sprints
    sprint_ids = [s.id for s in recent_sprints]
    reflections_result = await db.execute(
        select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint = {r.sprint_id: r for r in reflections}
    
    return {
        "total_sprints": stats.get("total_sprints", 0),
        "completion_rate": stats.get("completion_rate", 0.0),
        "avg_duration": stats.get("avg_duration_minutes", 25),
        "distraction_rate": stats.get("distraction_rate", 0.0),
        "recent_outcomes": [
            {
                "outcome": reflection_by_sprint[s.id].outcome if s.id in reflection_by_sprint else None,
                "duration": s.duration_minutes,
            }
            for s in recent_sprints[:5]
        ],
    }


async def analyze_task_clarity(*, task_title: str, context: str | None) -> dict[str, Any]:
    """Analyze if a task needs clarification before starting sprint.
    
    Returns:
        {
            "needs_clarification": bool,
            "questions": list[str],  # Max 2 questions
            "reasoning": str
        }
    """
    system = (
        "You are a productivity coach analyzing if a task is clear enough to start working on. "
        "A task needs clarification if it's vague, too broad, or missing key information. "
        "If clarification is needed, ask 1-2 specific questions that will help break it down. "
        "Output JSON: {\"needs_clarification\": bool, \"questions\": [str], \"reasoning\": str}"
    )
    
    user = f"Task: {task_title}\n"
    if context:
        user += f"Context: {context}\n"
    user += (
        "Analyze if this task is clear enough to start a focused 10-25 minute sprint. "
        "If not, what 1-2 questions would help clarify it?"
    )
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            return {"needs_clarification": False, "questions": [], "reasoning": "Task seems clear"}
        
        return {
            "needs_clarification": result.get("needs_clarification", False),
            "questions": result.get("questions", [])[:2],  # Max 2 questions
            "reasoning": result.get("reasoning", ""),
        }
    except (LLMError, Exception) as e:
        logger.warning("Task clarity analysis failed: %s", e)
        return {"needs_clarification": False, "questions": [], "reasoning": "Analysis unavailable"}


async def pick_best_next_action(
    *, task_title: str, microsteps: list[str], user_context: dict[str, Any]
) -> dict[str, Any]:
    """Pick the single best microstep to start with based on user patterns.
    
    Returns:
        {
            "recommended_step": str,
            "reasoning": str,
            "estimated_minutes": int
        }
    """
    system = (
        "You are a productivity coach picking the best first action for a sprint. "
        "Consider the user's patterns and pick the easiest, most concrete step to build momentum. "
        "Output JSON: {\"recommended_step\": str, \"reasoning\": str, \"estimated_minutes\": int}"
    )
    
    user = f"Task: {task_title}\n"
    user += f"Available microsteps:\n"
    for i, step in enumerate(microsteps, 1):
        user += f"{i}. {step}\n"
    
    user += f"\nUser patterns:\n"
    user += f"- Completion rate: {user_context.get('completion_rate', 0):.0%}\n"
    user += f"- Distraction rate: {user_context.get('distraction_rate', 0):.0%}\n"
    user += f"- Typical sprint: {user_context.get('avg_duration', 25)} min\n"
    
    user += "\nPick the single best step to start with (usually the easiest/most concrete)."
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            # Fallback: pick first step
            return {
                "recommended_step": microsteps[0] if microsteps else "Start working",
                "reasoning": "First step is usually a good starting point",
                "estimated_minutes": 5,
            }
        
        return {
            "recommended_step": result.get("recommended_step", microsteps[0] if microsteps else "Start"),
            "reasoning": result.get("reasoning", ""),
            "estimated_minutes": result.get("estimated_minutes", 5),
        }
    except (LLMError, Exception) as e:
        logger.warning("Next action selection failed: %s", e)
        return {
            "recommended_step": microsteps[0] if microsteps else "Start working",
            "reasoning": "Begin with the first step",
            "estimated_minutes": 5,
        }


async def triage_distraction(*, distraction_note: str, task_title: str) -> dict[str, Any]:
    """Classify distraction and suggest minimal recovery action.
    
    Returns:
        {
            "urgency": "urgent" | "quick_fix" | "later" | "ignore",
            "action": str,  # Smallest action to handle it
            "reasoning": str
        }
    """
    system = (
        "You are a productivity coach triaging a distraction during a focused sprint. "
        "Classify urgency and suggest the SMALLEST action to handle it without derailing the sprint. "
        "Output JSON: {\"urgency\": str, \"action\": str, \"reasoning\": str}"
    )
    
    user = f"Current task: {task_title}\n"
    user += f"Distraction: {distraction_note}\n"
    user += (
        "Classify urgency (urgent/quick_fix/later/ignore) and suggest minimal action. "
        "Examples: 'Add to parking lot', 'Send 1-sentence reply', 'Close tab and return to X'"
    )
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            return {
                "urgency": "later",
                "action": "Add to parking lot and return to task",
                "reasoning": "Handle after sprint",
            }
        
        return {
            "urgency": result.get("urgency", "later"),
            "action": result.get("action", "Note it and continue"),
            "reasoning": result.get("reasoning", ""),
        }
    except (LLMError, Exception) as e:
        logger.warning("Distraction triage failed: %s", e)
        return {
            "urgency": "later",
            "action": "Add to parking lot and return to task",
            "reasoning": "Handle after sprint",
        }


async def generate_reflection(
    *,
    task_title: str,
    duration_minutes: int,
    distractions: list[str],
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """Auto-generate sprint reflection based on what happened.
    
    Returns:
        {
            "outcome": "done" | "blocked" | "distracted",
            "reason": str,
            "next_step": str
        }
    """
    system = (
        "You are a productivity coach writing a sprint reflection. "
        "Analyze what happened and suggest a concrete next step. "
        "Output JSON: {\"outcome\": str, \"reason\": str, \"next_step\": str}"
    )
    
    user = f"Task: {task_title}\n"
    user += f"Sprint duration: {duration_minutes} min\n"
    user += f"Distractions logged: {len(distractions)}\n"
    if distractions:
        user += "Distraction notes:\n"
        for d in distractions[:3]:  # Max 3
            user += f"- {d}\n"
    
    user += f"\nUser patterns:\n"
    user += f"- Typical completion rate: {user_context.get('completion_rate', 0):.0%}\n"
    
    user += (
        "\nSuggest outcome (done/blocked/distracted), brief reason, and concrete next step. "
        "Be encouraging but honest."
    )
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            return {
                "outcome": "distracted" if len(distractions) > 2 else "done",
                "reason": "Sprint completed",
                "next_step": "Continue with next microstep",
            }
        
        return {
            "outcome": result.get("outcome", "done"),
            "reason": result.get("reason", "Sprint completed"),
            "next_step": result.get("next_step", "Continue"),
        }
    except (LLMError, Exception) as e:
        logger.warning("Reflection generation failed: %s", e)
        return {
            "outcome": "done",
            "reason": "Sprint completed",
            "next_step": "Continue with next step",
        }


async def propose_next_sprint(
    *,
    db: AsyncSession,
    user_id: UUID,
    current_task_id: UUID | None,
    last_reflection: dict[str, Any],
) -> dict[str, Any]:
    """Propose what to work on next based on reflection and user patterns.
    
    Returns:
        {
            "task_id": UUID | None,
            "task_title": str,
            "reasoning": str,
            "suggested_duration": int
        }
    """
    user_context = await _get_user_context(db=db, user_id=user_id)
    
    # Get current task if provided
    current_task_title = "Unknown"
    if current_task_id:
        task_result = await db.execute(select(Task).where(Task.id == current_task_id))
        task = task_result.scalar_one_or_none()
        if task:
            current_task_title = task.title
    
    # Get other open tasks
    tasks_result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.archived_at.is_(None), Task.completed_at.is_(None))
        .order_by(Task.created_at.desc())
        .limit(5)
    )
    open_tasks = list(tasks_result.scalars().all())
    
    system = (
        "You are a productivity coach suggesting what to work on next after a sprint. "
        "Consider the last reflection and user patterns. "
        "Output JSON: {\"continue_current\": bool, \"reasoning\": str, \"suggested_duration\": int}"
    )
    
    user = f"Last sprint task: {current_task_title}\n"
    user += f"Last outcome: {last_reflection.get('outcome', 'unknown')}\n"
    user += f"Last reflection: {last_reflection.get('reason', '')}\n"
    
    if open_tasks:
        user += f"\nOther open tasks:\n"
        for t in open_tasks[:3]:
            user += f"- {t.title}\n"
    
    user += f"\nUser patterns:\n"
    user += f"- Completion rate: {user_context.get('completion_rate', 0):.0%}\n"
    user += f"- Avg sprint: {user_context.get('avg_duration', 25)} min\n"
    
    user += "\nShould they continue the current task or switch? Suggest sprint duration (10-25 min)."
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            return {
                "task_id": current_task_id,
                "task_title": current_task_title,
                "reasoning": "Continue with current task",
                "suggested_duration": 25,
            }
        
        continue_current = result.get("continue_current", True)
        
        return {
            "task_id": current_task_id if continue_current else None,
            "task_title": current_task_title if continue_current else "Choose a task",
            "reasoning": result.get("reasoning", ""),
            "suggested_duration": result.get("suggested_duration", 25),
        }
    except (LLMError, Exception) as e:
        logger.warning("Next sprint proposal failed: %s", e)
        return {
            "task_id": current_task_id,
            "task_title": current_task_title,
            "reasoning": "Continue with current task",
            "suggested_duration": 25,
        }
