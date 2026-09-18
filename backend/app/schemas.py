"""Shared pydantic shapes.

StarterConcept / OnboardingQuestion define THE onboarding contract: subject
templates in the library and the Dynamic Onboarding Agent's JSON output are
validated against the same models, so both paths feed identical downstream code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StarterConcept(BaseModel):
    name: str
    parent: str | None = None
    prerequisites: list[str] = Field(default_factory=list)


class OnboardingQuestion(BaseModel):
    key: str
    text: str
    type: Literal["single_select", "multi_select", "free_text"]
    options: list[str] = Field(default_factory=list)


class SubjectTemplateData(BaseModel):
    subject: str
    starter_concepts: list[StarterConcept]
    onboarding_questions: list[OnboardingQuestion]
