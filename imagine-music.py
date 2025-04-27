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
DEFAULT_TIME_SIGNATURE = {"numerator": 4, "denominator": 4} # Add default time signature

def parse_midi_to_mvp_json(midi_file: mido.MidiFile):
    """
    Parses all tracks of a MIDI file to extract notes, plus tempo, key signature,
    and time signature from the first track, into the MVP JSON format.
    """
    if not midi_file.tracks:
        print("Warning: MIDI file has no tracks.", file=sys.stderr)
        return None # Or handle more gracefully

    # --- Find first tempo, key signature, and time signature from Track 0 (or first track) ---
    # For Type 1 files, these are often in track 0. For Type 0, they are mixed in.
    # We stick to reading from the first track available for MVP+.
    first_track_meta = midi_file.tracks[0]
    tempo = DEFAULT_TEMPO
    key_signature = DEFAULT_KEY
    time_signature_data = DEFAULT_TIME_SIGNATURE.copy()
    found_tempo = False
    found_key = False
    found_time_sig = False

    for msg in first_track_meta:
        if msg.is_meta:
            if msg.type == 'set_tempo' and not found_tempo:
                tempo = msg.tempo
                found_tempo = True
                print(f"Found tempo: {tempo}")
            elif msg.type == 'key_signature' and not found_key:
                key_signature = msg.key
                found_key = True
                print(f"Found key signature: {key_signature}")
            elif msg.type == 'time_signature' and not found_time_sig:
                time_signature_data['numerator'] = msg.numerator
                time_signature_data['denominator'] = msg.denominator
                found_time_sig = True
                print(f"Found time signature: {msg.numerator}/{msg.denominator}")
        if found_tempo and found_key and found_time_sig:
            break

    # --- Extract notes from ALL tracks ---
    all_tracks_notes = []
    last_tick_first_track = 0 # Keep track of the end of the first track specifically

    for i, track in enumerate(midi_file.tracks):
        notes = []
        current_time_ticks = 0
        active_notes = {}  # pitch -> (start_tick, velocity)
        print(f"Processing Track {i}...")

        for msg in track:
            current_time_ticks += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes[msg.note] = (current_time_ticks, msg.velocity)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in active_notes:
                    start_tick, velocity = active_notes.pop(msg.note)
                    duration_tick = current_time_ticks - start_tick
                    if duration_tick >= 0:
                        notes.append({
                            "pitch": msg.note,
                            "start_tick": start_tick,
                            "duration_tick": duration_tick,
                            "velocity": velocity
                        })
                # else: Note off without matching note on - ignore

        if active_notes:
            print(f"Warning: Track {i} - {len(active_notes)} notes were left active at the end.", file=sys.stderr)
            # Optionally handle dangling notes

        all_tracks_notes.append({"notes": notes})
        if i == 0:
            last_tick_first_track = current_time_ticks # Record end time of the first track

        print(f"Track {i}: Found {len(notes)} notes. Ends at tick {current_time_ticks}.")


    # --- Construct JSON ---
    mvp_representation = {
        "tempo": tempo,
        "key_signature": key_signature,
        "time_signature": time_signature_data,
        "ticks_per_beat": midi_file.ticks_per_beat,
        "tracks": all_tracks_notes # Include notes from all tracks
    }

    # Return both JSON and the last tick time of the FIRST track (for appending)
    return mvp_representation, last_tick_first_track

def call_gemini_for_analysis(mvp_json_data: dict):
    """
    (Optional MVP Step 5)
    Constructs a prompt and calls the Gemini API to analyze tempo and key.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # Don't treat as fatal error for optional step, just warn.
        print("Warning: GEMINI_API_KEY not found. Skipping optional analysis step.", file=sys.stderr)
        return

    try:
        genai.configure(api_key=api_key)
        # Use a model suitable for analysis, flash might be sufficient
        model = genai.GenerativeModel('gemini-1.5-flash')

        # --- Construct the Analysis Prompt ---
        # Calculate BPM from tempo (microseconds per beat) for better readability in prompt/output
        tempo_microseconds = mvp_json_data.get('tempo', DEFAULT_TEMPO)
        bpm = round(60_000_000 / tempo_microseconds) if tempo_microseconds > 0 else "N/A"

        prompt = f"""
You are a MIDI music analysis assistant.
Analyze the provided musical data in JSON format, focusing on the first track.
The JSON includes notes, the initially detected tempo ({tempo_microseconds} microseconds per beat, approx {bpm} BPM),
and the initially detected key signature ('{mvp_json_data.get('key_signature', DEFAULT_KEY)}').

Input Data:
```json
{json.dumps(mvp_json_data, indent=2)}
```

Based *primarily* on the note data provided, please confirm or correct:
1. The most likely Key Signature.
2. The primary Tempo in BPM (Beats Per Minute). You can use the provided tempo as a strong hint.

Output your answer concisely in the format:
"Key Signature: [Your Identified Key], Tempo: [Your Calculated BPM] BPM"

Analysis Result:
"""
        print("\n--- Sending Analysis Prompt to Gemini (Optional Step 5) ---")
        # print(prompt) # Uncomment to debug the prompt
        print("--- End Analysis Prompt ---")

        # --- Call Gemini API ---
        print("\nCalling Gemini API for analysis...")
        # Add safety settings to potentially reduce refusals for simple analysis
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        print("Received analysis response from Gemini.")

        if response.parts:
            analysis_text = response.text
            print("\n--- Gemini Analysis Result ---")
            print(analysis_text.strip())
            print("--- End Gemini Analysis Result ---\n")
        else:
            print("Warning: Gemini analysis response did not contain expected parts.", file=sys.stderr)
            if response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}", file=sys.stderr)

    except Exception as e:
        print(f"Warning: Error during optional Gemini analysis step: {e}", file=sys.stderr)


def call_gemini_for_extension(mvp_json_data: dict, bars_to_extend: int):
    """
    Constructs a prompt and calls the Gemini API to generate extended notes
    for the FIRST track, using all tracks as context.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        print("Please create a .env file with your key (see .env.template).", file=sys.stderr)
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # Or choose another appropriate model

        # --- Construct the Prompt (MVP Step 6 / Post-MVP Refinement) ---
        # Calculate extension length in ticks using time signature
        ticks_per_beat = mvp_json_data.get('ticks_per_beat', 480) # Default if missing
        time_sig = mvp_json_data.get('time_signature', DEFAULT_TIME_SIGNATURE)
        numerator = time_sig.get('numerator', DEFAULT_TIME_SIGNATURE['numerator'])
        # Denominator interpretation for beats per bar is complex in MIDI.
        # Simplification: Assume numerator directly gives beats per bar (common for x/4 time).
        # A more robust calculation would use the denominator: beats_per_bar = numerator * (4 / denominator)
        # but let's stick to the simpler approach for now.
        ticks_per_bar = ticks_per_beat * numerator
        target_extension_ticks = ticks_per_bar * bars_to_extend

        extension_request = (f"Extend the musical piece by approximately {bars_to_extend} bars "
                             f"(target duration: around {target_extension_ticks} ticks). "
                             f"Generate new notes ONLY for the FIRST track (track 0). "
                             f"Use the existing notes from all tracks as musical context.")

        prompt = f"""
You are a MIDI music generation assistant.
Analyze the provided musical data in JSON format which contains multiple tracks.
Generate new musical material that extends the piece in a similar style.

**IMPORTANT**: Generate new notes ONLY for the FIRST track (track index 0).
You can use the content of other tracks as musical context for your generation.

Input Data (Multiple Tracks):
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {extension_request}

Output ONLY the JSON representation of the *new* notes to be appended to the FIRST track.
The JSON should be a list of note objects, each with "pitch", "start_tick", "duration_tick", and "velocity".
The "start_tick" for the new notes should be relative to the beginning of the *extension* (i.e., start from 0 or a small positive value).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format for new notes (for the first track):
```json
[
  {{ "pitch": 60, "start_tick": 0, "duration_tick": 480, "velocity": 90 }},
  {{ "pitch": 62, "start_tick": 480, "duration_tick": 480, "velocity": 90 }}
]
```

Generated Notes JSON (for Track 0):
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
    parser.add_argument("bars_to_extend", type=int, help="Number of bars to extend the first track by.") # Keep help text simple

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
    print("\nParsing MIDI data (all tracks) to JSON format...")
    parse_result = parse_midi_to_mvp_json(midi_file)

    if parse_result:
        mvp_json_data, last_original_tick_first_track = parse_result # Renamed variable
        print("Successfully parsed MIDI data.")
        # Optionally print the JSON data for debugging
        # print("\n--- MVP JSON Representation ---")
        # print(json.dumps(mvp_json_data, indent=2))
        # print("--- End JSON Representation ---\n")

        # --- Optional Analysis Step (MVP Step 5) ---
        # Analysis prompt currently only uses global tempo/key, doesn't need change yet
        call_gemini_for_analysis(mvp_json_data)

    else:
        print("Failed to parse MIDI data into JSON.", file=sys.stderr)
        sys.exit(1)

    # --- Call Gemini for Generation ---
    # Pass the full JSON data, but generation targets the first track
    generated_notes_json_text = call_gemini_for_extension(mvp_json_data, args.bars_to_extend)

    if generated_notes_json_text:
        print("Successfully received generation response from Gemini.")

        # --- Parse Gemini Response (Step 9) ---
        print("\nParsing Gemini response...")
        generated_notes = parse_gemini_response(generated_notes_json_text)

        if generated_notes:
             # --- Convert to MIDI Events (Step 10) ---
             print("\nConverting generated notes to MIDI events...")
             # Use last_original_tick_first_track as the offset for the new events
             new_midi_events = generated_notes_to_midi_events(generated_notes, last_original_tick_first_track) # Use renamed variable

             if new_midi_events:
                 # --- Append to Track (Step 11) ---
                 # Still appending only to the first track for "Extend"
                 print(f"\nAppending {len(new_midi_events)} new events to the first track (Track 0)...")
                 if midi_file.tracks:
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
