#!/usr/bin/env python3
"""Backward-compatible entry: delegates to test_prove (deterministic ship). """
import sys
from test_prove import main

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("GOLDEN_E2E_FAIL", e, file=sys.stderr)
        sys.exit(1)
