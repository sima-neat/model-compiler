#!/usr/bin/env python3
"""Compatibility wrapper for the packaged ResNet-50 PTQ example."""

import runpy
from pathlib import Path


target = Path(__file__).resolve().parent / "resnet50-ptq" / "compile_first_model.py"
runpy.run_path(str(target), run_name="__main__")
