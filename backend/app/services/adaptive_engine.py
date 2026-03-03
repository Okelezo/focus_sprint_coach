"""Adaptive Sprint Engine - Personalization that learns from user patterns.

Features:
1. Auto-recommend sprint duration (10/15/25 min) based on completion patterns
2. Detect task paralysis and suggest smaller steps
3. Time-of-day analysis and nudges
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint, SprintStatus
from app.db.models.sprint_reflection import SprintReflection
from app.db.models.task import Task
from app.services.sprints import get_recent_sprint_stats

logger = logging.getLogger(__name__)


async def recommend_sprint_duration(*, db: AsyncSession, user_id: UUID) -> dict:
    """Recommend optimal sprint duration based on user's completion patterns.
    
    Returns:
        {
            "recommended_duration": int,  # 10, 15, or 25
            "reasoning": str,
            "confidence": float  # 0.0 to 1.0
        }
    """
    stats = await get_recent_sprint_stats(db=db, user_id=user_id, days=30)
    
    total_sprints = stats.get("total_sprints", 0)
    
    # Not enough data - default to 25
    if total_sprints < 3:
        return {
            "recommended_duration": 25,
            "reasoning": "Standard 25-minute sprint (not enough history to personalize yet)",
            "confidence": 0.3,
        }
    
    # Get sprints grouped by duration
    sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id)
        .order_by(Sprint.started_at.desc())
        .limit(30)
    )
    sprints = list(sprints_result.scalars().all())
    
    # Get reflections
    sprint_ids = [s.id for s in sprints]
    reflections_result = await db.execute(
        select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint = {r.sprint_id: r for r in reflections}
    
    # Analyze completion rate by duration bucket
    duration_stats = {10: {"total": 0, "completed": 0}, 15: {"total": 0, "completed": 0}, 25: {"total": 0, "completed": 0}}
    
    for sprint in sprints:
        # Bucket durations
        if sprint.duration_minutes <= 12:
            bucket = 10
        elif sprint.duration_minutes <= 20:
            bucket = 15
        else:
            bucket = 25
        
        duration_stats[bucket]["total"] += 1
        
        if sprint.id in reflection_by_sprint and reflection_by_sprint[sprint.id].outcome == "done":
            duration_stats[bucket]["completed"] += 1
    
    # Calculate completion rates
    completion_rates = {}
    for duration, stats_data in duration_stats.items():
        if stats_data["total"] > 0:
            completion_rates[duration] = stats_data["completed"] / stats_data["total"]
        else:
            completion_rates[duration] = 0.0
    
    # Find best duration
    best_duration = max(completion_rates.items(), key=lambda x: x[1])
    
    # Check if user is struggling (low overall completion rate)
    overall_completion = stats.get("completion_rate", 0.0)
    
    if overall_completion < 0.4:
        # Struggling - recommend shorter sprints
        recommended = 10
        reasoning = f"Shorter 10-min sprints recommended - your completion rate is {overall_completion:.0%}. Smaller chunks build momentum!"
        confidence = 0.8
    elif best_duration[1] > 0.6 and duration_stats[best_duration[0]]["total"] >= 3:
        # Clear winner with enough data
        recommended = best_duration[0]
        reasoning = f"You complete {best_duration[1]:.0%} of {best_duration[0]}-min sprints - that's your sweet spot!"
        confidence = 0.9
    else:
        # Default based on overall pattern
        if overall_completion > 0.7:
            recommended = 25
            reasoning = f"You're crushing it ({overall_completion:.0%} completion) - stick with 25-min sprints!"
        else:
            recommended = 15
            reasoning = f"15-min sprints balance focus and completion ({overall_completion:.0%} rate)"
        confidence = 0.6
    
    return {
        "recommended_duration": recommended,
        "reasoning": reasoning,
        "confidence": confidence,
    }


async def detect_task_paralysis(*, db: AsyncSession, user_id: UUID, task_id: UUID) -> dict:
    """Detect if user is stuck on a task and suggest breaking it down.
    
    Returns:
        {
            "is_paralyzed": bool,
            "indicators": list[str],
            "suggestion": str
        }
    """
    # Get task
    task_result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = task_result.scalar_one_or_none()
    
    if task is None:
        return {"is_paralyzed": False, "indicators": [], "suggestion": ""}
    
    # Get sprints for this task
    sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.task_id == task_id, Sprint.user_id == user_id)
        .order_by(Sprint.started_at.desc())
    )
    sprints = list(sprints_result.scalars().all())
    
    indicators = []
    
    # Indicator 1: Multiple failed/abandoned sprints
    if len(sprints) >= 3:
        sprint_ids = [s.id for s in sprints]
        reflections_result = await db.execute(
            select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
        )
        reflections = list(reflections_result.scalars().all())
        
        failed_count = sum(1 for r in reflections if r.outcome in ["blocked", "distracted"])
        
        if failed_count >= 2:
            indicators.append(f"You've struggled with this task {failed_count} times")
    
    # Indicator 2: Task created >3 days ago but not completed
    if task.created_at:
        age_days = (datetime.now(timezone.utc) - task.created_at).days
        if age_days >= 3 and not task.completed_at:
            indicators.append(f"Task is {age_days} days old and still not done")
    
    # Indicator 3: Task title suggests complexity
    complexity_keywords = ["implement", "build", "create", "design", "research", "analyze", "refactor"]
    if any(keyword in task.title.lower() for keyword in complexity_keywords):
        indicators.append("Task title suggests this is complex work")
    
    is_paralyzed = len(indicators) >= 2
    
    if is_paralyzed:
        suggestion = (
            "🎯 This task might be too big. Try breaking it into 3 tiny steps:\n"
            "1. What's the absolute smallest thing you can do in 5 minutes?\n"
            "2. What would 'done enough' look like?\n"
            "3. What can you skip or simplify?"
        )
    else:
        suggestion = ""
    
    return {
        "is_paralyzed": is_paralyzed,
        "indicators": indicators,
        "suggestion": suggestion,
    }


async def analyze_time_of_day_patterns(*, db: AsyncSession, user_id: UUID) -> dict:
    """Analyze when user is most productive and suggest best times.
    
    Returns:
        {
            "best_hours": list[int],  # Hours of day (0-23)
            "worst_hours": list[int],
            "recommendation": str,
            "sample_size": int
        }
    """
    # Get recent sprints with timestamps
    sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id)
        .order_by(Sprint.started_at.desc())
        .limit(50)
    )
    sprints = list(sprints_result.scalars().all())
    
    if len(sprints) < 5:
        return {
            "best_hours": [],
            "worst_hours": [],
            "recommendation": "Not enough sprint history to analyze time-of-day patterns yet",
            "sample_size": len(sprints),
        }
    
    # Get reflections
    sprint_ids = [s.id for s in sprints]
    reflections_result = await db.execute(
        select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint = {r.sprint_id: r for r in reflections}
    
    # Group by hour of day
    hour_stats = {h: {"total": 0, "completed": 0} for h in range(24)}
    
    for sprint in sprints:
        hour = sprint.started_at.hour
        hour_stats[hour]["total"] += 1
        
        if sprint.id in reflection_by_sprint and reflection_by_sprint[sprint.id].outcome == "done":
            hour_stats[hour]["completed"] += 1
    
    # Calculate completion rates for hours with data
    hour_rates = {}
    for hour, stats in hour_stats.items():
        if stats["total"] >= 2:  # Need at least 2 sprints
            hour_rates[hour] = stats["completed"] / stats["total"]
    
    if not hour_rates:
        return {
            "best_hours": [],
            "worst_hours": [],
            "recommendation": "Need more varied sprint times to detect patterns",
            "sample_size": len(sprints),
        }
    
    # Find best and worst hours
    sorted_hours = sorted(hour_rates.items(), key=lambda x: x[1], reverse=True)
    
    best_hours = [h for h, rate in sorted_hours[:3] if rate > 0.6]
    worst_hours = [h for h, rate in sorted_hours[-3:] if rate < 0.4]
    
    # Generate recommendation
    if best_hours:
        best_times = ", ".join([f"{h}:00" for h in best_hours])
        recommendation = f"🌟 You're most productive around {best_times}. Schedule important work then!"
    else:
        recommendation = "Keep tracking - we'll find your peak productivity hours soon!"
    
    return {
        "best_hours": best_hours,
        "worst_hours": worst_hours,
        "recommendation": recommendation,
        "sample_size": len(sprints),
    }


async def get_adaptive_recommendations(*, db: AsyncSession, user_id: UUID, task_id: UUID | None = None) -> dict:
    """Get all adaptive recommendations in one call.
    
    Returns comprehensive personalization data.
    """
    duration_rec = await recommend_sprint_duration(db=db, user_id=user_id)
    time_analysis = await analyze_time_of_day_patterns(db=db, user_id=user_id)
    
    result = {
        "duration": duration_rec,
        "time_of_day": time_analysis,
    }
    
    if task_id:
        paralysis = await detect_task_paralysis(db=db, user_id=user_id, task_id=task_id)
        result["task_paralysis"] = paralysis
    
    return result
