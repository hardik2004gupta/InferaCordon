"""
Context engine: selects and renders static prompt templates per budget class.

Per CLAUDE.md Section 6 Step 4 (Pre-Inference Pipeline) and policy.budget_profiles.context_template:
- Templates: direct / step_by_step / verify_steps (documented in CLAUDE.md Section 11.5)
- Template selection is driven by the policy budget profile, not by gateway code logic
- System prompt version tracked in policy (versions.system_prompt) for audit traceability
- No dynamic prompt construction beyond template rendering

File name: context_engine.py (per Part IX authoritative layout).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContextTemplate(str, Enum):
    DIRECT = "direct"
    STEP_BY_STEP = "step_by_step"
    VERIFY_STEPS = "verify_steps"


# Inline templates — no file I/O at request time.
# System prompt version matches policy.versions.system_prompt = "prompt_v2"
_TEMPLATES: dict[str, dict[str, str]] = {
    "direct": {
        "system": (
            "You are a helpful, accurate, and concise assistant. "
            "Answer the question directly and accurately."
        ),
    },
    "step_by_step": {
        "system": (
            "You are a helpful assistant. Think through the problem carefully and "
            "systematically before providing your answer. Show your reasoning."
        ),
    },
    "verify_steps": {
        "system": (
            "You are a helpful assistant. Think through the problem step by step, "
            "verify each step of your reasoning, and then provide a well-supported "
            "final answer."
        ),
    },
}


@dataclass
class RenderedContext:
    """Fully rendered prompt context for a single inference request."""
    system_prompt: str
    user_message: str
    template_name: str
    prompt_version: str

    def to_messages(self) -> list[dict]:
        """Convert to OpenAI message format per CLAUDE.md Section 8."""
        msgs: list[dict] = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.append({"role": "user", "content": self.user_message})
        return msgs


class ContextEngine:
    """
    Renders prompt templates from policy configuration.
    Stateless — safe for concurrent requests.
    Per CLAUDE.md Section 5 (Component Responsibility Matrix).
    """

    def __init__(self, templates_dir: str = "") -> None:
        # Phase 4: templates are inline; templates_dir reserved for Phase 11 extension
        pass

    def render(
        self,
        prompt: str,
        template: ContextTemplate,
        prompt_version: str,
    ) -> RenderedContext:
        """
        Render a system prompt for the given template type.

        Args:
            prompt:         The user's (already redacted in Phase 5) prompt text.
            template:       Template enum selected by BudgetDecision.context_template.
            prompt_version: Version string from policy.versions.system_prompt.

        Returns:
            RenderedContext with system_prompt, user_message, and version tracking.
        """
        tmpl = _TEMPLATES.get(template.value, _TEMPLATES["direct"])
        return RenderedContext(
            system_prompt=tmpl["system"],
            user_message=prompt,
            template_name=template.value,
            prompt_version=prompt_version,
        )

    @staticmethod
    def template_from_str(template_name: str) -> ContextTemplate:
        """Parse a template name string from policy budget profile."""
        try:
            return ContextTemplate(template_name)
        except ValueError:
            return ContextTemplate.DIRECT
