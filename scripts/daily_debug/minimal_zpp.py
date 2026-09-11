#!/usr/bin/env python3
"""Minimal SIGILL reproducer for sima-ml-kernels develop.261 on non-AVX-512 x86."""
from ml_kernels.np_operators_helpers import zpp_multiply_add

print(zpp_multiply_add(1.0, 1.0, 1.0), flush=True)
