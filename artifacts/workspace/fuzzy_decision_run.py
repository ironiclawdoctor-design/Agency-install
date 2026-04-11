#!/usr/bin/env python3
"""
Fuzzy Logic Decision: Should we batch download movie transcripts?
Binary choice: YES (batch download) vs NO (use only Tangled)
"""

def triangular(x, a, b, c):
    """Triangular membership function."""
    if x 