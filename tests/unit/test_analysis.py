"""
Patient Safety Monitor - Analysis Module Unit Tests

Comprehensive tests for the analysis module covering:
- LLM client configuration and response handling
- Claude and OpenAI API clients
- LLM client factory
- Prompt template loading
- Analysis pipeline stages (classification, extraction, human factors, blog generation)
- Result data classes
"""

import asyncio
import json
import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from uuid import uuid4

from analysis.llm_client import (
    LLMConfig,
    LLMResponse,
    BaseLLMClient,
    ClaudeClient,
    OpenAIClient,
    LLMClientFactory,
)
from analysis.analyser import (
    ClassificationResult,
    ExtractionResult,
    HumanFactorsResult,
    BlogPostResult,
    AnalysisPipelineResult,
    PromptTemplateLoader,
    AnalysisPipeline,
)


# =============================================================================
# Test LLM Data Classes
# =============================================================================

class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_values(self):
        """Test that defaults are set correctly."""
        config = LLMConfig()

        assert config.temperature == 0.3
        assert config.max_tokens == 4096
        assert config.timeout_seconds == 120
        assert config.max_retries == 3
        assert config.stop_sequences == []
        assert config.json_mode is False

    def test_custom_values(self):
        """Test setting custom values."""
        config = LLMConfig(
            temperature=0.7,
            max_tokens=2000,
            timeout_seconds=60,
            max_retries=5,
            stop_sequences=["STOP", "END"],
            json_mode=True,
        )

        assert config.temperature == 0.7
        assert config.max_tokens == 2000
        assert config.timeout_seconds == 60
        assert config.max_retries == 5
        assert config.stop_sequences == ["STOP", "END"]
        assert config.json_mode is True


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_default_values(self):
        """Test that defaults are set correctly."""
        response = LLMResponse(content="Test content")

        assert response.content == "Test content"
        assert response.tokens_input == 0
        assert response.tokens_output == 0
        assert response.cost_usd == 0.0
        assert response.model == ""
        assert response.provider == ""
        assert response.latency_seconds == 0.0
        assert response.raw_response is None

    def test_custom_values(self):
        """Test setting custom values."""
        response = LLMResponse(
            content="Custom content",
            tokens_input=100,
            tokens_output=200,
            cost_usd=0.015,
            model="claude-sonnet-4",
            provider="claude",
            latency_seconds=2.5,
            raw_response={"test": "data"},
        )

        assert response.content == "Custom content"
        assert response.tokens_input == 100
        assert response.tokens_output == 200
        assert response.cost_usd == 0.015
        assert response.model == "claude-sonnet-4"
        assert response.provider == "claude"
        assert response.latency_seconds == 2.5
        assert response.raw_response == {"test": "data"}

    def test_total_tokens_property(self):
        """Test total_tokens computed property."""
        response = LLMResponse(
            content="Test",
            tokens_input=150,
            tokens_output=350,
        )

        assert response.total_tokens == 500


# =============================================================================
# Test Base LLM Client
# =============================================================================

class TestBaseLLMClient:
    """Tests for BaseLLMClient abstract class."""

    def test_cost_calculation(self):
        """Test cost calculation with various token counts."""
        # Create a concrete implementation for testing
        class TestClient(BaseLLMClient):
            COST_PER_1K_INPUT = 0.003
            COST_PER_1K_OUTPUT = 0.015

            @property
            def provider_name(self) -> str:
                return "test"

            async def _call_api(self, system_prompt, user_prompt, config):
                return {}

            def _parse_response(self, raw_response):
                return "", 0, 0

        client = TestClient(api_key="test-key", model="test-model")

        # Test with 1000 input and 2000 output tokens
        cost = client._calculate_cost(1000, 2000)
        # (1000/1000 * 0.003) + (2000/1000 * 0.015) = 0.003 + 0.030 = 0.033
        assert cost == 0.033

        # Test with zero tokens
        cost_zero = client._calculate_cost(0, 0)
        assert cost_zero == 0.0

        # Test with fractional thousands
        cost_partial = client._calculate_cost(500, 750)
        # (500/1000 * 0.003) + (750/1000 * 0.015) = 0.0015 + 0.01125 = 0.01275
        assert cost_partial == 0.01275

    @pytest.mark.asyncio
    async def test_retry_logic(self):
        """Test retry logic with exponential backoff."""
        call_count = 0

        class TestClient(BaseLLMClient):
            COST_PER_1K_INPUT = 0.003
            COST_PER_1K_OUTPUT = 0.015

            @property
            def provider_name(self) -> str:
                return "test"

            async def _call_api(self, system_prompt, user_prompt, config):
                nonlocal call_count
                call_count += 1

                # Fail first 2 attempts, succeed on 3rd
                if call_count < 3:
                    raise ValueError("Simulated API error")

                return {
                    "content": [{"type": "text", "text": "Success"}],
                    "usage": {"input_tokens": 100, "output_tokens": 200},
                }

            def _parse_response(self, raw_response):
                return "Success", 100, 200

        client = TestClient(api_key="test-key", model="test-model")
        config = LLMConfig(max_retries=3)

        response = await client.complete(
            system_prompt="System",
            user_prompt="User",
            config=config,
        )

        # Should succeed after 3 attempts
        assert call_count == 3
        assert response.content == "Success"

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that retries are exhausted and exception is raised."""
        class TestClient(BaseLLMClient):
            @property
            def provider_name(self) -> str:
                return "test"

            async def _call_api(self, system_prompt, user_prompt, config):
                raise ValueError("Persistent error")

            def _parse_response(self, raw_response):
                return "", 0, 0

        client = TestClient(api_key="test-key", model="test-model")
        config = LLMConfig(max_retries=2)

        with pytest.raises(ValueError, match="Persistent error"):
            await client.complete(
                system_prompt="System",
                user_prompt="User",
                config=config,
            )


# =============================================================================
# Test Claude Client
# =============================================================================

class TestClaudeClient:
    """Tests for ClaudeClient."""

    def test_provider_name(self):
        """Test provider name is correct."""
        client = ClaudeClient(api_key="test-key")
        assert client.provider_name == "claude"

    def test_parse_response(self):
        """Test parsing Claude API response."""
        client = ClaudeClient(api_key="test-key")

        raw_response = {
            "content": [
                {"type": "text", "text": "First block. "},
                {"type": "text", "text": "Second block."},
            ],
            "usage": {
                "input_tokens": 150,
                "output_tokens": 450,
            },
        }

        content, tokens_in, tokens_out = client._parse_response(raw_response)

        assert content == "First block. Second block."
        assert tokens_in == 150
        assert tokens_out == 450

    def test_parse_response_missing_fields(self):
        """Test parsing response with missing fields."""
        client = ClaudeClient(api_key="test-key")

        raw_response = {
            "content": [],
            "usage": {},
        }

        content, tokens_in, tokens_out = client._parse_response(raw_response)

        assert content == ""
        assert tokens_in == 0
        assert tokens_out == 0

    def test_calculate_cost(self):
        """Test Claude cost calculation with correct pricing."""
        client = ClaudeClient(api_key="test-key")

        # Claude Sonnet 4: $0.003 per 1K input, $0.015 per 1K output
        cost = client._calculate_cost(1000, 2000)
        # (1000/1000 * 0.003) + (2000/1000 * 0.015) = 0.003 + 0.030 = 0.033
        assert cost == 0.033

    @pytest.mark.asyncio
    async def test_call_api(self):
        """Test Claude API call with mocked client."""
        mock_anthropic = MagicMock()
        mock_messages = AsyncMock()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "content": [{"type": "text", "text": "Response"}],
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }
        mock_messages.create.return_value = mock_response
        mock_anthropic.messages = mock_messages

        with patch('anthropic.AsyncAnthropic', return_value=mock_anthropic):
            client = ClaudeClient(api_key="test-key", model="claude-sonnet-4")

            raw_response = await client._call_api(
                system_prompt="You are helpful",
                user_prompt="Hello",
                config=LLMConfig(),
            )

            assert raw_response["content"][0]["text"] == "Response"
            assert raw_response["usage"]["input_tokens"] == 100


# =============================================================================
# Test OpenAI Client
# =============================================================================

class TestOpenAIClient:
    """Tests for OpenAIClient."""

    def test_provider_name(self):
        """Test provider name is correct."""
        client = OpenAIClient(api_key="test-key")
        assert client.provider_name == "openai"

    def test_parse_response(self):
        """Test parsing OpenAI API response."""
        client = OpenAIClient(api_key="test-key")

        raw_response = {
            "choices": [
                {
                    "message": {
                        "content": "OpenAI response content",
                    },
                },
            ],
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 600,
            },
        }

        content, tokens_in, tokens_out = client._parse_response(raw_response)

        assert content == "OpenAI response content"
        assert tokens_in == 200
        assert tokens_out == 600

    def test_parse_response_missing_fields(self):
        """Test parsing response with missing fields."""
        client = OpenAIClient(api_key="test-key")

        raw_response = {
            "choices": [],
            "usage": {},
        }

        content, tokens_in, tokens_out = client._parse_response(raw_response)

        assert content == ""
        assert tokens_in == 0
        assert tokens_out == 0

    @pytest.mark.asyncio
    async def test_json_mode_configuration(self):
        """Test that JSON mode is correctly configured."""
        mock_openai = MagicMock()
        mock_chat = MagicMock()
        mock_completions = AsyncMock()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "choices": [{"message": {"content": '{"key": "value"}'}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 100},
        }
        mock_completions.create.return_value = mock_response
        mock_chat.completions = mock_completions
        mock_openai.chat = mock_chat

        with patch('openai.AsyncOpenAI', return_value=mock_openai):
            client = OpenAIClient(api_key="test-key", model="gpt-5-turbo")

            config = LLMConfig(json_mode=True)
            raw_response = await client._call_api(
                system_prompt="System",
                user_prompt="User",
                config=config,
            )

            # Verify json_mode was passed in the call
            call_args = mock_completions.create.call_args
            assert call_args.kwargs["response_format"] == {"type": "json_object"}


# =============================================================================
# Test LLM Client Factory
# =============================================================================

class TestLLMClientFactory:
    """Tests for LLMClientFactory."""

    def test_create_claude_client(self):
        """Test creating Claude client."""
        client = LLMClientFactory.create(
            provider="claude",
            api_key="test-claude-key",
            model="claude-sonnet-4",
        )

        assert isinstance(client, ClaudeClient)
        assert client.api_key == "test-claude-key"
        assert client.model == "claude-sonnet-4"

    def test_create_openai_client(self):
        """Test creating OpenAI client."""
        client = LLMClientFactory.create(
            provider="openai",
            api_key="test-openai-key",
            model="gpt-5-turbo",
        )

        assert isinstance(client, OpenAIClient)
        assert client.api_key == "test-openai-key"
        assert client.model == "gpt-5-turbo"

    def test_create_with_default_model(self):
        """Test creating client with default model."""
        client = LLMClientFactory.create(
            provider="claude",
            api_key="test-key",
        )

        assert isinstance(client, ClaudeClient)
        assert client.model == "claude-sonnet-4-20250514"

    def test_create_unknown_provider(self):
        """Test creating client with unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            LLMClientFactory.create(
                provider="unknown",
                api_key="test-key",
            )

    def test_create_default_claude(self, mock_settings):
        """Test create_default with Claude as primary."""
        mock_settings.llm_primary_provider = "claude"
        mock_settings.anthropic_api_key = "claude-key"
        mock_settings.openai_api_key = None
        mock_settings.llm_primary_model = "claude-sonnet-4"

        client = LLMClientFactory.create_default()

        assert isinstance(client, ClaudeClient)
        assert client.api_key == "claude-key"

    def test_create_default_openai(self, mock_settings):
        """Test create_default with OpenAI as primary."""
        mock_settings.llm_primary_provider = "openai"
        mock_settings.openai_api_key = "openai-key"
        mock_settings.anthropic_api_key = None
        mock_settings.llm_primary_model = "gpt-5-turbo"

        client = LLMClientFactory.create_default()

        assert isinstance(client, OpenAIClient)
        assert client.api_key == "openai-key"

    def test_create_default_no_keys(self, mock_settings):
        """Test create_default with no API keys raises error."""
        mock_settings.anthropic_api_key = None
        mock_settings.openai_api_key = None

        with pytest.raises(ValueError, match="No LLM API keys configured"):
            LLMClientFactory.create_default()


# =============================================================================
# Test Prompt Template Loader
# =============================================================================

class TestPromptTemplateLoader:
    """Tests for PromptTemplateLoader."""

    def test_load_existing_template(self, tmp_path):
        """Test loading an existing template file."""
        # Create test template file
        template_dir = tmp_path / "prompts"
        template_dir.mkdir()
        template_file = template_dir / "test_template.txt"
        template_file.write_text("Hello {name}, you are {age} years old.")

        loader = PromptTemplateLoader(template_dir)
        result = loader.load("test_template", name="Alice", age=30)

        assert result == "Hello Alice, you are 30 years old."

    def test_caching_behavior(self, tmp_path):
        """Test that templates are cached after first load."""
        template_dir = tmp_path / "prompts"
        template_dir.mkdir()
        template_file = template_dir / "cached_template.txt"
        template_file.write_text("Original content {var}")

        loader = PromptTemplateLoader(template_dir)

        # First load
        result1 = loader.load("cached_template", var="value1")
        assert result1 == "Original content value1"

        # Modify file (should not affect cached version)
        template_file.write_text("Modified content {var}")

        # Second load (should use cache)
        result2 = loader.load("cached_template", var="value2")
        assert result2 == "Original content value2"

        # Clear cache and reload
        loader.clear_cache()
        result3 = loader.load("cached_template", var="value3")
        assert result3 == "Modified content value3"

    def test_variable_substitution(self, tmp_path):
        """Test variable substitution with multiple variables."""
        template_dir = tmp_path / "prompts"
        template_dir.mkdir()
        template_file = template_dir / "multi_var.txt"
        template_file.write_text("Name: {name}, Age: {age}, City: {city}")

        loader = PromptTemplateLoader(template_dir)
        result = loader.load("multi_var", name="Bob", age=25, city="London")

        assert result == "Name: Bob, Age: 25, City: London"

    def test_fallback_to_default_prompts(self, tmp_path):
        """Test fallback to default prompts when template not found."""
        template_dir = tmp_path / "prompts"
        template_dir.mkdir()

        loader = PromptTemplateLoader(template_dir)
        result = loader.load("classify_healthcare", content="Test content")

        # Should return default prompt with substituted content
        assert "Test content" in result
        assert "healthcare" in result.lower()

    def test_clear_cache(self, tmp_path):
        """Test clearing template cache."""
        template_dir = tmp_path / "prompts"
        template_dir.mkdir()
        template_file = template_dir / "clear_test.txt"
        template_file.write_text("Test {value}")

        loader = PromptTemplateLoader(template_dir)

        # Load and cache
        loader.load("clear_test", value="1")
        assert "clear_test" in loader._cache

        # Clear cache
        loader.clear_cache()
        assert "clear_test" not in loader._cache


# =============================================================================
# Test Result Classes
# =============================================================================

class TestResultClasses:
    """Tests for result data classes."""

    def test_classification_result(self):
        """Test ClassificationResult dataclass."""
        result = ClassificationResult(
            is_healthcare=True,
            confidence=0.92,
            reasoning="Clear medical context",
            tokens_used=150,
            cost_usd=0.002,
        )

        assert result.is_healthcare is True
        assert result.confidence == 0.92
        assert result.reasoning == "Clear medical context"
        assert result.tokens_used == 150
        assert result.cost_usd == 0.002

    def test_extraction_result(self):
        """Test ExtractionResult dataclass."""
        result = ExtractionResult(
            summary="Patient fell in hospital",
            incident_date="2024-01-15",
            location="General Hospital Ward A",
            parties_involved=["Patient", "Nurse", "Doctor"],
            sequence_of_events=["Patient admitted", "Fall occurred", "Treatment given"],
            coroner_recommendations=["Improve flooring", "Better staffing"],
            healthcare_context={"settings": ["Hospital"], "specialties": ["Emergency"]},
            tokens_used=500,
            cost_usd=0.01,
        )

        assert result.summary == "Patient fell in hospital"
        assert result.incident_date == "2024-01-15"
        assert len(result.parties_involved) == 3
        assert len(result.sequence_of_events) == 3
        assert len(result.coroner_recommendations) == 2
        assert result.healthcare_context["settings"] == ["Hospital"]

    def test_human_factors_result(self):
        """Test HumanFactorsResult dataclass."""
        result = HumanFactorsResult(
            individual_factors=[{"factor": "Fatigue", "severity": "high"}],
            team_factors=[{"factor": "Communication", "severity": "medium"}],
            task_factors=[],
            technology_factors=[],
            environment_factors=[],
            organisational_factors=[{"factor": "Staffing", "severity": "high"}],
            latent_hazards=[{"hazard": "Insufficient rest periods"}],
            improvement_opportunities=[{"recommendation": "Implement shift limits"}],
            tokens_used=800,
            cost_usd=0.02,
        )

        assert len(result.individual_factors) == 1
        assert len(result.team_factors) == 1
        assert len(result.organisational_factors) == 1
        assert len(result.latent_hazards) == 1
        assert len(result.improvement_opportunities) == 1

        # Test to_dict method
        dict_result = result.to_dict()
        assert "individual_factors" in dict_result
        assert "team_factors" in dict_result
        assert dict_result["individual_factors"][0]["factor"] == "Fatigue"

    def test_blog_post_result(self):
        """Test BlogPostResult dataclass."""
        result = BlogPostResult(
            title="Lessons from Hospital Fall",
            content_markdown="# Introduction\n\nContent here",
            excerpt="A patient fell in hospital",
            key_learnings=["Check flooring", "Improve staffing", "Better communication"],
            tags=["falls", "hospital", "safety"],
            tokens_used=1200,
            cost_usd=0.03,
        )

        assert result.title == "Lessons from Hospital Fall"
        assert "# Introduction" in result.content_markdown
        assert len(result.key_learnings) == 3
        assert len(result.tags) == 3

    def test_analysis_pipeline_result_success(self):
        """Test AnalysisPipelineResult success property."""
        result = AnalysisPipelineResult(
            classification=ClassificationResult(
                is_healthcare=True,
                confidence=0.9,
                reasoning="Test",
                tokens_used=100,
                cost_usd=0.001,
            ),
            extraction=ExtractionResult(summary="Test", tokens_used=200, cost_usd=0.002),
            human_factors=HumanFactorsResult(tokens_used=300, cost_usd=0.003),
            blog_post=BlogPostResult(
                title="Test",
                content_markdown="# Test",
                excerpt="Test",
                key_learnings=["Test"],
                tags=["test"],
                tokens_used=400,
                cost_usd=0.004,
            ),
        )

        assert result.success is True

    def test_analysis_pipeline_result_failure(self):
        """Test AnalysisPipelineResult with errors."""
        result = AnalysisPipelineResult(
            errors=["Classification failed", "API error"],
        )

        assert result.success is False

    def test_analysis_pipeline_result_total_tokens(self):
        """Test total_tokens property calculation."""
        result = AnalysisPipelineResult(
            classification=ClassificationResult(
                is_healthcare=True,
                confidence=0.9,
                reasoning="Test",
                tokens_used=100,
                cost_usd=0.001,
            ),
            extraction=ExtractionResult(summary="Test", tokens_used=200, cost_usd=0.002),
            human_factors=HumanFactorsResult(tokens_used=300, cost_usd=0.003),
            blog_post=BlogPostResult(
                title="Test",
                content_markdown="Test",
                excerpt="Test",
                key_learnings=[],
                tags=[],
                tokens_used=400,
                cost_usd=0.004,
            ),
        )

        assert result.total_tokens == 1000  # 100 + 200 + 300 + 400

    def test_analysis_pipeline_result_total_cost(self):
        """Test total_cost_usd property calculation."""
        result = AnalysisPipelineResult(
            classification=ClassificationResult(
                is_healthcare=True,
                confidence=0.9,
                reasoning="Test",
                tokens_used=100,
                cost_usd=0.001,
            ),
            extraction=ExtractionResult(summary="Test", tokens_used=200, cost_usd=0.002),
            human_factors=HumanFactorsResult(tokens_used=300, cost_usd=0.003),
            blog_post=BlogPostResult(
                title="Test",
                content_markdown="Test",
                excerpt="Test",
                key_learnings=[],
                tags=[],
                tokens_used=400,
                cost_usd=0.004,
            ),
        )

        assert result.total_cost_usd == 0.01  # 0.001 + 0.002 + 0.003 + 0.004


# =============================================================================
# Test Analysis Pipeline
# =============================================================================

class TestAnalysisPipeline:
    """Tests for AnalysisPipeline."""

    def test_parse_json_direct(self):
        """Test parsing JSON directly."""
        pipeline = AnalysisPipeline(client=MagicMock())

        json_str = '{"key": "value", "number": 42}'
        result = pipeline._parse_json(json_str)

        assert result == {"key": "value", "number": 42}

    def test_parse_json_from_markdown_code_block(self):
        """Test extracting JSON from markdown code block."""
        pipeline = AnalysisPipeline(client=MagicMock())

        content = """
Here is the result:

```json
{
    "is_healthcare": true,
    "confidence": 0.95
}
```
"""
        result = pipeline._parse_json(content)

        assert result == {"is_healthcare": True, "confidence": 0.95}

    def test_parse_json_from_markdown_without_language(self):
        """Test extracting JSON from code block without language specifier."""
        pipeline = AnalysisPipeline(client=MagicMock())

        content = """
```
{"status": "success", "count": 5}
```
"""
        result = pipeline._parse_json(content)

        assert result == {"status": "success", "count": 5}

    def test_parse_json_with_regex_fallback(self):
        """Test extracting JSON using regex fallback."""
        pipeline = AnalysisPipeline(client=MagicMock())

        content = """
Some text before the JSON object.
{"extracted": true, "method": "regex"}
And some text after.
"""
        result = pipeline._parse_json(content)

        assert result == {"extracted": True, "method": "regex"}

    def test_parse_json_invalid(self):
        """Test parsing invalid JSON returns empty dict."""
        pipeline = AnalysisPipeline(client=MagicMock())

        content = "This is not JSON at all"
        result = pipeline._parse_json(content)

        assert result == {}

    @pytest.mark.asyncio
    async def test_classify(self, finding_factory):
        """Test classification stage with mocked LLM response."""
        mock_client = MagicMock()
        mock_response = LLMResponse(
            content='{"is_healthcare": true, "confidence": 0.92, "reasoning": "Clear medical context"}',
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.002,
        )
        mock_client.complete = AsyncMock(return_value=mock_response)

        pipeline = AnalysisPipeline(client=mock_client)
        finding = finding_factory(
            title="Hospital Incident",
            content_text="Patient fell in hospital ward",
        )

        result = await pipeline._classify(finding)

        assert result.is_healthcare is True
        assert result.confidence == 0.92
        assert result.reasoning == "Clear medical context"
        assert result.tokens_used == 150  # 100 + 50
        assert result.cost_usd == 0.002

    @pytest.mark.asyncio
    async def test_extract(self):
        """Test extraction stage with mocked LLM response."""
        mock_client = MagicMock()
        mock_response = LLMResponse(
            content=json.dumps({
                "summary": "Patient fell in ward",
                "incident_date": "2024-01-15",
                "location": "General Hospital",
                "parties_involved": ["Patient", "Nurse"],
                "sequence_of_events": ["Admission", "Fall", "Treatment"],
                "coroner_recommendations": ["Improve flooring"],
                "healthcare_context": {"settings": ["Hospital"], "specialties": ["General"]},
            }),
            tokens_input=200,
            tokens_output=300,
            cost_usd=0.01,
        )
        mock_client.complete = AsyncMock(return_value=mock_response)

        pipeline = AnalysisPipeline(client=mock_client)
        result = await pipeline._extract("Test content")

        assert result.summary == "Patient fell in ward"
        assert result.incident_date == "2024-01-15"
        assert len(result.parties_involved) == 2
        assert len(result.sequence_of_events) == 3
        assert result.tokens_used == 500

    @pytest.mark.asyncio
    async def test_analyse_human_factors(self):
        """Test human factors analysis stage."""
        mock_client = MagicMock()
        mock_response = LLMResponse(
            content=json.dumps({
                "individual_factors": [{"factor": "Fatigue", "severity": "high"}],
                "team_factors": [{"factor": "Communication", "severity": "medium"}],
                "task_factors": [],
                "technology_factors": [],
                "environment_factors": [],
                "organisational_factors": [{"factor": "Staffing", "severity": "high"}],
                "latent_hazards": [{"hazard": "Understaffing"}],
                "improvement_opportunities": [{"recommendation": "Increase staff"}],
            }),
            tokens_input=400,
            tokens_output=600,
            cost_usd=0.02,
        )
        mock_client.complete = AsyncMock(return_value=mock_response)

        pipeline = AnalysisPipeline(client=mock_client)
        result = await pipeline._analyse_human_factors("Content", "Summary")

        assert len(result.individual_factors) == 1
        assert len(result.team_factors) == 1
        assert len(result.organisational_factors) == 1
        assert len(result.latent_hazards) == 1
        assert len(result.improvement_opportunities) == 1
        assert result.tokens_used == 1000

    @pytest.mark.asyncio
    async def test_generate_blog(self):
        """Test blog generation stage."""
        mock_client = MagicMock()
        mock_response = LLMResponse(
            content=json.dumps({
                "title": "Lessons from a Hospital Fall",
                "content_markdown": "# Introduction\n\nA patient fell...",
                "excerpt": "A case study of a hospital fall",
                "key_learnings": ["Check flooring", "Improve communication", "Review staffing"],
                "tags": ["falls", "hospital", "safety"],
            }),
            tokens_input=500,
            tokens_output=800,
            cost_usd=0.03,
        )
        mock_client.complete = AsyncMock(return_value=mock_response)

        extraction = ExtractionResult(summary="Test summary", tokens_used=0, cost_usd=0.0)
        human_factors = HumanFactorsResult(
            improvement_opportunities=[
                {"recommendation": "Improve staffing"},
                {"recommendation": "Better communication"},
            ],
            tokens_used=0,
            cost_usd=0.0,
        )

        pipeline = AnalysisPipeline(client=mock_client)
        result = await pipeline._generate_blog(extraction, human_factors)

        assert result.title == "Lessons from a Hospital Fall"
        assert "# Introduction" in result.content_markdown
        assert len(result.key_learnings) == 3
        assert len(result.tags) == 3
        assert result.tokens_used == 1300

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, finding_factory, mock_settings):
        """Test full analysis pipeline with all stages."""
        mock_client = MagicMock()

        # Mock responses for each stage
        classify_response = LLMResponse(
            content='{"is_healthcare": true, "confidence": 0.95, "reasoning": "Medical"}',
            tokens_input=50,
            tokens_output=25,
            cost_usd=0.001,
        )

        extract_response = LLMResponse(
            content=json.dumps({
                "summary": "Test summary",
                "healthcare_context": {},
            }),
            tokens_input=100,
            tokens_output=100,
            cost_usd=0.005,
        )

        hf_response = LLMResponse(
            content=json.dumps({
                "individual_factors": [],
                "team_factors": [],
                "task_factors": [],
                "technology_factors": [],
                "environment_factors": [],
                "organisational_factors": [],
                "latent_hazards": [],
                "improvement_opportunities": [{"recommendation": "Test"}],
            }),
            tokens_input=200,
            tokens_output=200,
            cost_usd=0.01,
        )

        blog_response = LLMResponse(
            content=json.dumps({
                "title": "Test Blog",
                "content_markdown": "# Test",
                "excerpt": "Test excerpt",
                "key_learnings": ["Learning 1"],
                "tags": ["test"],
            }),
            tokens_input=300,
            tokens_output=300,
            cost_usd=0.015,
        )

        mock_client.complete = AsyncMock(
            side_effect=[classify_response, extract_response, hf_response, blog_response]
        )

        mock_settings.llm_temperature_analysis = 0.3
        mock_settings.llm_temperature_creative = 0.7

        pipeline = AnalysisPipeline(client=mock_client)
        finding = finding_factory(
            title="Test Finding",
            content_text="Test content for analysis",
        )

        result = await pipeline.analyse(finding, skip_classification=False)

        assert result.success is True
        assert result.classification is not None
        assert result.classification.is_healthcare is True
        assert result.extraction is not None
        assert result.human_factors is not None
        assert result.blog_post is not None
        assert result.total_tokens > 0
        assert result.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_pipeline_non_healthcare_early_exit(self, finding_factory):
        """Test pipeline exits early for non-healthcare findings."""
        mock_client = MagicMock()
        classify_response = LLMResponse(
            content='{"is_healthcare": false, "confidence": 0.85, "reasoning": "Not medical"}',
            tokens_input=50,
            tokens_output=25,
            cost_usd=0.001,
        )
        mock_client.complete = AsyncMock(return_value=classify_response)

        pipeline = AnalysisPipeline(client=mock_client)
        finding = finding_factory(
            title="Car Accident",
            content_text="Traffic incident on highway",
        )

        result = await pipeline.analyse(finding, skip_classification=False)

        # Should have classification but no other stages
        assert result.classification is not None
        assert result.classification.is_healthcare is False
        assert result.extraction is None
        assert result.human_factors is None
        assert result.blog_post is None
        assert result.success is False  # No blog post means not successful

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, finding_factory):
        """Test pipeline handles errors gracefully."""
        mock_client = MagicMock()
        mock_client.complete = AsyncMock(side_effect=Exception("API Error"))

        pipeline = AnalysisPipeline(client=mock_client)
        finding = finding_factory(
            title="Test",
            content_text="Test content",
        )

        result = await pipeline.analyse(finding, skip_classification=False)

        assert result.success is False
        assert len(result.errors) > 0
        assert "API Error" in result.errors[0]
