import argparse
import mido
import sys
import json
import os # Added import
import google.generativeai as genai # Added import
from dotenv import load_dotenv # Added import

# Default values if not found in MIDI
DEFAULT_TEMPO = 500000  # 120 bpm
DEFAULT_KEY = "Cmaj"

def parse_midi_to_mvp_json(midi_file: mido.MidiFile):
    """
    Parses the first track of a MIDI file to extract notes, tempo, and key signature
    into the MVP JSON format.
    """
    if not midi_file.tracks:
        print("Warning: MIDI file has no tracks.", file=sys.stderr)
        return None # Or handle more gracefully

    # --- Find first tempo and key signature ---
    # According to spec, look in the first track for MVP.
    # For Type 1 files, tempo/key are often in track 0, but we stick to spec for now.
    first_track = midi_file.tracks[0]
    tempo = DEFAULT_TEMPO
    key_signature = DEFAULT_KEY
    found_tempo = False
    found_key = False

    # First pass for meta messages (tempo, key)
    for msg in first_track:
        if msg.is_meta:
            if msg.type == 'set_tempo' and not found_tempo:
                tempo = msg.tempo
                found_tempo = True
                print(f"Found tempo: {tempo}")
            elif msg.type == 'key_signature' and not found_key:
                key_signature = msg.key # mido provides the key name directly
                found_key = True
                print(f"Found key signature: {key_signature}")
        if found_tempo and found_key:
            break # Optimization: stop searching once both are found

    # --- Extract notes from the first track ---
    notes = []
    current_time_ticks = 0
    active_notes = {}  # pitch -> (start_tick, velocity)

    for msg in first_track:
        current_time_ticks += msg.time # Accumulate delta time in ticks

        if msg.type == 'note_on' and msg.velocity > 0:
            # Store note_on event
            active_notes[msg.note] = (current_time_ticks, msg.velocity)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            # Note_off event or note_on with velocity 0
            if msg.note in active_notes:
                start_tick, velocity = active_notes.pop(msg.note)
                duration_tick = current_time_ticks - start_tick
                if duration_tick >= 0: # Avoid negative duration if events are weirdly ordered
                    notes.append({
                        "pitch": msg.note,
                        "start_tick": start_tick,
                        "duration_tick": duration_tick,
                        "velocity": velocity
                    })
            # else: Note off without matching note on - ignore for MVP

    if active_notes:
        print(f"Warning: {len(active_notes)} notes were left active at the end of the track.", file=sys.stderr)
        # Optionally handle these dangling notes, e.g., by giving them a default duration till end?

    # --- Construct JSON ---
    mvp_representation = {
        "tempo": tempo,
        "key_signature": key_signature,
        "ticks_per_beat": midi_file.ticks_per_beat,
        "tracks": [
            {
                "notes": notes
            }
        ]
    }
    return mvp_representation

def call_gemini_for_extension(mvp_json_data: dict, bars_to_extend: int):
    """
    Constructs a prompt and calls the Gemini API to generate extended notes.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        print("Please create a .env file with your key (see .env.template).", file=sys.stderr)
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # Or choose another appropriate model

        # --- Construct the Prompt (MVP Step 6) ---
        # TODO: Refine this prompt significantly based on testing.
        # TODO: Calculate extension length in ticks based on bars_to_extend, tempo, and ticks_per_beat.
        # For now, just passing the number of bars as a concept.
        extension_request = f"Extend the following musical piece by approximately {bars_to_extend} bars."

        prompt = f"""
You are a MIDI music generation assistant.
Analyze the provided musical data in JSON format and generate new musical material
that extends the piece in a similar style.

Input Data:
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {extension_request}

Output ONLY the JSON representation of the *new* notes to be appended.
The JSON should be a list of note objects, each with "pitch", "start_tick", "duration_tick", and "velocity".
The "start_tick" for the new notes should be relative to the beginning of the *extension* (i.e., start from 0 or a small positive value).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format for new notes:
```json
[
  {{ "pitch": 60, "start_tick": 0, "duration_tick": 480, "velocity": 90 }},
  {{ "pitch": 62, "start_tick": 480, "duration_tick": 480, "velocity": 90 }}
]
```

Generated Notes JSON:
"""
        print("\n--- Sending Prompt to Gemini ---")
        # print(prompt) # Uncomment to debug the prompt
        print("--- End Prompt ---")

        # --- Call Gemini API (MVP Step 7) ---
        print("\nCalling Gemini API...")
        response = model.generate_content(prompt)
        print("Received response from Gemini.")

        # Basic check for response content (more robust parsing needed later)
        if response.parts:
            generated_json_text = response.text # Access text directly
            print("\n--- Gemini Response Text ---")
            print(generated_json_text)
            print("--- End Gemini Response Text ---\n")
            return generated_json_text # Return the raw text for now
        else:
            print("Warning: Gemini response did not contain expected parts.", file=sys.stderr)
            # Print safety feedback if available
            if response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}", file=sys.stderr)
            return None

    except Exception as e:
        print(f"Error calling Gemini API: {e}", file=sys.stderr)
        # TODO: Handle specific API errors (rate limits, auth issues) more gracefully.
        return None


def main():
    load_dotenv() # Load .env file

    parser = argparse.ArgumentParser(description="Modify a MIDI file using Gemini.")
    # ... existing argument parsing ...
    parser.add_argument("bars_to_extend", type=int, help="Number of bars to extend the first track by.") # TODO: Later change to ticks or handle bar conversion

    args = parser.parse_args()

    print(f"Loading MIDI file: {args.input_midi_path}")

    try:
        midi_file = mido.MidiFile(args.input_midi_path)
        print(f"Successfully loaded MIDI file. Type: {midi_file.type}, Ticks per beat: {midi_file.ticks_per_beat}")
        # MVP Spec simplification: Assume Type 1, focus on first track.
        if midi_file.type == 0 and len(midi_file.tracks) > 1:
             print("Warning: Input is Type 0 MIDI with multiple tracks. MVP processing only the first track's content.", file=sys.stderr)
        elif not midi_file.tracks:
             print("Error: MIDI file contains no tracks.", file=sys.stderr)
             sys.exit(1)

    # ... existing error handling ...
    except Exception as e:
        print(f"Error loading MIDI file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Parse and Convert to JSON ---
    print("\nParsing MIDI data to MVP JSON format...")
    mvp_json_data = parse_midi_to_mvp_json(midi_file)

    if mvp_json_data:
        print("Successfully parsed MIDI data.")
        # Print JSON for verification (can be removed later)
        print("\n--- MVP JSON Representation ---")
        print(json.dumps(mvp_json_data, indent=2))
        print("--- End MVP JSON Representation ---\n")
    else:
        print("Failed to parse MIDI data into JSON.", file=sys.stderr)
        sys.exit(1)

    # --- Call Gemini for Generation ---
    generated_notes_json_text = call_gemini_for_extension(mvp_json_data, args.bars_to_extend)

    if generated_notes_json_text:
        print("Successfully received generation response from Gemini.")
        # TODO: Implement Step 9: Validate and parse the generated_notes_json_text
        # TODO: Implement Step 10: Convert parsed data into MIDI events
        # TODO: Implement Step 11: Append events to midi_file.tracks[0]
        # TODO: Implement Step 12: Save midi_file
        # TODO: Implement Step 13: Confirmation message
    else:
        print("Failed to get valid generation response from Gemini.", file=sys.stderr)
        sys.exit(1)


    # --- Placeholder for next steps ---
    print("Next steps: Parse Gemini JSON, convert to MIDI events, append, save.")
    # ... existing placeholder code ...


if __name__ == "__main__":
    main()
