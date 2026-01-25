"""
Patient Safety Monitor - Analysis Package

This package provides LLM-powered analysis of coronial findings.

Modules:
    llm_client: Unified LLM client interface (Claude, OpenAI)
    analyser: Multi-stage analysis pipeline
    processor: Batch processing of findings
    
Usage:
    from analysis import AnalysisPipeline, AnalysisProcessor
    
    # Single finding analysis
    pipeline = AnalysisPipeline()
    result = await pipeline.analyse(finding)
    
    # Batch processing
    processor = AnalysisProcessor()
    stats = await processor.process_all_pending(limit=10)
"""

from analysis.llm_client import (
    BaseLLMClient,
    ClaudeClient,
    LLMClientFactory,
    LLMConfig,
    LLMResponse,
)
from analysis.analyser import (
    AnalysisPipeline,
    AnalysisPipelineResult,
    ClassificationResult,
    ExtractionResult,
    BlogPostResult,
    PromptTemplateLoader,
)
from analysis.human_factors import (
    HumanFactorsResult,
    SEIPSDomain,
    Severity,
    HumanFactor,
    LatentHazard,
    Recommendation,
)
from analysis.processor import (
    AnalysisProcessor,
    ProcessingStats,
)

__all__ = [
    # LLM Client
    "BaseLLMClient",
    "ClaudeClient",
    "LLMClientFactory",
    "LLMConfig",
    "LLMResponse",
    # Pipeline
    "AnalysisPipeline",
    "AnalysisPipelineResult",
    "ClassificationResult",
    "ExtractionResult",
    "BlogPostResult",
    "PromptTemplateLoader",
    # Human Factors
    "HumanFactorsResult",
    "SEIPSDomain",
    "Severity",
    "HumanFactor",
    "LatentHazard",
    "Recommendation",
    # Processor
    "AnalysisProcessor",
    "ProcessingStats",
]
