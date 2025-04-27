**Project Title:** Gemini MIDI Modifier

**1. Introduction**

This project aims to create a tool that leverages the Gemini API to analyze and modify MIDI files based on user requests. The initial focus (MVP) is on loading a MIDI file, performing basic analysis, extending it based on user input, and saving the result. Subsequent versions will add more sophisticated analysis and modification capabilities.

**2. Key Components & Technologies (MVP & Beyond)**

*   **Programming Language:** Python 3.x
*   **MIDI Library:** `mido` (for low-level MIDI event manipulation). `pretty_midi` might be considered post-MVP for easier structural analysis.
*   **Gemini API Client:** Google AI Python SDK (`google-generativeai`).
*   **User Interface:** Command-Line Interface (CLI).
*   **Data Representation for Gemini:** JSON. The complexity will evolve from MVP to later stages.

**3. MVP Core Functionality**

*   **MIDI Input:** Load a standard MIDI file (.mid). Assume Type 1 format initially for simplicity. Handle basic errors like file not found.
*   **Basic MIDI-to-JSON Conversion:**
    *   Extract tempo (first tempo event found).
    *   Extract key signature (first key signature event found).
    *   Extract time signature (first time signature event found - numerator/denominator). *(Added Post-MVP)*
    *   Extract notes from the *first* track: pitch (MIDI number), start time (in ticks), duration (in ticks), velocity.
    *   Represent this information in a simple JSON structure (See MVP Data Representation).
*   **Basic Analysis (via Gemini):**
    *   Send the simplified JSON to Gemini.
    *   Prompt Gemini to confirm/identify the key signature and tempo based on the provided data. (Keep analysis minimal for MVP).
*   **Simple User Interaction:**
    *   Display the identified key and tempo.
    *   Prompt the user for only one modification type: **Extend**.
    *   Ask the user for the desired extension length (e.g., number of bars).
*   **Basic Generation (via Gemini):**
    *   Construct a simple prompt for Gemini including:
        *   The JSON representation of the *first track* notes.
        *   The identified key, tempo, and time signature.
        *   The user's request ("Extend by X bars, which is approximately Y ticks"). *(Refined Post-MVP)*
    *   Prompt Gemini to generate *only new notes* (pitch, start time relative to the end of original, duration, velocity) in a similar style, formatted as JSON.
*   **Basic JSON-to-MIDI Conversion:**
    *   Parse the generated JSON notes from Gemini.
*   **MIDI Output:**
    *   Append the newly generated MIDI note events (note_on, note_off with correct delta times) to the *end of the first track* of the original MIDI data.
    *   Save the resulting composition as a new standard MIDI file (.mid).

**4. MVP Workflow**

1.  User executes script: `python modify_midi.py <input_midi_path> <output_midi_path> <bars_to_extend>`
2.  Program loads `<input_midi_path>` using `mido`.
3.  Program performs basic parsing (first track notes, first tempo, first key signature).
4.  Program converts this minimal data into MVP JSON format.
5.  (Optional MVP step, can be simplified) Program sends JSON to Gemini for basic analysis (confirm key/tempo).
6.  Program constructs a generation prompt for Gemini (original notes JSON, key, tempo, extend request).
7.  Program sends the generation prompt to Gemini.
8.  Program receives the generated notes representation in JSON.
9.  Program validates and parses the generated JSON notes.
10. Program converts the parsed data into MIDI note events.
11. Program appends the generated MIDI events to the first track of the loaded MIDI data.
12. Program saves the modified MIDI structure to `<output_midi_path>`.
13. Program confirms success and provides the output file path.

**5. MVP Data Representation (Initial + Time Signature)**

*   A JSON object containing:
    *   `tempo`: integer (microseconds per beat)
    *   `key_signature`: string (e.g., "Cmaj")
    *   `time_signature`: object `{ "numerator": int, "denominator": int }` *(Added Post-MVP)*
    *   `ticks_per_beat`: integer
    *   `tracks`: List containing *one* track object (for MVP).
        *   Track object contains:
            *   `notes`: List of note objects.
                *   Note object: `{ "pitch": int, "start_tick": int, "duration_tick": int, "velocity": int }`

**6. Potential Challenges (MVP Focus)**

*   **MIDI-to-JSON Conversion:** Accurately converting MIDI timing (delta ticks) to absolute start times and durations in ticks for the JSON representation.
*   **JSON-to-MIDI Conversion:** Correctly converting the generated notes (with potentially relative start times from Gemini) back into MIDI events with accurate delta times for appending.
*   **Gemini Prompt Engineering (Basic):** Crafting prompts that reliably make Gemini generate notes in the correct JSON format for the simple "Extend" task.
*   **Musical Coherence (Basic):** Even simple extensions might sound disjointed. MVP accepts this; quality improvement is post-MVP.
*   **Error Handling:** Basic handling for file errors, API connection issues, and potentially unparseable JSON from Gemini.

**7. Post-MVP Refinements & Enhancements**

*(This section combines elements from the original Core Functionality, Refinement Questions, Refined Design Decisions, and Future Enhancements, deferred until after the MVP is working)*

*   **Enhanced MIDI Input:** Handle Type 0 MIDI files, potentially merge tracks.
*   **Full MIDI-to-JSON Conversion:**
    *   Represent *all* tracks.
    *   Handle meta-messages (multiple time signature changes, multiple tempos/keys). *(Partially addressed: First time signature parsed)*
    *   Handle program changes (instruments).
*   **Sophisticated Analysis (via Gemini):**
    *   Identify main melody lines across tracks.
    *   Detailed harmonic analysis (chord progressions with timing, inversions, extensions).
    *   Musical style/genre identification.
*   **Advanced User Interaction:**
    *   Display detailed analysis results.
    *   Implement **Complement** modification type (bass lines, harmony, counter-melody).
    *   Allow selection of specific tracks for analysis/modification.
    *   Structured parameter input (dropdowns, fields for style, part type, variations).
*   **Advanced Generation (via Gemini):**
    *   Generate specific complementary parts.
    *   Control over instrumentation, dynamics, rhythm.
    *   Generate variations based on style.
    *   Handle multi-track generation.
*   **Intelligent MIDI Output:**
    *   Add generated parts as *new* tracks for "Complement".
    *   Integrate generated tempo/key/time signature changes.
    *   Handle program changes for generated tracks.
*   **Refined Data Representation:** Develop a more comprehensive JSON structure for Gemini to handle the complexity above.
*   **Improved Prompt Engineering:** Iteratively refine prompts for better musical coherence, quality, and control. *(Partially addressed: More precise extension length)*
*   **Context Window Management:** Decide how much context (whole piece vs. recent bars) to provide Gemini.
*   **Robust Error Handling:** Handle diverse MIDI file issues, API limits, musically nonsensical output.
*   **Evaluation:** Develop methods (potentially simple rule-based checks or subjective listening tests) to evaluate output quality.
*   **Further Future Ideas:** GUI, style transfer, arrangement, drum patterns, real-time interaction, model finetuning, iterative refinement loop.

**8. Evaluation (MVP)**

*   The primary evaluation for the MVP will be subjective: Does the program load a MIDI, extend it without crashing, and produce a playable output MIDI file where the extension is audible? Musical quality is a secondary concern at this stage.
