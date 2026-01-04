# Imagine Music

## Introduction

This project aims to create a tool that leverages the Google Gemini API to help you arrange music: input a simple MIDI melody or chord idea, Gemini will help you expand on this, then saving the result as a MIDI file and importing that into your favorite DAW.

## Current Functionality

*   **MIDI Input:** Loads standard MIDI files (`.mid`), supporting both Type 0 and Type 1.
*   **Deep Analysis:** Extracts all notes, instruments, and meta-message changes (tempo, key, time signature).
*   **Structural Awareness:** Uses Gemini to identify song sections (e.g., Intro, Verse, Chorus) and musical style.
*   **Multi-Track Generation:** 
    *   **Extend Tracks:** Select one or more tracks to extend simultaneously. Gemini generates coherent material for all selected tracks.
    *   **Complement Arrangement:** Generate an entire new arrangement (multiple tracks) to complement the existing piece. Includes instrument selection and drum track support.
*   **Creative Control:**
    *   **Style/Variation:** Provide textual hints (e.g., "more energetic", "syncopated rhythm") to guide Gemini's generation.
    *   **Intelligent Transitions:** Supports suggested musical shifts (tempo, key, time signature changes) at transition points.
*   **Robust Pipeline:** Uses the new `google-genai` SDK with structured JSON parsing for reliable results.
*   **TUI Interface:** Interactive terminal interface for file selection, settings, and displaying analysis results.
*   **Automated Testing:** Comprehensive test suite for MIDI parsing and AI response handling.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd midi-thinker
    ```

2.  **Install `uv` (if not already installed):**
    ```bash
    # On macOS/Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # On Windows
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

3.  **Install dependencies and run:**
    `uv` manages the virtual environment automatically.
    ```bash
    uv sync
    ```

4.  **Set up API Key:**
    *   Copy the `.env.template` file to `.env`.
    *   Open `.env` and replace `"YOUR_API_KEY_HERE"` with your actual Google Gemini API key.
    *   Ensure `.env` is listed in your `.gitignore` file (it is by default).

## Usage

Execute the script using `uv run`:

```bash
# Launch TUI to select input file and settings
uv run imagine-music.py

# Provide input file via CLI, then use TUI for other settings
uv run imagine-music.py -i ./path/to/your/input.mid
```

### Development

To run tests:
```bash
uv run python -m pytest
```

To run linter:
```bash
uv run ruff check .
```

## Future Enhancements (Post-MVP)

*   **Advanced Generation:**
    *   Control over velocity layers and humanization.
    *   Interactive iterative refinement (feedback loop with Gemini).
*   **Integration:**
    *   Support for `pretty_midi` for higher-level structural manipulation.
    *   Direct export to DAW-friendly formats or XML.
*   **Evaluation:**
    *   Musical rule-based validation of generated output.
*   **Audio-to-MIDI:** Further refine the `music-analyzer.py` tool for high-fidelity transcription.

