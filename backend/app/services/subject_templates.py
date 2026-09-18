"""Built-in subject template library + idempotent DB seeding."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SubjectTemplate
from app.schemas import SubjectTemplateData

BUILTIN_TEMPLATES: list[dict] = [
    {
        "subject": "Computer Science",
        "starter_concepts": [
            {"name": "Arrays", "parent": None, "prerequisites": []},
            {"name": "Recursion", "parent": None, "prerequisites": []},
            {"name": "Stacks & Queues", "parent": None, "prerequisites": ["Arrays"]},
            {"name": "Trees", "parent": None, "prerequisites": ["Recursion"]},
            {"name": "Graphs", "parent": None, "prerequisites": ["Trees"]},
            {"name": "Dynamic Programming", "parent": None, "prerequisites": ["Recursion", "Arrays"]},
            {"name": "Time Complexity", "parent": None, "prerequisites": []},
            {"name": "Operating Systems: Processes", "parent": None, "prerequisites": []},
            {"name": "DBMS: Normalization", "parent": None, "prerequisites": []},
            {"name": "Networks: TCP/IP", "parent": None, "prerequisites": []},
        ],
        "onboarding_questions": [
            {"key": "languages", "text": "Which languages are you comfortable coding in?", "type": "multi_select", "options": ["C++", "Python", "Java", "JavaScript", "SQL", "Other"]},
            {"key": "dsa_comfort", "text": "How comfortable are you with data structures & algorithms?", "type": "single_select", "options": ["Just starting", "Know the basics", "Comfortable with medium problems", "Strong — solving hard problems regularly"]},
            {"key": "cp_habit", "text": "Do you practice competitive programming?", "type": "single_select", "options": ["No", "Occasionally", "Regularly (Codeforces/LeetCode etc.)"]},
            {"key": "current_courses", "text": "Which courses are you currently taking?", "type": "multi_select", "options": ["Data Structures", "OS", "DBMS", "Computer Networks", "OOP", "Other"]},
            {"key": "goal", "text": "What's your main goal right now?", "type": "single_select", "options": ["Ace semester exams", "Placement/interview prep", "Build real projects", "Deepen understanding for its own sake"]},
        ],
    },
    {
        "subject": "Physics",
        "starter_concepts": [
            {"name": "Kinematics", "parent": None, "prerequisites": []},
            {"name": "Newton's Laws", "parent": None, "prerequisites": ["Kinematics"]},
            {"name": "Work, Energy & Power", "parent": None, "prerequisites": ["Newton's Laws"]},
            {"name": "Rotational Motion", "parent": None, "prerequisites": ["Newton's Laws"]},
            {"name": "Electrostatics", "parent": None, "prerequisites": []},
            {"name": "Current Electricity", "parent": None, "prerequisites": ["Electrostatics"]},
            {"name": "Electromagnetic Induction", "parent": None, "prerequisites": ["Current Electricity"]},
            {"name": "Waves & Optics", "parent": None, "prerequisites": []},
            {"name": "Modern Physics: Photoelectric Effect", "parent": None, "prerequisites": []},
            {"name": "Thermodynamics", "parent": None, "prerequisites": []},
        ],
        "onboarding_questions": [
            {"key": "math_comfort", "text": "How comfortable are you with the calculus needed for physics (derivatives, integrals)?", "type": "single_select", "options": ["Not yet covered", "Basic", "Comfortable", "Strong"]},
            {"key": "topics_covered", "text": "Which broad areas have you already studied?", "type": "multi_select", "options": ["Mechanics", "Electromagnetism", "Optics", "Thermodynamics", "Modern Physics", "None yet"]},
            {"key": "explanation_style", "text": "How do you like physics explained?", "type": "single_select", "options": ["Intuition first, math later", "Math first, then intuition", "Real-world examples and analogies", "Diagrams and visualizations"]},
            {"key": "exam_context", "text": "Is there a specific exam you're preparing for?", "type": "single_select", "options": ["College semester exam", "Competitive/entrance exam", "Just learning, no exam", "Other"]},
            {"key": "goal", "text": "What's your main goal right now?", "type": "single_select", "options": ["Ace semester exams", "Competitive exam prep", "Build strong fundamentals", "Curiosity-driven learning"]},
        ],
    },
]


async def seed_builtin_templates(db: AsyncSession) -> None:
    """Insert built-in templates if missing. Safe to run every startup."""
    for raw in BUILTIN_TEMPLATES:
        data = SubjectTemplateData.model_validate(raw)  # fail loudly on drift
        existing = await db.scalar(
            select(SubjectTemplate).where(SubjectTemplate.subject == data.subject)
        )
        if existing is None:
            db.add(
                SubjectTemplate(
                    subject=data.subject,
                    starter_concepts=[c.model_dump() for c in data.starter_concepts],
                    onboarding_questions=[q.model_dump() for q in data.onboarding_questions],
                )
            )
    await db.commit()


async def get_template(db: AsyncSession, subject: str) -> SubjectTemplateData | None:
    row = await db.scalar(
        select(SubjectTemplate).where(SubjectTemplate.subject.ilike(subject))
    )
    if row is None:
        return None
    return SubjectTemplateData(
        subject=row.subject,
        starter_concepts=row.starter_concepts,
        onboarding_questions=row.onboarding_questions,
    )
