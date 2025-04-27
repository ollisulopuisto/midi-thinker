# Gemini MIDI Modifier

## Introduction

This project aims to create a tool that leverages the Google Gemini API to analyze and modify MIDI files. The initial focus (MVP) is on loading a MIDI file, performing basic analysis, extending it based on user input, and saving the result.

## MVP Functionality

*   Loads a standard MIDI file (`.mid`).
*   Extracts basic information from the first track (notes, first tempo, first key signature).
*   Sends this information to the Gemini API.
*   Prompts the user for the number of bars to extend the piece.
*   Requests the Gemini API to generate new notes to extend the first track in a similar style.
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
python modify_midi.py <input_midi_path> <output_midi_path> <bars_to_extend>
```

*   `<input_midi_path>`: Path to the MIDI file you want to modify.
*   `<output_midi_path>`: Path where the extended MIDI file will be saved.
*   `<bars_to_extend>`: The approximate number of bars by which to extend the first track.

**Example:**

```bash
python modify_midi.py ./input/my_song.mid ./output/my_song_extended.mid 4
```

This will load `my_song.mid`, ask Gemini to generate approximately 4 bars of music based on the first track, append it, and save the result to `my_song_extended.mid`.

## Future Enhancements (Post-MVP)

*   Support for Type 0 MIDI files.
*   Analysis and modification of multiple tracks.
*   More sophisticated analysis (harmony, style).
*   Different modification types (e.g., generating complementary parts like basslines or harmonies).
*   Improved prompt engineering for better musical coherence.
*   Handling of more MIDI meta-messages (time signatures, program changes).

## Contributing

Contributions are welcome. Please refer to the `spec.md` for more detailed design information.
