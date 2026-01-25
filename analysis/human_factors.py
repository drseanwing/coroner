"""
Human Factors Analysis Module

Implements SEIPS 2.0 (Systems Engineering Initiative for Patient Safety)
framework for analyzing human factors in healthcare incidents.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


# =============================================================================
# SEIPS 2.0 Framework Components
# =============================================================================

class SEIPSDomain(str, Enum):
    """SEIPS 2.0 system domains."""
    INDIVIDUAL = "individual"
    TEAM = "team"
    TASK = "task"
    TECHNOLOGY = "technology"
    ENVIRONMENT = "environment"
    ORGANISATIONAL = "organisational"


class Severity(str, Enum):
    """Severity levels for human factors."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class HumanFactor:
    """Single human factor identified in analysis."""
    factor: str
    description: str
    severity: Severity
    domain: SEIPSDomain
    evidence: Optional[str] = None
    affected_scope: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "factor": self.factor,
            "description": self.description,
            "severity": self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "domain": self.domain.value if isinstance(self.domain, SEIPSDomain) else self.domain,
            "evidence": self.evidence,
            "affected_scope": self.affected_scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanFactor":
        """Create from dictionary (database retrieval)."""
        severity = data.get("severity", "low")
        if isinstance(severity, str):
            severity = Severity(severity)

        domain = data.get("domain", "individual")
        if isinstance(domain, str):
            domain = SEIPSDomain(domain)

        return cls(
            factor=data.get("factor", ""),
            description=data.get("description", ""),
            severity=severity,
            domain=domain,
            evidence=data.get("evidence"),
            affected_scope=data.get("affected_scope"),
        )


@dataclass
class LatentHazard:
    """Hidden system vulnerability."""
    hazard: str
    domain: SEIPSDomain
    potential_for_future_harm: str
    detectability: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "hazard": self.hazard,
            "domain": self.domain.value if isinstance(self.domain, SEIPSDomain) else self.domain,
            "potential_for_future_harm": self.potential_for_future_harm,
            "detectability": self.detectability,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LatentHazard":
        """Create from dictionary (database retrieval)."""
        domain = data.get("domain", "individual")
        if isinstance(domain, str):
            domain = SEIPSDomain(domain)

        return cls(
            hazard=data.get("hazard", ""),
            domain=domain,
            potential_for_future_harm=data.get("potential_for_future_harm", ""),
            detectability=data.get("detectability", ""),
        )


@dataclass
class Recommendation:
    """Improvement opportunity."""
    recommendation: str
    target_domain: SEIPSDomain
    implementation_level: str  # local, departmental, organisational, system-wide
    priority: Severity
    existing_evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "recommendation": self.recommendation,
            "target_domain": self.target_domain.value if isinstance(self.target_domain, SEIPSDomain) else self.target_domain,
            "implementation_level": self.implementation_level,
            "priority": self.priority.value if isinstance(self.priority, Severity) else self.priority,
            "existing_evidence": self.existing_evidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recommendation":
        """Create from dictionary (database retrieval)."""
        target_domain = data.get("target_domain", "individual")
        if isinstance(target_domain, str):
            target_domain = SEIPSDomain(target_domain)

        priority = data.get("priority", "low")
        if isinstance(priority, str):
            priority = Severity(priority)

        return cls(
            recommendation=data.get("recommendation", ""),
            target_domain=target_domain,
            implementation_level=data.get("implementation_level", "local"),
            priority=priority,
            existing_evidence=data.get("existing_evidence"),
        )


@dataclass
class HumanFactorsResult:
    """Complete human factors analysis result."""
    # SEIPS domains - each stores list of dicts for backward compatibility
    individual_factors: List[Dict[str, Any]] = field(default_factory=list)
    team_factors: List[Dict[str, Any]] = field(default_factory=list)
    task_factors: List[Dict[str, Any]] = field(default_factory=list)
    technology_factors: List[Dict[str, Any]] = field(default_factory=list)
    environment_factors: List[Dict[str, Any]] = field(default_factory=list)
    organisational_factors: List[Dict[str, Any]] = field(default_factory=list)

    # Additional analysis
    latent_hazards: List[Dict[str, Any]] = field(default_factory=list)
    improvement_opportunities: List[Dict[str, Any]] = field(default_factory=list)

    tokens_used: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "individual_factors": self.individual_factors,
            "team_factors": self.team_factors,
            "task_factors": self.task_factors,
            "technology_factors": self.technology_factors,
            "environment_factors": self.environment_factors,
            "organisational_factors": self.organisational_factors,
            "latent_hazards": self.latent_hazards,
            "improvement_opportunities": self.improvement_opportunities,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanFactorsResult":
        """Create from dictionary (database retrieval)."""
        return cls(
            individual_factors=data.get("individual_factors", []),
            team_factors=data.get("team_factors", []),
            task_factors=data.get("task_factors", []),
            technology_factors=data.get("technology_factors", []),
            environment_factors=data.get("environment_factors", []),
            organisational_factors=data.get("organisational_factors", []),
            latent_hazards=data.get("latent_hazards", []),
            improvement_opportunities=data.get("improvement_opportunities", []),
            tokens_used=data.get("tokens_used", 0),
            cost_usd=data.get("cost_usd", 0.0),
        )

    def get_all_factors(self) -> List[Dict[str, Any]]:
        """Get all factors across all domains."""
        return (
            self.individual_factors
            + self.team_factors
            + self.task_factors
            + self.technology_factors
            + self.environment_factors
            + self.organisational_factors
        )

    def get_high_severity_factors(self) -> List[Dict[str, Any]]:
        """Get all high-severity factors across domains."""
        all_factors = self.get_all_factors()
        return [
            f for f in all_factors
            if f.get("severity") == "high"
        ]

    def get_factors_by_domain(self, domain: SEIPSDomain) -> List[Dict[str, Any]]:
        """Get factors for a specific SEIPS domain."""
        domain_map = {
            SEIPSDomain.INDIVIDUAL: self.individual_factors,
            SEIPSDomain.TEAM: self.team_factors,
            SEIPSDomain.TASK: self.task_factors,
            SEIPSDomain.TECHNOLOGY: self.technology_factors,
            SEIPSDomain.ENVIRONMENT: self.environment_factors,
            SEIPSDomain.ORGANISATIONAL: self.organisational_factors,
        }
        return domain_map.get(domain, [])

    def severity_summary(self) -> Dict[str, int]:
        """Count factors by severity level."""
        summary = {"high": 0, "medium": 0, "low": 0}

        for factor in self.get_all_factors():
            severity = factor.get("severity", "low")
            if severity in summary:
                summary[severity] += 1

        return summary

    def domain_summary(self) -> Dict[str, int]:
        """Count factors by SEIPS domain."""
        return {
            "individual": len(self.individual_factors),
            "team": len(self.team_factors),
            "task": len(self.task_factors),
            "technology": len(self.technology_factors),
            "environment": len(self.environment_factors),
            "organisational": len(self.organisational_factors),
        }


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "SEIPSDomain",
    "Severity",
    "HumanFactor",
    "LatentHazard",
    "Recommendation",
    "HumanFactorsResult",
]
