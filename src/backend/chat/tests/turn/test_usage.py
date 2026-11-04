"""Tests for chat.turn.usage.AgentUsage."""

import pytest
from pydantic_ai import RunUsage

from chat.turn.usage import AgentUsage

CO2_SCALE = 10**20


@pytest.mark.parametrize(
    ("usage", "expected_kg_co2"),
    (
        [RunUsage(details={"co2_impact_factor_20": int(1.23e-9 * CO2_SCALE)}), 1.23e-9],
        [RunUsage(details={"other_metric": 36}), 0.0],
        [RunUsage(details={"co2_impact_factor_20": 0.0}), 0.0],
    ),
)
def test_extract_co2_from_usage(usage, expected_kg_co2):
    """Typical Albert value: integer-scaled CO2 is divided back to kgCO2eq."""
    result = AgentUsage.from_run(usage).co2_impact
    assert result == pytest.approx(expected_kg_co2, rel=1e-9)
