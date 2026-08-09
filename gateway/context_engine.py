"""
Context engine: selects and renders static prompt templates per budget class.

Per CLAUDE.md Section 6 (Step 11) and policy.budget_profiles.context_template:
- Templates: direct / step_by_step / verify_steps (defined in CLAUDE.md Section 11)
- Template selection driven by policy budget profile, not by code logic
- Versions tracked in policy (system_prompt: prompt_v2) for audit
- No dynamic prompt construction beyond template rendering
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContextTemplate(str, Enum):
    DIRECT = "direct"
    STEP_BY_STEP = "step_by_step"
    VERIFY_STEPS = "verify_steps"


@dataclass
class RenderedContext:
    system_prompt: str
    user_message: str
    template_name: str
    prompt_version: str


class ContextEngine:
    """Renders prompt templates from policy configuration."""

    def __init__(self, templates_dir: str) -> None:
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 11 (Week 1)")

    def render(
        self,
        prompt: str,
        template: ContextTemplate,
        prompt_version: str,
    ) -> RenderedContext:
        raise NotImplementedError("Implement per CLAUDE.md Section 6 Step 11 (Week 1)")
