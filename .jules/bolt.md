# Bolt's Performance Journal

This journal records critical learnings, architectural insights, and performance patterns discovered in this codebase.

## 2026-03-30 - Repeated Mapping Construction in MIDI Generation Loops
**Learning:** `drum_name_to_midi` was rebuilding a 35-item tuple-keyed dictionary and performing linear substring scans on every note during MIDI export. In sequences with hundreds to thousands of drum hits, extracting exact match lookups into a module-level dictionary provides ~40x speedup ($O(1)$ fast path) while maintaining fallback compatibility.
**Action:** When mapping human-readable instrument or note labels to MIDI numbers in batch generation paths, prefer pre-computed module-level hash tables with $O(1)$ fast paths rather than inline reallocated dictionaries with linear loops.
