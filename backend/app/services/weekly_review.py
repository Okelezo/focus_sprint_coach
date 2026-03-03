"""Weekly Review Agent - Retention booster with pattern analysis and experiments.

Features:
1. Weekly pattern summary
2. Suggest 1 experiment for next week
3. Generate shareable stats
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint
from app.db.models.sprint_event import SprintEvent, SprintEventType
from app.db.models.sprint_reflection import SprintReflection
from app.db.models.task import Task
from app.services.llm import LLMError, _chat_completion_json

logger = logging.getLogger(__name__)


async def generate_weekly_summary(*, db: AsyncSession, user_id: UUID, week_offset: int = 0) -> dict:
    """Generate comprehensive weekly summary with patterns and insights.
    
    Args:
        week_offset: 0 for current week, -1 for last week, etc.
    
    Returns:
        {
            "week_start": str,
            "week_end": str,
            "total_sprints": int,
            "total_minutes": int,
            "completion_rate": float,
            "top_outcomes": dict,
            "distraction_count": int,
            "most_productive_day": str,
            "task_breakdown": dict,
            "patterns": list[str],
            "shareable_stat": str
        }
    """
    # Calculate week boundaries
    # week_offset:
    # -  0 = current week (starting Monday)
    # - -1 = last week
    # - +1 = next week
    now = datetime.now(timezone.utc)
    current_week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start = current_week_start + timedelta(days=7 * week_offset)
    week_end = week_start + timedelta(days=7)
    
    # Get sprints in week
    sprints_result = await db.execute(
        select(Sprint)
        .where(
            Sprint.user_id == user_id,
            Sprint.started_at >= week_start,
            Sprint.started_at < week_end,
        )
        .order_by(Sprint.started_at.asc())
    )
    sprints = list(sprints_result.scalars().all())
    
    if not sprints:
        return {
            "week_start": week_start.date().isoformat(),
            "week_end": week_end.date().isoformat(),
            "total_sprints": 0,
            "total_minutes": 0,
            "completion_rate": 0.0,
            "top_outcomes": {},
            "distraction_count": 0,
            "most_productive_day": "N/A",
            "task_breakdown": {},
            "patterns": ["No sprints this week - time to get started!"],
            "shareable_stat": "🎯 Ready to start your first sprint!",
        }
    
    # Get reflections
    sprint_ids = [s.id for s in sprints]
    reflections_result = await db.execute(
        select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint = {r.sprint_id: r for r in reflections}
    
    # Get distraction events
    events_result = await db.execute(
        select(SprintEvent)
        .where(
            SprintEvent.sprint_id.in_(sprint_ids),
            SprintEvent.type == SprintEventType.distraction.value,
        )
    )
    distraction_events = list(events_result.scalars().all())
    
    # Get tasks
    task_ids = [s.task_id for s in sprints if s.task_id]
    if task_ids:
        tasks_result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
        tasks = list(tasks_result.scalars().all())
        task_by_id = {t.id: t for t in tasks}
    else:
        task_by_id = {}
    
    # Calculate stats
    total_sprints = len(sprints)
    total_minutes = sum(s.duration_minutes for s in sprints)
    
    # Outcome breakdown
    outcomes = {}
    for sprint in sprints:
        if sprint.id in reflection_by_sprint:
            outcome = reflection_by_sprint[sprint.id].outcome
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    
    completion_rate = outcomes.get("done", 0) / total_sprints if total_sprints > 0 else 0.0
    
    # Day-of-week analysis
    day_stats = {}
    for sprint in sprints:
        day_name = sprint.started_at.strftime("%A")
        if day_name not in day_stats:
            day_stats[day_name] = {"total": 0, "completed": 0}
        day_stats[day_name]["total"] += 1
        if sprint.id in reflection_by_sprint and reflection_by_sprint[sprint.id].outcome == "done":
            day_stats[day_name]["completed"] += 1
    
    # Find most productive day
    most_productive_day = "N/A"
    if day_stats:
        best_day = max(
            day_stats.items(),
            key=lambda x: (x[1]["completed"] / x[1]["total"] if x[1]["total"] > 0 else 0, x[1]["total"]),
        )
        most_productive_day = f"{best_day[0]} ({best_day[1]['completed']}/{best_day[1]['total']} done)"
    
    # Task breakdown
    task_breakdown = {}
    for sprint in sprints:
        if sprint.task_id and sprint.task_id in task_by_id:
            task_title = task_by_id[sprint.task_id].title
            task_breakdown[task_title] = task_breakdown.get(task_title, 0) + 1
    
    # Identify patterns
    patterns = []
    
    if completion_rate >= 0.7:
        patterns.append(f"🔥 Strong week! {completion_rate:.0%} completion rate")
    elif completion_rate < 0.4:
        patterns.append(f"⚠️ Struggled this week - only {completion_rate:.0%} completion")
    
    if len(distraction_events) > total_sprints * 0.5:
        patterns.append(f"📱 High distraction week - {len(distraction_events)} interruptions logged")
    
    if outcomes.get("blocked", 0) >= 3:
        patterns.append(f"🚧 Hit blockers {outcomes['blocked']} times - tasks might be too complex")
    
    # Most worked-on task
    if task_breakdown:
        top_task = max(task_breakdown.items(), key=lambda x: x[1])
        if top_task[1] >= 3:
            patterns.append(f"🎯 Focused heavily on: '{top_task[0]}' ({top_task[1]} sprints)")
    
    # Consistency pattern
    sprint_days = set(s.started_at.date() for s in sprints)
    if len(sprint_days) >= 5:
        patterns.append(f"⭐ Consistent! Sprinted on {len(sprint_days)} different days")
    elif len(sprint_days) <= 2:
        patterns.append(f"📅 Only sprinted on {len(sprint_days)} days - try spreading work across the week")
    
    # Generate shareable stat
    shareable_stat = _generate_shareable_stat(
        total_sprints=total_sprints,
        total_minutes=total_minutes,
        completion_rate=completion_rate,
        most_productive_day=most_productive_day.split(" ")[0] if most_productive_day != "N/A" else "N/A",
    )
    
    return {
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "total_sprints": total_sprints,
        "total_minutes": total_minutes,
        "completion_rate": completion_rate,
        "top_outcomes": outcomes,
        "distraction_count": len(distraction_events),
        "most_productive_day": most_productive_day,
        "task_breakdown": task_breakdown,
        "patterns": patterns if patterns else ["Solid week of focused work!"],
        "shareable_stat": shareable_stat,
    }


def _generate_shareable_stat(
    total_sprints: int, total_minutes: int, completion_rate: float, most_productive_day: str
) -> str:
    """Generate a shareable stat for social media."""
    hours = total_minutes / 60
    
    if completion_rate >= 0.8:
        emoji = "🔥"
        vibe = "crushing it"
    elif completion_rate >= 0.6:
        emoji = "💪"
        vibe = "making progress"
    else:
        emoji = "🎯"
        vibe = "building momentum"
    
    return (
        f"{emoji} This week: {total_sprints} focused sprints, "
        f"{hours:.1f} hours of deep work, {completion_rate:.0%} completion rate. "
        f"{vibe.capitalize()} on {most_productive_day}s! #FocusSprintCoach"
    )


async def suggest_weekly_experiment(*, db: AsyncSession, user_id: UUID, weekly_summary: dict) -> dict:
    """Suggest one experiment for next week based on patterns.
    
    Returns:
        {
            "experiment": str,
            "reasoning": str,
            "how_to_measure": str
        }
    """
    patterns = weekly_summary.get("patterns", [])
    completion_rate = weekly_summary.get("completion_rate", 0.0)
    distraction_count = weekly_summary.get("distraction_count", 0)
    total_sprints = weekly_summary.get("total_sprints", 0)
    
    # Build context for LLM
    system = (
        "You are a productivity coach suggesting ONE specific experiment for next week. "
        "Make it concrete, measurable, and based on observed patterns. "
        "Output JSON: {\"experiment\": str, \"reasoning\": str, \"how_to_measure\": str}"
    )
    
    user = f"This week's stats:\n"
    user += f"- Total sprints: {total_sprints}\n"
    user += f"- Completion rate: {completion_rate:.0%}\n"
    user += f"- Distractions: {distraction_count}\n"
    user += f"\nObserved patterns:\n"
    for pattern in patterns:
        user += f"- {pattern}\n"
    
    user += (
        "\nSuggest ONE experiment for next week. Examples:\n"
        "- 'Try 10-min sprints instead of 25-min'\n"
        "- 'Start each day with your hardest task'\n"
        "- 'Turn off notifications during sprints'\n"
        "Be specific and actionable!"
    )
    
    try:
        result = await _chat_completion_json(system=system, user=user)
        if not isinstance(result, dict):
            return _fallback_experiment(completion_rate, distraction_count)
        
        return {
            "experiment": result.get("experiment", "Try shorter 10-min sprints"),
            "reasoning": result.get("reasoning", "Based on your patterns"),
            "how_to_measure": result.get("how_to_measure", "Track completion rate"),
        }
    except (LLMError, Exception) as e:
        logger.warning("Experiment suggestion failed: %s", e)
        return _fallback_experiment(completion_rate, distraction_count)


def _fallback_experiment(completion_rate: float, distraction_count: int) -> dict:
    """Fallback experiment suggestions based on simple rules."""
    if completion_rate < 0.4:
        return {
            "experiment": "Try 10-minute sprints instead of 25",
            "reasoning": "Shorter sprints are easier to complete and build momentum",
            "how_to_measure": "Track if your completion rate improves",
        }
    elif distraction_count > 10:
        return {
            "experiment": "Put phone in another room during sprints",
            "reasoning": "You logged many distractions - reduce temptation",
            "how_to_measure": "Count distractions per sprint",
        }
    else:
        return {
            "experiment": "Start each day with your hardest task",
            "reasoning": "Tackle tough work when energy is highest",
            "how_to_measure": "Note if you complete more difficult tasks",
        }


async def get_weekly_review(*, db: AsyncSession, user_id: UUID, week_offset: int = 0) -> dict:
    """Get complete weekly review with summary, experiment, and shareable stat.
    
    Returns comprehensive review for retention and engagement.
    """
    summary = await generate_weekly_summary(db=db, user_id=user_id, week_offset=week_offset)
    experiment = await suggest_weekly_experiment(db=db, user_id=user_id, weekly_summary=summary)
    
    return {
        "summary": summary,
        "experiment": experiment,
        "week_label": f"Week of {summary['week_start']}",
    }
