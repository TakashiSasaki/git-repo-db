"""Convenience reproduction wrapper for the actual pristine743 launch.

The recorded invocation used run_diagnostic.py with these two environment
settings; see clean743-launch.json and the archived exact driver/plugin bytes.
"""
import os
from pathlib import Path
import runpy

os.environ['REVIEW_SOURCE_ROOT']='/workspace/i6a-review-clean'
os.environ['REVIEW_DIAGNOSTIC_COHORT']='743'
runpy.run_path(str(Path(__file__).resolve().with_name('run_diagnostic.py')),run_name='__main__')
