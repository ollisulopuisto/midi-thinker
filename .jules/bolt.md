# Bolt's Performance Journal

This journal records critical learnings, architectural insights, and performance patterns discovered in this codebase.

## 2026-03-30 - Repeated Mapping Construction in MIDI Generation Loops
**Learning:** `drum_name_to_midi` was rebuilding a 35-item tuple-keyed dictionary and performing linear substring scans on every note during MIDI export. In sequences with hundreds to thousands of drum hits, extracting exact match lookups into a module-level dictionary provides ~40x speedup ($O(1)$ fast path) while maintaining fallback compatibility.
**Action:** When mapping human-readable instrument or note labels to MIDI numbers in batch generation paths, prefer pre-computed module-level hash tables with $O(1)$ fast paths rather than inline reallocated dictionaries with linear loops.

## 2026-11-03 - Memoization for Guitar Fretboard Search in ASCII Tab Generation
**Learning:** `get_best_fret` in `studio.py` loops through 6 strings, computes candidate frets, applies multiple scoring conditionals, and sorts candidate lists for every guitar note and chord hit. Because the search space is bounded by MIDI pitches and 6 string states (< 500 combinations), memoizing the function with `@lru_cache(maxsize=512)` delivers a ~13x speedup on repeated note/chord tab generation.
**Action:** Pure heuristic note-placement and fretboard mapping functions with small input domains should be memoized with `@lru_cache` to eliminate redundant scoring and sorting in rendering loops.
