import argparse
import mido
import sys
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
import re # Added import for cleaning JSON

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

    # --- Also return the last tick time of the track ---
    last_tick = current_time_ticks # The time accumulated at the end of the loop

    # Return both JSON and the last tick time
    return mvp_representation, last_tick

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


def parse_gemini_response(json_text: str):
    """
    Cleans and parses the JSON string potentially returned by Gemini.
    """
    if not json_text:
        print("Error: Received empty response text from Gemini.", file=sys.stderr)
        return None

    # Attempt to remove markdown code block fences and surrounding whitespace
    match = re.search(r'```json\s*([\s\S]*?)\s*```', json_text, re.IGNORECASE)
    if match:
        cleaned_text = match.group(1).strip()
    else:
        # If no markdown found, assume the text is the JSON itself (strip whitespace)
        cleaned_text = json_text.strip()

    if not cleaned_text:
        print("Error: Cleaned response text is empty.", file=sys.stderr)
        return None

    try:
        parsed_data = json.loads(cleaned_text)
        # Basic validation (expecting a list of notes)
        if not isinstance(parsed_data, list):
            print(f"Error: Parsed JSON is not a list as expected. Type: {type(parsed_data)}", file=sys.stderr)
            return None
        # Optional: Add more validation for note structure if needed
        # for note in parsed_data:
        #     if not all(k in note for k in ("pitch", "start_tick", "duration_tick", "velocity")):
        #         print(f"Error: Invalid note structure found in parsed JSON: {note}", file=sys.stderr)
        #         return None
        print(f"Successfully parsed {len(parsed_data)} generated notes from Gemini response.")
        return parsed_data
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from Gemini response: {e}", file=sys.stderr)
        print(f"Cleaned text was:\n---\n{cleaned_text}\n---", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred during JSON parsing: {e}", file=sys.stderr)
        return None


def generated_notes_to_midi_events(generated_notes: list, start_offset_ticks: int):
    """
    Converts a list of note dictionaries (from parsed JSON) into a list of
    mido MIDI messages with correct delta times, offset by start_offset_ticks.
    """
    events = []
    for note in generated_notes:
        # Ensure required keys are present and are integers
        try:
            pitch = int(note['pitch'])
            start_tick = int(note['start_tick']) + start_offset_ticks
            duration_tick = int(note['duration_tick'])
            velocity = int(note['velocity'])
            end_tick = start_tick + duration_tick

            # Clamp values to valid MIDI ranges
            pitch = max(0, min(127, pitch))
            velocity = max(0, min(127, velocity))
            if duration_tick < 0: duration_tick = 0 # Ensure non-negative duration

            if velocity == 0: # Treat velocity 0 as note_off
                 events.append({'type': 'note_off', 'tick': start_tick, 'pitch': pitch, 'velocity': 0})
            else:
                events.append({'type': 'note_on', 'tick': start_tick, 'pitch': pitch, 'velocity': velocity})
                events.append({'type': 'note_off', 'tick': end_tick, 'pitch': pitch, 'velocity': 0}) # Standard note_off velocity is often 0 or 64

        except KeyError as e:
            print(f"Warning: Skipping note due to missing key {e}: {note}", file=sys.stderr)
            continue
        except (ValueError, TypeError) as e:
            print(f"Warning: Skipping note due to invalid value type/format {e}: {note}", file=sys.stderr)
            continue


    # Sort events by tick time, then note_off before note_on for same tick
    events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))

    # Convert absolute ticks to delta times for mido messages
    midi_messages = []
    last_event_tick = start_offset_ticks # Start calculating deltas from the offset
    for event in events:
        delta_time = event['tick'] - last_event_tick
        if delta_time < 0:
             print(f"Warning: Negative delta time calculated ({delta_time}). Clamping to 0. Event: {event}", file=sys.stderr)
             delta_time = 0 # Should not happen with correct sorting, but safety check

        midi_messages.append(mido.Message(
            event['type'],
            note=event['pitch'],
            velocity=event['velocity'],
            time=delta_time
        ))
        last_event_tick = event['tick']

    print(f"Converted {len(generated_notes)} notes into {len(midi_messages)} MIDI messages.")
    return midi_messages


def main():
    load_dotenv() # Load .env file

    parser = argparse.ArgumentParser(description="Modify a MIDI file using Gemini.")
    # Add input and output path arguments
    parser.add_argument("input_midi_path", type=str, help="Path to the input MIDI file.")
    parser.add_argument("output_midi_path", type=str, help="Path to save the modified MIDI file.")
    parser.add_argument("bars_to_extend", type=int, help="Number of bars to extend the first track by.") # TODO: Later change to ticks or handle bar conversion

    args = parser.parse_args()

    print(f"Loading MIDI file: {args.input_midi_path}")

    try:
        midi_file = mido.MidiFile(args.input_midi_path)
        # ... existing loading code & checks ...
    # ... existing error handling ...
    except Exception as e:
        print(f"Error loading MIDI file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Parse and Convert to JSON ---
    print("\nParsing MIDI data to MVP JSON format...")
    parse_result = parse_midi_to_mvp_json(midi_file)

    if parse_result:
        mvp_json_data, last_original_tick = parse_result
        print("Successfully parsed MIDI data.")
        # ... existing JSON printing ...
    else:
        print("Failed to parse MIDI data into JSON.", file=sys.stderr)
        sys.exit(1)

    # --- Call Gemini for Generation ---
    generated_notes_json_text = call_gemini_for_extension(mvp_json_data, args.bars_to_extend)

    if generated_notes_json_text:
        print("Successfully received generation response from Gemini.")

        # --- Parse Gemini Response (Step 9) ---
        print("\nParsing Gemini response...")
        generated_notes = parse_gemini_response(generated_notes_json_text)

        if generated_notes:
             # --- Convert to MIDI Events (Step 10) ---
             print("\nConverting generated notes to MIDI events...")
             # Use last_original_tick as the offset for the new events
             new_midi_events = generated_notes_to_midi_events(generated_notes, last_original_tick)

             if new_midi_events:
                 # --- Append to Track (Step 11) ---
                 print(f"\nAppending {len(new_midi_events)} new events to the first track...")
                 # Ensure the first track exists
                 if midi_file.tracks:
                     # Adjust time of the first new event relative to the *last event* in the original track
                     # Mido handles delta times internally when appending, but the first delta needs care.
                     # The generated_notes_to_midi_events already calculates deltas relative to last_original_tick.
                     # We might need to adjust the *very first* delta if the original track didn't end exactly at last_original_tick
                     # For simplicity in MVP, we assume the delta calculation is sufficient.
                     midi_file.tracks[0].extend(new_midi_events)
                     print("Append successful.")

                     # --- Save MIDI File (Step 12) ---
                     try:
                         print(f"\nSaving modified MIDI to: {args.output_midi_path}")
                         midi_file.save(args.output_midi_path)
                         # --- Confirmation (Step 13) ---
                         print(f"\nSuccess! Modified MIDI saved to {args.output_midi_path}")
                     except Exception as e:
                         print(f"Error saving MIDI file: {e}", file=sys.stderr)
                         sys.exit(1)
                 else:
                      print("Error: Cannot append events, MIDI file has no tracks after loading.", file=sys.stderr)
                      sys.exit(1)
             else:
                  print("Failed to convert generated notes to MIDI events.", file=sys.stderr)
                  sys.exit(1)
        else:
             print("Failed to parse valid notes from Gemini response.", file=sys.stderr)
             sys.exit(1)

    else:
        print("Failed to get valid generation response from Gemini.", file=sys.stderr)
        sys.exit(1)

    # --- Remove Placeholder ---
    # print("Next steps: Parse Gemini JSON, convert to MIDI events, append, save.")


if __name__ == "__main__":
    main()
