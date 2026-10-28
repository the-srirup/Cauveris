"""
Physical unit normalization and dimensional validation.
"""

from typing import Tuple, Optional

TIME_UNITS = {
    "ns": 1e-6,
    "us": 1e-3,
    "ms": 1.0,
    "s": 1000.0,
    "sec": 1000.0,
    "second": 1000.0,
    "seconds": 1000.0,
    "m": 60000.0,
    "min": 60000.0,
}

DATA_SIZE_UNITS = {
    "b": 1e-6,
    "bytes": 1e-6,
    "kb": 1e-3,
    "kib": 1.024e-3,
    "mb": 1.0,
    "mib": 1.048576,
    "gb": 1000.0,
    "gib": 1073.741824,
}

FREQUENCY_UNITS = {
    "hz": 1.0,
    "khz": 1000.0,
    "mhz": 1e6,
}

DISTANCE_UNITS = {
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
}

DIMENSIONS = {
    "time": (TIME_UNITS, "ms"),
    "data_size": (DATA_SIZE_UNITS, "MB"),
    "frequency": (FREQUENCY_UNITS, "Hz"),
    "distance": (DISTANCE_UNITS, "m"),
}


def get_dimension(unit: str) -> Optional[str]:
    u = unit.lower().strip()
    for dim_name, (units_dict, _) in DIMENSIONS.items():
        if u in units_dict:
            return dim_name
    return None


def normalize_value(value: float, unit: str) -> Tuple[float, str]:
    """
    Normalizes a physical value to the canonical unit for its dimension.
    Raises ValueError if incompatible.
    """
    u = unit.lower().strip()
    dim = get_dimension(u)
    if not dim:
        # Unknown/dimensionless unit, return as-is
        return value, unit

    units_dict, canonical_unit = DIMENSIONS[dim]
    factor = units_dict[u]
    canonical_val = value * factor
    return round(canonical_val, 4), canonical_unit


def are_units_compatible(unit_a: str, unit_b: str) -> bool:
    dim_a = get_dimension(unit_a)
    dim_b = get_dimension(unit_b)
    if dim_a is not None and dim_b is not None:
        return dim_a == dim_b
    return unit_a.lower().strip() == unit_b.lower().strip()
