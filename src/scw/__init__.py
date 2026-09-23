"""SCW package: deterministic offline sharia-compliance workbook engine."""
from .engine import (ENGINE_VERSION, REFERENCE_VECTOR_ENGINE_VERSION,
                     VERDICTS, assert_engine_compatible, assert_input_bound,
                     check_pack_policy, evaluate)
from .canonical import canon, sha, load_json, dump_pretty

__all__ = ["ENGINE_VERSION", "REFERENCE_VECTOR_ENGINE_VERSION", "VERDICTS",
           "assert_engine_compatible", "assert_input_bound",
           "check_pack_policy", "evaluate", "canon", "sha", "load_json",
           "dump_pretty"]
