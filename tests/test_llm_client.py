"""
Tests for the LLM client layer.

Tests StubClient behavior, prompt loading, and user message building.
Does NOT test AnthropicClient (requires API key).
"""

import json

from ai_ops.llm.client import StubClient, create_client
from ai_ops.llm.prompts import build_user_message, load_system_prompt


class TestStubClient:
    """Test the StubClient (deterministic responses)."""

    def test_provider_name(self):
        client = StubClient()
        assert client.provider_name == "stub"

    def test_model_name(self):
        client = StubClient()
        assert client.model_name == "stub-v1"

    def test_dispatcher_response(self):
        """StubClient should return dispatcher-shaped JSON for dispatcher prompts."""
        client = StubClient()
        response = client.complete(
            system="You are the Dispatcher agent...",
            user="Build something",
        )
        parsed = json.loads(response)
        assert "classification" in parsed
        assert "plan" in parsed

    def test_research_response(self):
        """StubClient should return research-shaped JSON for research prompts."""
        client = StubClient()
        response = client.complete(
            system="You are the Research agent...",
            user="Compare frameworks",
        )
        parsed = json.loads(response)
        assert "findings" in parsed
        assert "recommendations" in parsed

    def test_builder_response(self):
        client = StubClient()
        response = client.complete(
            system="You are the Builder agent...",
            user="Implement feature",
        )
        parsed = json.loads(response)
        assert "implementation_summary" in parsed
        assert "files_changed" in parsed

    def test_reviewer_response(self):
        client = StubClient()
        response = client.complete(
            system="You are the Reviewer agent...",
            user="Review code",
        )
        parsed = json.loads(response)
        assert "verdict" in parsed

    def test_fallback_response(self):
        """Unknown system prompt should still return valid JSON."""
        client = StubClient()
        response = client.complete(
            system="You are an unknown agent.",
            user="Do something",
        )
        parsed = json.loads(response)
        assert "status" in parsed

    def test_expect_json_flag(self):
        """expect_json flag should not break StubClient."""
        client = StubClient()
        response = client.complete(
            system="You are the Dispatcher",
            user="Task",
            expect_json=True,
        )
        parsed = json.loads(response)
        assert isinstance(parsed, dict)


class TestCreateClient:
    """Test the client factory function."""

    def test_no_api_key_returns_stub(self, monkeypatch):
        """Without API key, create_client should return StubClient."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = create_client()
        assert client.provider_name == "stub"

    def test_explicit_none_returns_stub(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = create_client(api_key=None)
        assert client.provider_name == "stub"


class TestPromptLoading:
    """Test prompt.md loading."""

    def test_load_dispatcher_prompt(self):
        prompt = load_system_prompt("dispatcher")
        assert "Dispatcher" in prompt
        assert len(prompt) > 100  # should be substantial

    def test_load_research_prompt(self):
        prompt = load_system_prompt("research")
        assert "Research" in prompt

    def test_load_builder_prompt(self):
        prompt = load_system_prompt("builder")
        assert "Builder" in prompt

    def test_load_reviewer_prompt(self):
        prompt = load_system_prompt("reviewer")
        assert "Reviewer" in prompt

    def test_load_nonexistent_prompt(self):
        """Loading a prompt for a nonexistent agent should raise."""
        import pytest
        with pytest.raises(FileNotFoundError):
            load_system_prompt("nonexistent-agent")


class TestUserMessageBuilding:
    """Test user message construction."""

    def test_basic_message(self):
        msg = build_user_message(description="Build a login page")
        assert "Build a login page" in msg
        assert "## Task" in msg

    def test_with_criteria(self):
        msg = build_user_message(
            description="Build auth",
            acceptance_criteria=["JWT support", "Password hashing"],
        )
        assert "JWT support" in msg
        assert "Acceptance Criteria" in msg

    def test_with_constraints(self):
        msg = build_user_message(
            description="Build auth",
            constraints=["Python 3.11+"],
        )
        assert "Python 3.11+" in msg
        assert "Constraints" in msg

    def test_with_context(self):
        msg = build_user_message(
            description="Build auth",
            context={"research_output": {"findings": ["use PyJWT"]}},
        )
        assert "research_output" in msg
        assert "PyJWT" in msg

    def test_empty_context_excluded(self):
        msg = build_user_message(
            description="Build auth",
            context={"empty": {}},
        )
        assert "empty" not in msg
