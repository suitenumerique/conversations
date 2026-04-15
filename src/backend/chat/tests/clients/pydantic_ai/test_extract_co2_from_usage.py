"""Tests for _extract_co2_from_usage in chat.clients.pydantic_ai."""
# pylint: disable=protected-access

import pytest
from pydantic_ai import RunUsage

from chat.clients.pydantic_ai import _extract_co2_from_usage

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
    result = _extract_co2_from_usage(usage)
    assert result == pytest.approx(expected_kg_co2, rel=1e-9)
