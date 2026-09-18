"""Learning-plan logic: prereq ordering, status bands, 'up next' correctness."""

import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Concept, LearnerConceptState, User
from app.services.onboarding import seed_concepts_for_user
from app.services.plan import learning_plan
from app.services.subject_templates import get_template, seed_builtin_templates


@pytest.mark.asyncio
async def test_plan_orders_ready_before_locked_and_done_last():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"plan-{uuid.uuid4().hex[:10]}@example.com", name="P")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Computer Science")
        concepts = await seed_concepts_for_user(db, user.id, template)
        by_name = {c.name: c for c in concepts}

        # master the prerequisites of Trees (Recursion) and mark Arrays done
        for name in ("Recursion", "Arrays"):
            st = await db.get(LearnerConceptState, (user.id, by_name[name].id))
            st.mastery = 0.8
        await db.commit()

        plan = await learning_plan(db, user.id, "Computer Science")

    statuses = [p["status"] for p in plan]
    # ready block first, locked in the middle, done at the end
    assert statuses == sorted(statuses, key=lambda s: {"ready": 0, "locked": 1, "done": 2}[s])

    entries = {p["name"]: p for p in plan}
    assert entries["Trees"]["status"] == "ready"          # prereq Recursion done
    assert entries["Graphs"]["status"] == "locked"        # prereq Trees not done
    assert entries["Dynamic Programming"]["status"] == "ready"  # Recursion+Arrays done
    assert entries["Arrays"]["status"] == "done"
    # 'up next' is a ready concept, and prereq order holds within ready group
    assert plan[0]["status"] == "ready"
    ready_names = [p["name"] for p in plan if p["status"] == "ready"]
    assert ready_names.index("Trees") < len(ready_names)
