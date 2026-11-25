"""apqr-toolkit: open-source statistics for Annual Product Quality Reviews."""
from .stats import Spec, capability, control_limits, descriptive, interpret_cpk, out_of_spec, trend_rules

__version__ = "0.1.0"
__all__ = ["Spec", "capability", "control_limits", "descriptive", "interpret_cpk", "out_of_spec", "trend_rules"]
