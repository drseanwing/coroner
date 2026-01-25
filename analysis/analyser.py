"""
Patient Safety Monitor - Analysis Pipeline

Multi-stage LLM analysis for coronial findings.
Handles classification, extraction, human factors analysis, and blog generation.

Stages:
    1. Classification: Healthcare-related or not
    2. Extraction: Structured data from content
    3. Human Factors: SEIPS framework analysis
    4. Blog Generation: Reader-friendly content

Usage:
    from analysis.analyser import AnalysisPipeline
    
    pipeline = AnalysisPipeline()
    result = await pipeline.analyse(finding)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from analysis.llm_client import (
    BaseLLMClient,
    LLMClientFactory,
    LLMConfig,
    LLMResponse,
)
from config.settings import get_settings
from database.models import Finding


logger = logging.getLogger(__name__)


# =============================================================================
# Result Data Classes
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of healthcare classification."""
    
    is_healthcare: bool
    confidence: float
    reasoning: str
    tokens_used: int = 0
    cost_usd: float = 0.0


@dataclass
class ExtractionResult:
    """Result of structured data extraction."""
    
    summary: str
    incident_date: Optional[str] = None
    location: Optional[str] = None
    parties_involved: list[str] = field(default_factory=list)
    sequence_of_events: list[str] = field(default_factory=list)
    coroner_recommendations: list[str] = field(default_factory=list)
    healthcare_context: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    cost_usd: float = 0.0


@dataclass
class HumanFactorsResult:
    """Result of SEIPS human factors analysis."""
    
    # SEIPS domains
    individual_factors: list[dict[str, Any]] = field(default_factory=list)
    team_factors: list[dict[str, Any]] = field(default_factory=list)
    task_factors: list[dict[str, Any]] = field(default_factory=list)
    technology_factors: list[dict[str, Any]] = field(default_factory=list)
    environment_factors: list[dict[str, Any]] = field(default_factory=list)
    organisational_factors: list[dict[str, Any]] = field(default_factory=list)
    
    # Additional analysis
    latent_hazards: list[dict[str, Any]] = field(default_factory=list)
    improvement_opportunities: list[dict[str, Any]] = field(default_factory=list)
    
    tokens_used: int = 0
    cost_usd: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "individual_factors": self.individual_factors,
            "team_factors": self.team_factors,
            "task_factors": self.task_factors,
            "technology_factors": self.technology_factors,
            "environment_factors": self.environment_factors,
            "organisational_factors": self.organisational_factors,
        }


@dataclass
class BlogPostResult:
    """Result of blog post generation."""
    
    title: str
    content_markdown: str
    excerpt: str
    key_learnings: list[str]
    tags: list[str]
    tokens_used: int = 0
    cost_usd: float = 0.0


@dataclass
class AnalysisPipelineResult:
    """Complete result from the analysis pipeline."""
    
    # Stage results
    classification: Optional[ClassificationResult] = None
    extraction: Optional[ExtractionResult] = None
    human_factors: Optional[HumanFactorsResult] = None
    blog_post: Optional[BlogPostResult] = None
    
    # Aggregate stats
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if pipeline completed successfully."""
        return len(self.errors) == 0 and self.blog_post is not None
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used across all stages."""
        total = 0
        if self.classification:
            total += self.classification.tokens_used
        if self.extraction:
            total += self.extraction.tokens_used
        if self.human_factors:
            total += self.human_factors.tokens_used
        if self.blog_post:
            total += self.blog_post.tokens_used
        return total
    
    @property
    def total_cost_usd(self) -> float:
        """Total cost in USD."""
        total = 0.0
        if self.classification:
            total += self.classification.cost_usd
        if self.extraction:
            total += self.extraction.cost_usd
        if self.human_factors:
            total += self.human_factors.cost_usd
        if self.blog_post:
            total += self.blog_post.cost_usd
        return total


# =============================================================================
# Prompt Template Loader
# =============================================================================

class PromptTemplateLoader:
    """
    Loads and manages prompt templates.
    
    Templates are stored as text files in config/prompts/ directory.
    Supports variable substitution using {variable_name} syntax.
    """
    
    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the loader.
        
        Args:
            templates_dir: Directory containing templates
        """
        if templates_dir is None:
            settings = get_settings()
            templates_dir = settings.project_root / "config" / "prompts"
        
        self.templates_dir = Path(templates_dir)
        self._cache: dict[str, str] = {}
    
    def load(self, template_name: str, **variables: Any) -> str:
        """
        Load a template and substitute variables.
        
        Args:
            template_name: Name of template file (without extension)
            **variables: Variables to substitute
            
        Returns:
            Rendered template string
        """
        # Check cache
        if template_name not in self._cache:
            template_path = self.templates_dir / f"{template_name}.txt"
            
            if not template_path.exists():
                logger.warning(f"Template not found: {template_path}")
                # Return a default prompt
                return self._get_default_prompt(template_name, variables)
            
            self._cache[template_name] = template_path.read_text()
        
        template = self._cache[template_name]
        
        # Substitute variables
        for key, value in variables.items():
            template = template.replace(f"{{{key}}}", str(value))
        
        return template
    
    def _get_default_prompt(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> str:
        """Get a default prompt when template is missing."""
        defaults = {
            "classify_healthcare": """
You are a medical classification expert. Analyze the following finding and determine if it is related to healthcare delivery.

Finding:
{content}

Respond with a JSON object containing:
- is_healthcare: boolean
- confidence: float between 0 and 1
- reasoning: brief explanation
""",
            "extract_content": """
You are an expert at extracting structured information from medical and coronial documents.

Document:
{content}

Extract and return a JSON object with:
- summary: Brief summary of the incident
- incident_date: Date of incident if mentioned
- location: Location if mentioned
- parties_involved: List of parties
- sequence_of_events: List of key events
- coroner_recommendations: List of recommendations
- healthcare_context: Object with settings and specialties arrays
""",
            "analyse_human_factors": """
You are an expert in healthcare human factors analysis using the SEIPS 2.0 framework.

Incident Summary:
{summary}

Content:
{content}

Analyze this incident and identify human factors issues across these domains:
- Individual factors (fatigue, cognitive load, skill, stress)
- Team factors (communication, handover, supervision)
- Task factors (complexity, time pressure, interruptions)
- Technology factors (equipment, usability, documentation)
- Environment factors (physical layout, crowding, resources)
- Organisational factors (staffing, policies, culture)

For each factor found, provide:
- factor: Name of the factor
- description: How it contributed
- severity: high/medium/low

Also identify:
- latent_hazards: Hidden system weaknesses
- improvement_opportunities: Actionable recommendations

Return as a JSON object.
""",
            "generate_blog_post": """
You are a medical writer creating educational content for healthcare professionals.

Summary:
{summary}

Human Factors Analysis:
{human_factors}

Key Learnings:
{key_learnings}

Write a blog post that:
1. Has an engaging, professional title
2. Opens with key takeaways in a highlighted box
3. Explains what happened factually
4. Discusses human factors issues
5. Provides actionable recommendations
6. Uses clear, accessible language

Return as JSON:
- title: string
- content_markdown: full post in markdown
- excerpt: 2-3 sentence preview
- key_learnings: array of 3-5 bullet points
- tags: array of relevant tags
""",
        }
        
        prompt = defaults.get(template_name, "")
        for key, value in variables.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))
        
        return prompt
    
    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()


# =============================================================================
# Analysis Pipeline
# =============================================================================

class AnalysisPipeline:
    """
    Multi-stage analysis pipeline for coronial findings.
    
    Stages:
        1. classify: Determine if healthcare-related
        2. extract: Extract structured data
        3. analyse_human_factors: Apply SEIPS framework
        4. generate_blog: Create reader-friendly content
    """
    
    def __init__(
        self,
        client: Optional[BaseLLMClient] = None,
        template_loader: Optional[PromptTemplateLoader] = None,
    ):
        """
        Initialize the pipeline.
        
        Args:
            client: LLM client (creates default if not provided)
            template_loader: Template loader (creates default if not provided)
        """
        self.client = client or LLMClientFactory.create_default()
        self.templates = template_loader or PromptTemplateLoader()
        self.settings = get_settings()
    
    async def analyse(
        self,
        finding: Finding,
        skip_classification: bool = False,
    ) -> AnalysisPipelineResult:
        """
        Run the full analysis pipeline on a finding.
        
        Args:
            finding: Finding to analyze
            skip_classification: Skip classification if already done
            
        Returns:
            AnalysisPipelineResult with all stage results
        """
        result = AnalysisPipelineResult()
        
        logger.info(
            f"Starting analysis pipeline",
            extra={"finding_id": str(finding.id)},
        )
        
        # Get content
        content = finding.content_text or finding.content_html or ""
        if not content:
            result.errors.append("No content available for analysis")
            return result
        
        try:
            # Stage 1: Classification
            if not skip_classification:
                result.classification = await self._classify(finding)
                
                if not result.classification.is_healthcare:
                    logger.info(
                        "Finding classified as non-healthcare",
                        extra={
                            "finding_id": str(finding.id),
                            "confidence": result.classification.confidence,
                        },
                    )
                    result.completed_at = datetime.utcnow()
                    return result
            
            # Stage 2: Extraction
            result.extraction = await self._extract(content)
            
            # Stage 3: Human Factors Analysis
            result.human_factors = await self._analyse_human_factors(
                content,
                result.extraction.summary,
            )
            
            # Stage 4: Blog Generation
            result.blog_post = await self._generate_blog(
                result.extraction,
                result.human_factors,
            )
            
            result.completed_at = datetime.utcnow()
            
            logger.info(
                "Analysis pipeline completed",
                extra={
                    "finding_id": str(finding.id),
                    "total_tokens": result.total_tokens,
                    "total_cost": result.total_cost_usd,
                },
            )
            
        except Exception as e:
            logger.error(
                f"Analysis pipeline failed",
                extra={"finding_id": str(finding.id), "error": str(e)},
            )
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
        
        return result
    
    async def _classify(self, finding: Finding) -> ClassificationResult:
        """Run healthcare classification."""
        logger.debug("Running classification stage")
        
        content = finding.content_text or finding.content_html or finding.title
        
        prompt = self.templates.load(
            "classify_healthcare",
            content=content[:8000],  # Truncate for context limit
        )
        
        config = LLMConfig(
            temperature=self.settings.llm_temperature_analysis,
            max_tokens=500,
            json_mode=True,
        )
        
        response = await self.client.complete(
            system_prompt="You are a healthcare classification expert. Always respond with valid JSON.",
            user_prompt=prompt,
            config=config,
        )
        
        # Parse response
        data = self._parse_json(response.content)
        
        return ClassificationResult(
            is_healthcare=data.get("is_healthcare", False),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            tokens_used=response.total_tokens,
            cost_usd=response.cost_usd,
        )
    
    async def _extract(self, content: str) -> ExtractionResult:
        """Extract structured data from content."""
        logger.debug("Running extraction stage")
        
        prompt = self.templates.load(
            "extract_content",
            content=content[:12000],
        )
        
        config = LLMConfig(
            temperature=self.settings.llm_temperature_analysis,
            max_tokens=2000,
            json_mode=True,
        )
        
        response = await self.client.complete(
            system_prompt="You are an expert at extracting structured information. Always respond with valid JSON.",
            user_prompt=prompt,
            config=config,
        )
        
        data = self._parse_json(response.content)
        
        return ExtractionResult(
            summary=data.get("summary", ""),
            incident_date=data.get("incident_date"),
            location=data.get("location"),
            parties_involved=data.get("parties_involved", []),
            sequence_of_events=data.get("sequence_of_events", []),
            coroner_recommendations=data.get("coroner_recommendations", []),
            healthcare_context=data.get("healthcare_context", {}),
            tokens_used=response.total_tokens,
            cost_usd=response.cost_usd,
        )
    
    async def _analyse_human_factors(
        self,
        content: str,
        summary: str,
    ) -> HumanFactorsResult:
        """Run SEIPS human factors analysis."""
        logger.debug("Running human factors analysis stage")
        
        prompt = self.templates.load(
            "analyse_human_factors",
            content=content[:10000],
            summary=summary,
        )
        
        config = LLMConfig(
            temperature=self.settings.llm_temperature_analysis,
            max_tokens=3000,
            json_mode=True,
        )
        
        response = await self.client.complete(
            system_prompt="You are a healthcare human factors expert. Analyze using SEIPS 2.0 framework. Always respond with valid JSON.",
            user_prompt=prompt,
            config=config,
        )
        
        data = self._parse_json(response.content)
        
        return HumanFactorsResult(
            individual_factors=data.get("individual_factors", []),
            team_factors=data.get("team_factors", []),
            task_factors=data.get("task_factors", []),
            technology_factors=data.get("technology_factors", []),
            environment_factors=data.get("environment_factors", []),
            organisational_factors=data.get("organisational_factors", []),
            latent_hazards=data.get("latent_hazards", []),
            improvement_opportunities=data.get("improvement_opportunities", []),
            tokens_used=response.total_tokens,
            cost_usd=response.cost_usd,
        )
    
    async def _generate_blog(
        self,
        extraction: ExtractionResult,
        human_factors: HumanFactorsResult,
    ) -> BlogPostResult:
        """Generate blog post content."""
        logger.debug("Running blog generation stage")
        
        # Format human factors for prompt
        hf_summary = json.dumps(human_factors.to_dict(), indent=2)
        
        # Create key learnings from recommendations
        key_learnings = []
        for opp in human_factors.improvement_opportunities[:5]:
            if isinstance(opp, dict):
                key_learnings.append(opp.get("recommendation", str(opp)))
            else:
                key_learnings.append(str(opp))
        
        prompt = self.templates.load(
            "generate_blog_post",
            summary=extraction.summary,
            human_factors=hf_summary[:4000],
            key_learnings="\n".join(f"- {l}" for l in key_learnings),
        )
        
        config = LLMConfig(
            temperature=self.settings.llm_temperature_creative,
            max_tokens=4000,
            json_mode=True,
        )
        
        response = await self.client.complete(
            system_prompt="You are a medical writer. Create educational content for healthcare professionals. Always respond with valid JSON.",
            user_prompt=prompt,
            config=config,
        )
        
        data = self._parse_json(response.content)
        
        return BlogPostResult(
            title=data.get("title", ""),
            content_markdown=data.get("content_markdown", ""),
            excerpt=data.get("excerpt", ""),
            key_learnings=data.get("key_learnings", key_learnings),
            tags=data.get("tags", []),
            tokens_used=response.total_tokens,
            cost_usd=response.cost_usd,
        )
    
    def _parse_json(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in content
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        logger.warning("Failed to parse JSON from LLM response")
        return {}


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "AnalysisPipeline",
    "AnalysisPipelineResult",
    "ClassificationResult",
    "ExtractionResult",
    "HumanFactorsResult",
    "BlogPostResult",
    "PromptTemplateLoader",
]
