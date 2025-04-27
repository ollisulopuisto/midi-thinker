import mido
import sys
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv
import re # Added import for cleaning JSON
from tui import get_user_input, show_error, show_success # Import TUI functions

# Default values if not found in MIDI
DEFAULT_TEMPO = 500000  # 120 bpm
DEFAULT_KEY = "Cmaj"
DEFAULT_TIME_SIGNATURE = {"numerator": 4, "denominator": 4} # Add default time signature
# Instrument program numbers (General MIDI)
DEFAULT_INSTRUMENT = 0 # Acoustic Grand Piano
ACOUSTIC_BASS = 32
DEFAULT_COMPLEMENT_INSTRUMENT = ACOUSTIC_BASS

def parse_midi_to_mvp_json(midi_file: mido.MidiFile):
    """
    Parses all tracks of a MIDI file to extract notes and the first program change,
    plus tempo, key signature, and time signature from the first track,
    into the MVP JSON format.
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

    # --- Extract notes and program change from ALL tracks ---
    all_tracks_data = [] # Renamed from all_tracks_notes
    last_tick_first_track = 0

    for i, track in enumerate(midi_file.tracks):
        notes = []
        current_time_ticks = 0
        active_notes = {}
        first_program_change = None # Store the program number of the first program_change msg
        found_program_change = False
        print(f"Processing Track {i}...")

        for msg in track:
            # Find first program_change in the track
            if not found_program_change and msg.type == 'program_change':
                first_program_change = msg.program
                found_program_change = True
                print(f"  Found program change: {first_program_change}")

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

        # Add track data including notes and instrument program
        all_tracks_data.append({
            "instrument_program": first_program_change if found_program_change else 0, # Default to 0 (Piano) if not found
            "notes": notes
        })
        if i == 0:
            last_tick_first_track = current_time_ticks

        print(f"Track {i}: Instrument Program: {first_program_change if found_program_change else '0 (Default)'}. Found {len(notes)} notes. Ends at tick {current_time_ticks}.")


    # --- Construct JSON ---
    mvp_representation = {
        "tempo": tempo,
        "key_signature": key_signature,
        "time_signature": time_signature_data,
        "ticks_per_beat": midi_file.ticks_per_beat,
        "tracks": all_tracks_data # Use the new list containing track data
    }

    # Return both JSON and the last tick time of the FIRST track (for appending)
    return mvp_representation, last_tick_first_track

def call_gemini_for_analysis(mvp_json_data: dict):
    """
    (Optional MVP Step 5 - Basic Analysis)
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


def call_gemini_for_detailed_analysis(mvp_json_data: dict):
    """
    (Post-MVP)
    Constructs a prompt and calls the Gemini API for more detailed analysis.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not found. Skipping detailed analysis.", file=sys.stderr)
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # Flash is likely sufficient

        # Calculate BPM for prompt context
        tempo_microseconds = mvp_json_data.get('tempo', DEFAULT_TEMPO)
        bpm = round(60_000_000 / tempo_microseconds) if tempo_microseconds > 0 else "N/A"
        key_signature = mvp_json_data.get('key_signature', DEFAULT_KEY)
        time_signature = mvp_json_data.get('time_signature', DEFAULT_TIME_SIGNATURE)
        ts_str = f"{time_signature.get('numerator', 4)}/{time_signature.get('denominator', 4)}"

        prompt = f"""
You are an expert MIDI music analyst.
Analyze the provided musical data in JSON format, which contains multiple tracks with notes and instrument information.

Input Data:
```json
{json.dumps(mvp_json_data, indent=2)}
```

Based on the provided data (especially the notes across all tracks):
1.  **Key Signature:** Confirm or identify the most likely overall key signature.
2.  **Tempo:** Confirm or identify the primary tempo in BPM.
3.  **Time Signature:** Confirm the primary time signature ({ts_str} was detected initially).
4.  **Musical Style/Genre:** Briefly describe the likely musical style or genre (e.g., Classical, Jazz, Pop Ballad, Electronic).
5.  **Harmony:** Briefly describe the basic harmonic structure if discernible (e.g., Simple diatonic chords, Modal, Complex jazz harmony).

Output your analysis clearly, addressing each point.

Detailed Analysis:
"""
        print("\n--- Sending Detailed Analysis Prompt to Gemini ---")
        # print(prompt) # Uncomment to debug
        print("--- End Detailed Analysis Prompt ---")

        print("\nCalling Gemini API for detailed analysis...")
        # Use safety settings similar to basic analysis
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        print("Received detailed analysis response from Gemini.")

        if response.parts:
            analysis_text = response.text
            print("\n--- Gemini Detailed Analysis Result ---")
            print(analysis_text.strip())
            print("--- End Gemini Detailed Analysis Result ---\n")
        else:
            print("Warning: Gemini detailed analysis response did not contain expected parts.", file=sys.stderr)
            if response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}", file=sys.stderr)

    except Exception as e:
        print(f"Warning: Error during detailed Gemini analysis step: {e}", file=sys.stderr)


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


def call_gemini_for_complement(mvp_json_data: dict, complement_type: str):
    """
    (Post-MVP)
    Constructs a prompt and calls the Gemini API to generate a new complementary track.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        print("Please create a .env file with your key (see .env.template).", file=sys.stderr)
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # Or pro for potentially better musicality

        # Basic context for the prompt
        key_signature = mvp_json_data.get('key_signature', DEFAULT_KEY)
        tempo_microseconds = mvp_json_data.get('tempo', DEFAULT_TEMPO)
        bpm = round(60_000_000 / tempo_microseconds) if tempo_microseconds > 0 else "N/A"

        # Define the generation request based on complement_type
        generation_request = f"Generate a new musical part to complement the existing tracks. The new part should be a '{complement_type}'."
        if "bassline" in complement_type.lower():
             generation_request += " Focus on lower registers and provide harmonic support."
        elif "harmony" in complement_type.lower():
             generation_request += " Focus on chords or pads that fit the existing harmony."
        elif "counter-melody" in complement_type.lower():
             generation_request += " Create an independent melodic line that interacts interestingly with the existing melody/melodies."
        else:
             generation_request += " Generate notes that musically fit well with the existing material."


        prompt = f"""
You are a MIDI music composition assistant.
Analyze the provided musical data (JSON format, multiple tracks).
Generate a *new* musical part as specified in the request.

Input Data (Multiple Tracks):
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {generation_request}
The piece is in {key_signature} at approximately {bpm} BPM.

Output ONLY the JSON representation of the *new* notes for the *new* complementary track.
The JSON should be a list of note objects, each with "pitch", "start_tick", "duration_tick", and "velocity".
The "start_tick" for the new notes should be relative to the beginning of the piece (i.e., start from 0 or a small positive value, aligning with the original structure).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format for the new complementary track:
```json
[
  {{ "pitch": 48, "start_tick": 0, "duration_tick": 960, "velocity": 80 }},
  {{ "pitch": 50, "start_tick": 960, "duration_tick": 960, "velocity": 80 }}
]
```

Generated Notes JSON (for the new complementary track):
"""
        print("\n--- Sending Complement Prompt to Gemini ---")
        # print(prompt) # Uncomment to debug
        print("--- End Complement Prompt ---")

        print("\nCalling Gemini API for complement generation...")
        response = model.generate_content(prompt) # Consider safety settings if needed
        print("Received complement response from Gemini.")

        if response.parts:
            generated_json_text = response.text
            print("\n--- Gemini Complement Response Text ---")
            print(generated_json_text)
            print("--- End Gemini Complement Response Text ---\n")
            return generated_json_text
        else:
            print("Warning: Gemini complement response did not contain expected parts.", file=sys.stderr)
            if response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}", file=sys.stderr)
            return None

    except Exception as e:
        print(f"Error calling Gemini API for complement: {e}", file=sys.stderr)
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
    Handles potential errors in note data gracefully.
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

    # --- Get User Input via TUI ---
    settings = get_user_input()
    if not settings:
        print("Operation cancelled by user.")
        sys.exit(0)

    input_midi_path = settings['input_path']
    output_midi_path = settings['output_path']
    mode = settings['mode']

    print(f"Loading MIDI file: {input_midi_path}")
    print(f"Mode: {mode}")
    if mode == 'extend':
        print(f"Bars to extend: {settings['bars_to_extend']}")
    elif mode == 'complement':
        print(f"Complement type: {settings['complement_type']}")


    try:
        midi_file = mido.MidiFile(input_midi_path)
        # Basic check: Does it have tracks?
        if not midi_file.tracks:
             error_msg = f"Error: Input MIDI file '{input_midi_path}' contains no tracks."
             print(error_msg, file=sys.stderr)
             show_error("MIDI Load Error", error_msg)
             sys.exit(1)
        # Check MIDI type (informational)
        print(f"MIDI Type: {midi_file.type}")
        if midi_file.type == 0 and len(midi_file.tracks) > 1:
            print("Warning: Type 0 MIDI file with multiple tracks found. Treating as a single logical track.", file=sys.stderr)
        elif midi_file.type == 2:
             print("Warning: Type 2 MIDI files are not fully supported. Results may be unpredictable.", file=sys.stderr)

    except FileNotFoundError:
        error_msg = f"Error: Input MIDI file not found at '{input_midi_path}'"
        print(error_msg, file=sys.stderr)
        show_error("File Not Found", error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Error loading MIDI file: {e}"
        print(error_msg, file=sys.stderr)
        show_error("MIDI Load Error", error_msg)
        sys.exit(1)

    # --- Parse and Convert to JSON ---
    print("\nParsing MIDI data (all tracks) to JSON format...")
    parse_result = parse_midi_to_mvp_json(midi_file)

    if parse_result:
        mvp_json_data, last_original_tick_first_track = parse_result
        print("Successfully parsed MIDI data.")
        # Optionally print the JSON data for debugging
        # print("\n--- MVP JSON Representation ---")
        # print(json.dumps(mvp_json_data, indent=2))
        # print("--- End JSON Representation ---\n")

        # --- Optional Basic Analysis Step (MVP Step 5) ---
        # call_gemini_for_analysis(mvp_json_data) # Keep or remove as desired

        # --- Detailed Analysis Step (Post-MVP) ---
        call_gemini_for_detailed_analysis(mvp_json_data)

    else:
        error_msg = "Failed to parse MIDI data into JSON."
        print(error_msg, file=sys.stderr)
        show_error("Parsing Error", error_msg)
        sys.exit(1)


    # --- Call Gemini for Generation based on mode ---
    generated_notes_json_text = None
    if mode == 'extend':
        generated_notes_json_text = call_gemini_for_extension(mvp_json_data, settings['bars_to_extend'])
    elif mode == 'complement':
        generated_notes_json_text = call_gemini_for_complement(mvp_json_data, settings['complement_type'])

    if generated_notes_json_text:
        print(f"Successfully received generation response from Gemini for mode '{mode}'.")

        # --- Parse Gemini Response ---
        print("\nParsing Gemini response...")
        generated_notes = parse_gemini_response(generated_notes_json_text)

        if generated_notes:
             # --- Convert to MIDI Events ---
             print("\nConverting generated notes to MIDI events...")
             start_offset = 0
             if mode == 'extend':
                 start_offset = last_original_tick_first_track # Append after original track 0 content
             elif mode == 'complement':
                 start_offset = 0 # New track starts from time 0

             new_midi_events = generated_notes_to_midi_events(generated_notes, start_offset)

             if new_midi_events is not None: # Check if conversion was successful (might return empty list)
                 # --- Add Events to MIDI File ---
                 if mode == 'extend':
                     print(f"\nAppending {len(new_midi_events)} new events to the first track (Track 0)...")
                     if midi_file.tracks:
                         midi_file.tracks[0].extend(new_midi_events)
                         print("Append successful.")
                     else:
                          # This check should be redundant due to earlier check, but good practice
                          error_msg = "Error: Cannot append events, MIDI file has no tracks."
                          print(error_msg, file=sys.stderr)
                          show_error("MIDI Error", error_msg)
                          sys.exit(1)

                 elif mode == 'complement':
                     print(f"\nCreating a new track for the '{settings['complement_type']}' complement...")
                     new_track = mido.MidiTrack()
                     midi_file.tracks.append(new_track)
                     print(f"Appended new Track {len(midi_file.tracks) - 1}.")

                     # Add a program change message at the beginning of the new track
                     # Determine instrument based on complement type (simple logic for now)
                     instrument_program = DEFAULT_COMPLEMENT_INSTRUMENT
                     comp_type_lower = settings['complement_type'].lower()
                     if "bass" in comp_type_lower:
                         instrument_program = ACOUSTIC_BASS
                     elif "harmony" in comp_type_lower or "pad" in comp_type_lower:
                         instrument_program = 89 # Pad 1 (New Age) - example
                     elif "melody" in comp_type_lower:
                         instrument_program = 81 # Lead 1 (Square) - example
                     # Add more mappings as needed

                     print(f"Setting instrument for new track to Program {instrument_program}.")
                     # Add program change with delta time 0 at the start
                     new_track.append(mido.Message('program_change', program=instrument_program, time=0))

                     # Add the generated notes
                     print(f"Adding {len(new_midi_events)} generated events to the new track...")
                     new_track.extend(new_midi_events)
                     print("Events added to new track.")


                 # --- Save MIDI File ---
                 try:
                     print(f"\nSaving modified MIDI to: {output_midi_path}")
                     # Ensure the output directory exists
                     output_dir = os.path.dirname(output_midi_path)
                     if output_dir and not os.path.exists(output_dir):
                         os.makedirs(output_dir)
                         print(f"Created output directory: {output_dir}")

                     midi_file.save(output_midi_path)
                     success_msg = f"Success! Modified MIDI saved to {output_midi_path}"
                     print(f"\n{success_msg}")
                     show_success("Operation Successful", success_msg)
                 except Exception as e:
                     error_msg = f"Error saving MIDI file: {e}"
                     print(error_msg, file=sys.stderr)
                     show_error("Save Error", error_msg)
                     sys.exit(1)

             else:
                  error_msg = "Failed to convert generated notes to MIDI events (returned None or error)."
                  print(error_msg, file=sys.stderr)
                  show_error("Conversion Error", error_msg)
                  sys.exit(1)
        else:
             error_msg = "Failed to parse valid notes from Gemini response."
             print(error_msg, file=sys.stderr)
             show_error("Parsing Error", error_msg)
             sys.exit(1)

    else:
        error_msg = f"Failed to get valid generation response from Gemini for mode '{mode}'."
        print(error_msg, file=sys.stderr)
        show_error("Gemini Error", error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
