# Imagine Music

## Introduction

This project aims to create a tool that leverages the Google Gemini API to help you arrange music: input a simple MIDI melody or chord idea, Gemini will help you expand on this, then saving the result as a MIDI file and importing that into your favorite DAW.

## Current Functionality

*   Loads a standard MIDI file (`.mid`) via command-line argument or TUI file selector.
*   Extracts basic information (first tempo, first key signature, first time signature).
*   Extracts notes and the first instrument program number (`program_change`) from *all* tracks.
*   Sends this information (all tracks) to the Gemini API for detailed analysis (key, tempo, time sig, style, harmony), with caching.
*   **Displays the detailed analysis results to the user.**
*   Prompts the user via TUI to select a mode:
    *   **Extend Track**: Choose a track and number of bars to extend.
    *   **Add Complementary Track**: Specify the type of complement (e.g., bassline).
*   Calculates the target extension length in MIDI ticks based on the time signature and tempo (for Extend mode).
*   Requests the Gemini API to generate new notes based on the selected mode:
    *   Extend: Generates notes for the *selected track* using all tracks as context.
    *   Complement: Generates notes for a *new track*.
*   Appends the generated notes to the end of the selected track (Extend) or adds them as a new track with an appropriate instrument (Complement).
*   Saves the modified MIDI data to a user-specified output file.
*   Includes basic error handling for file loading, API calls (including blocked prompts), and response parsing, with user feedback via TUI. *(New)*

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


The script will then:
1. Load the MIDI file.
2. Perform detailed analysis using Gemini (or load from cache).
3. **Show you the analysis results.**
4. Guide you through the TUI to select the operation mode (Extend/Complement), output file, and mode-specific parameters.
5. Generate the music with Gemini.
6. Save the result to your specified output path.

**Example (using TUI after providing input file):**

```bash
python imagine-music.py -i ./samples/sample_composition.mid
```

This will load `sample_composition.mid`, show analysis, and then prompt you via TUI for the mode, output path, and other settings.

## Future Enhancements (Post-MVP)

*   Support for Type 0 MIDI files.
*   Analysis and modification of multiple tracks. *(Partially addressed: Multi-track parsing done)*
*   More sophisticated analysis (harmony, style). *(Partially addressed: Detailed analysis performed and displayed)*
*   Different modification types (e.g., generating complementary parts like basslines or harmonies). *(Partially addressed: Basic complement mode implemented)*
*   Improved prompt engineering for better musical coherence.
*   Handling of more MIDI meta-messages (multiple time signatures, program changes). *(Partially addressed: First time signature, first program change)*
*   Generating material for tracks other than the first, or adding new tracks. *(Partially addressed: Complement adds new track)*
*   Using extracted instrument information in prompts or generation logic. *(Partially addressed: Instrument used in prompts)*
*   **Advanced User Interaction:**
    *   Display detailed analysis results. *(Implemented)*
    *   Structured parameter input (dropdowns, fields for style, part type, variations).
*   **Advanced Generation:**
    *   Control over dynamics, rhythm.
    *   Generate variations based on style.
*   **Intelligent MIDI Output:**
    *   Integrate generated tempo/key/time signature changes.
*   **Robust Error Handling.** *(Partially addressed: API errors, blocked prompts, parsing issues)*
*   **Evaluation Methods.**
