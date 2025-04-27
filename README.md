# Gemini MIDI Modifier

## Introduction

This project aims to create a tool that leverages the Google Gemini API to help you arrange music: input a simple MIDI melody or chord idea, Gemini will help you expand on this, then saving the result as a MIDI file and importing that into your favorite DAW.

## MVP Functionality (and initial enhancements)

*   Loads a standard MIDI file (`.mid`).
*   Extracts basic information (first tempo, first key signature, first time signature) and notes from *all* tracks.
*   Sends this information (all tracks) to the Gemini API.
*   Prompts the user for the number of bars to extend the piece.
*   Calculates the target extension length in MIDI ticks based on the time signature and tempo.
*   Requests the Gemini API to generate new notes to extend the *first track* in a similar style, using all tracks as context.
*   Appends the generated notes to the end of the first track.
*   Saves the modified MIDI data to a new file.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd midi-thinker
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows use `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    ```bash
    pip install mido python-dotenv google-generativeai
    ```
4.  **Set up API Key:**
    *   Copy the `.env.template` file to `.env`.
    *   Open `.env` and replace `"YOUR_API_KEY_HERE"` with your actual Google Gemini API key.
    *   Ensure `.env` is listed in your `.gitignore` file (it is by default).

## Usage (MVP)

Execute the script from the command line:

```bash
python imagine-music.py <input_midi_path> <output_midi_path> <bars_to_extend>
```

*   `<input_midi_path>`: Path to the MIDI file you want to modify.
*   `<output_midi_path>`: Path where the extended MIDI file will be saved.
*   `<bars_to_extend>`: The number of bars by which to extend the first track. The script uses the MIDI's time signature (defaulting to 4/4 if none is found) to calculate a more precise target duration in ticks for the generation process.

**Example:**

```bash
python imagine-music.py ./input/my_song.mid ./output/my_song_extended.mid 4
```

This will load `my_song.mid`, ask Gemini to generate approximately 4 bars of music (calculated based on the MIDI's time signature) based on the first track, append it, and save the result to `my_song_extended.mid`.

## Future Enhancements (Post-MVP)

*   Support for Type 0 MIDI files.
*   Analysis and modification of multiple tracks. *(Partially addressed: Multi-track parsing done)*
*   More sophisticated analysis (harmony, style).
*   Different modification types (e.g., generating complementary parts like basslines or harmonies).
*   Improved prompt engineering for better musical coherence.
*   Handling of more MIDI meta-messages (multiple time signatures, program changes). *(Partially addressed: First time signature)*
*   Generating material for tracks other than the first, or adding new tracks.
