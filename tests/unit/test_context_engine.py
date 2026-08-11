"""
Unit tests for gateway/context_engine.py.

Tests cover:
- ContextTemplate enum values
- ContextEngine.render: all three template types
- RenderedContext.to_messages: OpenAI message format
- ContextEngine.template_from_str: valid/invalid template names
"""
from __future__ import annotations

import pytest

from gateway.context_engine import ContextEngine, ContextTemplate, RenderedContext


class TestContextTemplate:
    def test_enum_values(self):
        assert ContextTemplate.DIRECT.value == "direct"
        assert ContextTemplate.STEP_BY_STEP.value == "step_by_step"
        assert ContextTemplate.VERIFY_STEPS.value == "verify_steps"

    def test_string_comparison(self):
        assert ContextTemplate.DIRECT == "direct"

    def test_all_templates_distinct(self):
        values = {t.value for t in ContextTemplate}
        assert len(values) == 3


class TestContextEngineRender:
    def setup_method(self):
        self.engine = ContextEngine()

    def test_direct_template(self):
        result = self.engine.render(
            prompt="What is 2+2?",
            template=ContextTemplate.DIRECT,
            prompt_version="prompt_v2",
        )
        assert isinstance(result, RenderedContext)
        assert result.template_name == "direct"
        assert result.user_message == "What is 2+2?"
        assert result.prompt_version == "prompt_v2"
        assert len(result.system_prompt) > 0

    def test_step_by_step_template(self):
        result = self.engine.render(
            prompt="Solve this step by step",
            template=ContextTemplate.STEP_BY_STEP,
            prompt_version="prompt_v2",
        )
        assert result.template_name == "step_by_step"
        assert "step" in result.system_prompt.lower() or "systematic" in result.system_prompt.lower()

    def test_verify_steps_template(self):
        result = self.engine.render(
            prompt="Verify this claim",
            template=ContextTemplate.VERIFY_STEPS,
            prompt_version="prompt_v2",
        )
        assert result.template_name == "verify_steps"
        assert "verify" in result.system_prompt.lower()

    def test_user_message_preserved_exactly(self):
        prompt = "Hello\nworld\nwith newlines"
        result = self.engine.render(
            prompt=prompt,
            template=ContextTemplate.DIRECT,
            prompt_version="v1",
        )
        assert result.user_message == prompt

    def test_prompt_version_tracked(self):
        result = self.engine.render(
            prompt="Test",
            template=ContextTemplate.DIRECT,
            prompt_version="custom_v5",
        )
        assert result.prompt_version == "custom_v5"

    def test_engine_is_stateless_across_calls(self):
        r1 = self.engine.render("First", ContextTemplate.DIRECT, "v1")
        r2 = self.engine.render("Second", ContextTemplate.STEP_BY_STEP, "v1")
        assert r1.user_message != r2.user_message
        assert r1.template_name != r2.template_name

    def test_empty_prompt_renders(self):
        # Gateway shouldn't pass empty prompts, but engine should not crash
        result = self.engine.render("", ContextTemplate.DIRECT, "v1")
        assert result.user_message == ""

    def test_all_templates_produce_non_empty_system_prompts(self):
        for template in ContextTemplate:
            result = self.engine.render("Test", template, "v1")
            assert result.system_prompt.strip() != ""


class TestRenderedContextToMessages:
    def _render(self, template=ContextTemplate.DIRECT) -> RenderedContext:
        return ContextEngine().render(
            prompt="Test prompt",
            template=template,
            prompt_version="v1",
        )

    def test_returns_list(self):
        result = self._render()
        messages = result.to_messages()
        assert isinstance(messages, list)

    def test_has_system_message(self):
        messages = self._render().to_messages()
        roles = [m["role"] for m in messages]
        assert "system" in roles

    def test_has_user_message(self):
        messages = self._render().to_messages()
        roles = [m["role"] for m in messages]
        assert "user" in roles

    def test_system_comes_before_user(self):
        messages = self._render().to_messages()
        roles = [m["role"] for m in messages]
        assert roles.index("system") < roles.index("user")

    def test_user_message_content(self):
        messages = self._render().to_messages()
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert user_msgs[0]["content"] == "Test prompt"

    def test_message_dicts_have_role_and_content(self):
        for msg in self._render().to_messages():
            assert "role" in msg
            assert "content" in msg

    def test_all_templates_produce_messages(self):
        for template in ContextTemplate:
            messages = ContextEngine().render("Test", template, "v1").to_messages()
            assert len(messages) >= 2  # at least system + user


class TestTemplateFromStr:
    def test_direct(self):
        assert ContextEngine.template_from_str("direct") is ContextTemplate.DIRECT

    def test_step_by_step(self):
        assert ContextEngine.template_from_str("step_by_step") is ContextTemplate.STEP_BY_STEP

    def test_verify_steps(self):
        assert ContextEngine.template_from_str("verify_steps") is ContextTemplate.VERIFY_STEPS

    def test_unknown_falls_back_to_direct(self):
        result = ContextEngine.template_from_str("nonexistent_template")
        assert result is ContextTemplate.DIRECT

    def test_empty_string_falls_back_to_direct(self):
        result = ContextEngine.template_from_str("")
        assert result is ContextTemplate.DIRECT
