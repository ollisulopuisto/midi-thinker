# MIDI Thinker Implementation Progress

## MVP Workflow

-   [ ] 1. User executes script: `python modify_midi.py <input_midi_path> <output_midi_path> <bars_to_extend>` (Argument parsing)
-   [ ] 2. Program loads `<input_midi_path>` using `mido`.
-   [ ] 3. Program performs basic parsing (first track notes, first tempo, first key signature).
-   [ ] 4. Program converts this minimal data into MVP JSON format.
-   [ ] 5. (Optional) Program sends JSON to Gemini for basic analysis (confirm key/tempo).
-   [ ] 6. Program constructs a generation prompt for Gemini (original notes JSON, key, tempo, extend request).
-   [ ] 7. Program sends the generation prompt to Gemini.
-   [ ] 8. Program receives the generated notes representation in JSON.
-   [ ] 9. Program validates and parses the generated JSON notes.
-   [ ] 10. Program converts the parsed data into MIDI note events.
-   [ ] 11. Program appends the generated MIDI events to the first track of the loaded MIDI data.
-   [ ] 12. Program saves the modified MIDI structure to `<output_midi_path>`.
-   [ ] 13. Program confirms success and provides the output file path.
