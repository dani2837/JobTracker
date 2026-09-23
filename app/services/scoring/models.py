from dataclasses import asdict, dataclass, field


@dataclass
class Component:
    points: int
    positives: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    unmet: dict[str, str] = field(default_factory=dict)
    penalties: dict[str, int] = field(default_factory=dict)
    facts: dict = field(default_factory=dict)


@dataclass
class ScoreResult:
    score: int
    classification: str
    excluded: bool
    exclusion_reason: str | None
    score_breakdown: dict[str, int]
    warnings: list[str]
    positive_signals: list[str]
    unmet_requirements: list[str]
    penalties: dict[str, int]
    facts: dict
    weights: dict[str, int]
    profile_hash: str
    engine_version: str

    def to_dict(self) -> dict:
        return asdict(self)
