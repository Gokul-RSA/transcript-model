"""
Explainability — Reasoning trace builder.

Maintains a mutable list of ReasoningStep objects during a single reasoning
pass and assembles the final ExplainabilityMetadata at the end.
"""

from __future__ import annotations

import time
import uuid
from typing import List

from clinical_intelligence.rule_engine.models import (
    ExplainabilityMetadata,
    ReasoningStep,
)


class ExplainabilityTracer:
    """
    Collects reasoning steps during a single engine pass.

    Usage::

        tracer = ExplainabilityTracer()
        tracer.start()
        tracer.add_step(
            component="Matcher",
            description="Matched 'chest pain' to ACS with weight 0.35",
            input_facts=["chest pain (present, confidence=High)"],
            output="candidate: acs, raw_match_score += 0.35",
            confidence_delta=0.35,
        )
        metadata = tracer.finish(rules_evaluated=120, rules_matched=14, loaded_files=[...])
    """

    def __init__(self) -> None:
        self._steps: List[ReasoningStep] = []
        self._start_time: float = 0.0
        self._rules_evaluated: int = 0
        self._rules_matched: int = 0

    def start(self) -> None:
        """Record the start wall-clock time."""
        self._start_time = time.monotonic()
        self._steps.clear()
        self._rules_evaluated = 0
        self._rules_matched = 0

    def add_step(
        self,
        *,
        component: str,
        description: str,
        input_facts: List[str],
        output: str,
        confidence_delta: float = 0.0,
    ) -> None:
        """Append a new reasoning step to the trace."""
        step = ReasoningStep(
            step_id=str(uuid.uuid4())[:8],
            component=component,
            description=description,
            input_facts=input_facts,
            output=output,
            confidence_delta=confidence_delta,
        )
        self._steps.append(step)

    def increment_evaluated(self, n: int = 1) -> None:
        """Increment the count of rules evaluated."""
        self._rules_evaluated += n

    def increment_matched(self, n: int = 1) -> None:
        """Increment the count of rules that produced a match."""
        self._rules_matched += n

    def finish(
        self,
        rules_evaluated: int | None = None,
        rules_matched: int | None = None,
        loaded_files: List[str] | None = None,
    ) -> ExplainabilityMetadata:
        """
        Close the trace and return the final ExplainabilityMetadata.

        Parameters ``rules_evaluated`` and ``rules_matched`` override
        the internally accumulated counters if provided.
        """
        elapsed_ms = (time.monotonic() - self._start_time) * 1000.0
        return ExplainabilityMetadata(
            reasoning_steps=list(self._steps),
            rules_evaluated=rules_evaluated if rules_evaluated is not None else self._rules_evaluated,
            rules_matched=rules_matched if rules_matched is not None else self._rules_matched,
            reasoning_duration_ms=round(elapsed_ms, 2),
            rule_files_loaded=loaded_files or [],
        )
