import mido
import sys
import json
import os
import argparse
import google.generativeai as genai
from google.generativeai.types import generation_types # For specific exception handling
from google.api_core import exceptions as google_exceptions # For API errors
from dotenv import load_dotenv
import re
import hashlib # Added for caching
from tui import get_user_input, select_input_file, show_error, show_success, show_analysis_results

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
    Parses all tracks of a loaded MIDI file to extract notes and the first program change,
    plus tempo, key signature, and time signature from the first track,
    into the MVP JSON format. Also returns the end tick of each track.
    """
    # No need to check midi_file.tracks here, should be checked before calling

    # --- Find first tempo, key signature, and time signature from Track 0 ---
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
    all_tracks_data = []
    track_end_ticks = [] # Store end tick for each track

    for i, track in enumerate(midi_file.tracks):
        # ... existing code to extract notes and first_program_change ...
        notes = []
        current_time_ticks = 0
        active_notes = {}
        first_program_change = None
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

        if active_notes:
            print(f"Warning: Track {i} - {len(active_notes)} notes were left active at the end.", file=sys.stderr)
            # Optionally handle dangling notes

        # Add track data including notes and instrument program
        all_tracks_data.append({
            "instrument_program": first_program_change if found_program_change else 0,
            "notes": notes
        })
        track_end_ticks.append(current_time_ticks) # Store the end tick for this track

        print(f"Track {i}: Instrument Program: {first_program_change if found_program_change else '0 (Default)'}. Found {len(notes)} notes. Ends at tick {current_time_ticks}.")


    # --- Construct JSON ---
    mvp_representation = {
        "tempo": tempo,
        "key_signature": key_signature,
        "time_signature": time_signature_data,
        "ticks_per_beat": midi_file.ticks_per_beat,
        "tracks": all_tracks_data
    }

    # Return JSON and the list of end ticks
    return mvp_representation, track_end_ticks

# Cache directory
CACHE_DIR = ".midi-thinker-cache"

def get_cache_filepath(input_midi_path: str) -> str:
    """Generates a cache filepath based on the hash of the input MIDI file."""
    try:
        hasher = hashlib.sha256()
        with open(input_midi_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        return os.path.join(CACHE_DIR, f"{file_hash}.json")
    except Exception as e:
        print(f"Warning: Could not generate cache key for {input_midi_path}: {e}", file=sys.stderr)
        return None


def load_analysis_from_cache(cache_filepath: str) -> dict | None:
    """Loads analysis data from a cache file."""
    if not cache_filepath or not os.path.exists(cache_filepath):
        return None
    try:
        with open(cache_filepath, 'r') as f:
            cached_data = json.load(f)
        print(f"Loaded analysis from cache: {cache_filepath}")
        return cached_data
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in cache file: {cache_filepath}. Ignoring cache.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Could not load from cache file {cache_filepath}: {e}", file=sys.stderr)
        return None

def save_analysis_to_cache(cache_filepath: str, analysis_data: dict):
    """Saves analysis data to a cache file."""
    if not cache_filepath or not analysis_data:
        return
    try:
        with open(cache_filepath, 'w') as f:
            json.dump(analysis_data, f, indent=2)
        print(f"Saved analysis to cache: {cache_filepath}")
    except Exception as e:
        print(f"Warning: Could not save to cache file {cache_filepath}: {e}", file=sys.stderr)


def call_gemini_for_detailed_analysis(mvp_json_data: dict, input_midi_path: str):
    """
    (Post-MVP)
    Constructs a prompt and calls the Gemini API for detailed analysis, requesting JSON output.
    Uses caching based on the input MIDI file content.
    Returns the analysis data as a dictionary or None if an error occurs.
    """
    # --- Caching Logic ---
    cache_filepath = get_cache_filepath(input_midi_path)
    cached_analysis = load_analysis_from_cache(cache_filepath)
    if cached_analysis:
        return cached_analysis
    # --- End Caching Logic ---

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not found. Skipping detailed analysis.", file=sys.stderr)
        return None

    try:
        genai.configure(api_key=api_key)
        # Use a model that supports JSON output mode if available and needed,
        # but flash should handle structured JSON requests reasonably well.
        model = genai.GenerativeModel('gemini-1.5-flash')

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

Based on the provided data (especially the notes across all tracks), provide a detailed analysis.

**Output ONLY a valid JSON object** containing the following keys:
- "key_signature": String (e.g., "Cmaj", "Amin") - Confirm or identify the most likely overall key signature.
- "tempo_bpm": Integer - Confirm or identify the primary tempo in BPM.
- "time_signature": String (e.g., "4/4", "3/4") - Confirm the primary time signature ({ts_str} was detected initially).
- "style_genre": String - Briefly describe the likely musical style or genre (e.g., "Classical", "Jazz Ballad", "Electronic Dance").
- "harmony_description": String - Briefly describe the basic harmonic structure (e.g., "Simple diatonic chords", "Modal harmony", "Uses extended jazz chords").

Example JSON Output:
```json
{{
  "key_signature": "Gmaj",
  "tempo_bpm": 140,
  "time_signature": "4/4",
  "style_genre": "Pop Rock",
  "harmony_description": "Primarily uses I-V-vi-IV progression."
}}
```

Analysis JSON:
"""
        print("\n--- Sending Detailed Analysis Prompt to Gemini (Requesting JSON) ---")
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
        # Consider adding generation_config={"response_mime_type": "application/json"} if using a model/API version that supports it explicitly.
        response = model.generate_content(prompt, safety_settings=safety_settings)
        print("Received detailed analysis response from Gemini.")

        # Check for blocked response *before* accessing parts
        if not response.parts:
            block_reason = None
            safety_feedback = None
            if response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 safety_feedback = response.prompt_feedback.safety_ratings
            error_msg = "Gemini detailed analysis response was empty or blocked."
            if block_reason:
                error_msg += f" Reason: {block_reason}."
            if safety_feedback:
                 error_msg += f" Safety Feedback: {safety_feedback}"
            print(error_msg, file=sys.stderr)
            show_error("Gemini Analysis Error", error_msg) # Show error in TUI
            return None

        analysis_json_text = response.text
        print("\n--- Gemini Detailed Analysis Raw Response ---")
        print(analysis_json_text)
        print("--- End Gemini Detailed Analysis Raw Response ---\n")

        # Parse the JSON response
        parsed_analysis = parse_gemini_response(analysis_json_text) # Re-use existing JSON parser

        if isinstance(parsed_analysis, dict): # Expecting a dictionary now
            print("Successfully parsed analysis JSON from Gemini.")
            # Save to cache before returning
            save_analysis_to_cache(cache_filepath, parsed_analysis)
            return parsed_analysis
        else:
            # Error message now includes more context from parse_gemini_response if parsing failed
            error_msg = "Gemini analysis response was not parsed into a valid dictionary."
            print(error_msg, file=sys.stderr)
            show_error("Analysis Parsing Error", error_msg) # Show error in TUI
            return None

    except generation_types.BlockedPromptException as e:
        error_msg = f"Gemini detailed analysis prompt was blocked: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Analysis Error", error_msg)
        return None
    except google_exceptions.GoogleAPIError as e:
        error_msg = f"Gemini API error during detailed analysis: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini API Error", error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error during detailed Gemini analysis: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Analysis Error", error_msg)
        return None


def call_gemini_for_extension(mvp_json_data: dict, bars_to_extend: int, target_track_index: int):
    """
    Constructs a prompt and calls the Gemini API to generate extended notes
    for the specified target track, using all tracks as context.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        print("Please create a .env file with your key (see .env.template).", file=sys.stderr)
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # --- Construct the Prompt ---
        # Calculate extension length in ticks using time signature
        ticks_per_beat = mvp_json_data.get('ticks_per_beat', 480)
        time_sig = mvp_json_data.get('time_signature', DEFAULT_TIME_SIGNATURE)
        numerator = time_sig.get('numerator', DEFAULT_TIME_SIGNATURE['numerator'])
        ticks_per_bar = ticks_per_beat * numerator
        target_extension_ticks = ticks_per_bar * bars_to_extend

        # Update extension request to mention the target track index
        extension_request = (f"Extend the musical piece by approximately {bars_to_extend} bars "
                             f"(target duration: around {target_extension_ticks} ticks). "
                             f"Generate new notes ONLY for Track {target_track_index}. "
                             f"Use the existing notes from all tracks as musical context.")
        target_instrument = mvp_json_data["tracks"][target_track_index].get("instrument_program", 0)


        prompt = f"""
You are a MIDI music generation assistant.
Analyze the provided musical data in JSON format which contains multiple tracks.
Generate new musical material that extends the piece in a similar style.

**IMPORTANT**: Generate new notes ONLY for Track {target_track_index} (which uses instrument program {target_instrument}).
You can use the content of other tracks as musical context for your generation.

Input Data (Multiple Tracks):
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {extension_request}

Output ONLY the JSON representation of the *new* notes to be appended to Track {target_track_index}.
The JSON should be a list of note objects, each with "pitch", "start_tick", "duration_tick", and "velocity".
The "start_tick" for the new notes should be relative to the beginning of the *extension* (i.e., start from 0 or a small positive value).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format for new notes (for Track {target_track_index}):
```json
[
  {{ "pitch": 60, "start_tick": 0, "duration_tick": 480, "velocity": 90 }},
  {{ "pitch": 62, "start_tick": 480, "duration_tick": 480, "velocity": 90 }}
]
```

Generated Notes JSON (for Track {target_track_index}):
"""
        print(f"\n--- Sending Prompt to Gemini (Extend Track {target_track_index}) ---")
        # print(prompt) # Uncomment to debug the prompt
        print("--- End Prompt ---")

        # --- Call Gemini API ---
        print("\nCalling Gemini API...")
        # Add safety settings similar to analysis
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        print("Received response from Gemini.")

        # Check for blocked response *before* accessing parts
        if not response.parts:
            block_reason = None
            safety_feedback = None
            if response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 safety_feedback = response.prompt_feedback.safety_ratings
            error_msg = "Gemini extension response was empty or blocked."
            if block_reason:
                error_msg += f" Reason: {block_reason}."
            if safety_feedback:
                 error_msg += f" Safety Feedback: {safety_feedback}"
            print(error_msg, file=sys.stderr)
            show_error("Gemini Extension Error", error_msg) # Show error in TUI
            return None

        generated_json_text = response.text
        print("\n--- Gemini Response Text ---")
        print(generated_json_text)
        print("--- End Gemini Response Text ---\n")
        return generated_json_text

    except generation_types.BlockedPromptException as e:
        error_msg = f"Gemini extension prompt was blocked: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Extension Error", error_msg)
        return None
    except google_exceptions.GoogleAPIError as e:
        error_msg = f"Gemini API error during extension: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini API Error", error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error calling Gemini API for extension: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Error", error_msg)
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
        # Add safety settings similar to analysis
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        print("Received complement response from Gemini.")

        # Check for blocked response *before* accessing parts
        if not response.parts:
            block_reason = None
            safety_feedback = None
            if response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 safety_feedback = response.prompt_feedback.safety_ratings
            error_msg = "Gemini complement response was empty or blocked."
            if block_reason:
                error_msg += f" Reason: {block_reason}."
            if safety_feedback:
                 error_msg += f" Safety Feedback: {safety_feedback}"
            print(error_msg, file=sys.stderr)
            show_error("Gemini Complement Error", error_msg) # Show error in TUI
            return None

        generated_json_text = response.text
        print("\n--- Gemini Complement Response Text ---")
        print(generated_json_text)
        print("--- End Gemini Complement Response Text ---\n")
        return generated_json_text

    except generation_types.BlockedPromptException as e:
        error_msg = f"Gemini complement prompt was blocked: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Complement Error", error_msg)
        return None
    except google_exceptions.GoogleAPIError as e:
        error_msg = f"Gemini API error during complement generation: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini API Error", error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error calling Gemini API for complement: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Error", error_msg)
        return None


def parse_gemini_response(json_text: str):
    """
    Cleans and parses the JSON string potentially returned by Gemini.
    Handles potential markdown fences. Returns the parsed Python object (list or dict).
    Includes more detailed error reporting.
    """
    if not json_text:
        print("Error: Received empty response text from Gemini.", file=sys.stderr)
        return None # Keep returning None on fundamental errors

    cleaned_text = json_text.strip()
    # Attempt to remove markdown code block fences and surrounding whitespace
    # Match ```json ... ``` or just ``` ... ```
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned_text, re.IGNORECASE | re.DOTALL)
    if match:
        cleaned_text = match.group(1).strip()
    # else: # If no markdown found, assume the text is the JSON itself (already stripped)
        # cleaned_text = json_text.strip() # Already done above

    if not cleaned_text:
        print("Error: Cleaned response text (after removing potential markdown) is empty.", file=sys.stderr)
        print(f"Original text was:\n---\n{json_text}\n---", file=sys.stderr)
        return None

    try:
        parsed_data = json.loads(cleaned_text)
        print(f"Successfully parsed JSON data from Gemini response (Type: {type(parsed_data)}).")
        return parsed_data
    except json.JSONDecodeError as e:
        # Provide more context about the decoding error
        error_msg = f"Error: Failed to decode JSON from Gemini response: {e}. "
        # Show the position of the error if available
        error_msg += f"Error at line {e.lineno}, column {e.colno} (char {e.pos})."
        print(error_msg, file=sys.stderr)
        # Log the problematic text for debugging
        print(f"Cleaned text that failed parsing was:\n---\n{cleaned_text}\n---", file=sys.stderr)
        # Optionally show a simplified error via TUI
        show_error("JSON Parsing Error", f"Failed to parse Gemini's response.\nDetails: {e}")
        return None
    except Exception as e:
        # Catch other potential errors during parsing
        error_msg = f"An unexpected error occurred during JSON parsing: {e}"
        print(error_msg, file=sys.stderr)
        print(f"Cleaned text was:\n---\n{cleaned_text}\n---", file=sys.stderr)
        show_error("JSON Parsing Error", f"An unexpected error occurred during parsing.\nDetails: {e}")
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

    # --- Argument Parsing for Optional Input File ---
    parser = argparse.ArgumentParser(
        description="Modify or extend a MIDI file using Gemini, with TUI for settings.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        help="Optional: Path to the input MIDI file. If not provided, a file selector will be shown."
    )
    args = parser.parse_args()


    # --- Determine Input Path (CLI or TUI) ---
    input_midi_path = args.input
    if not input_midi_path:
        print("Input file not provided via command line, launching file selector...")
        input_midi_path = select_input_file()
        if not input_midi_path:
            print("Operation cancelled by user during file selection.")
            sys.exit(0)
        print(f"Selected input file: {input_midi_path}")
    else:
        print(f"Using input file from command line: {input_midi_path}")

    # --- Validate and Load Input MIDI File ---
    try:
        # Check if file exists before trying to load
        if not os.path.exists(input_midi_path):
            raise FileNotFoundError(f"Input MIDI file not found at '{input_midi_path}'")

        print(f"\nLoading MIDI file: {input_midi_path}")
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

        num_tracks = len(midi_file.tracks) # Get number of tracks

    except FileNotFoundError as e:
        error_msg = str(e)
        print(error_msg, file=sys.stderr)
        show_error("File Not Found", error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Error loading MIDI file: {e}"
        print(error_msg, file=sys.stderr)
        show_error("MIDI Load Error", error_msg)
        sys.exit(1)


    # --- Get Remaining User Input via TUI ---
    # Pass the determined input_midi_path and num_tracks to the TUI function
    settings = get_user_input(input_midi_path, num_tracks)
    if not settings:
        print("Operation cancelled by user during settings input.")
        sys.exit(0)

    # Combine input path with other settings
    settings['input_path'] = input_midi_path # Keep for consistency if needed elsewhere, though midi_file is loaded
    output_midi_path = settings['output_path']
    mode = settings['mode']

    # Print selected mode details
    print(f"\nSelected Mode: {mode}")
    if mode == 'extend':
        print(f"Target Track: {settings['target_track_index']}")
        print(f"Bars to extend: {settings['bars_to_extend']}")
    elif mode == 'complement':
        print(f"Complement type: {settings['complement_type']}")


    # --- Parse and Convert to JSON ---
    print("\nParsing MIDI data (all tracks) to JSON format...")
    parse_result = parse_midi_to_mvp_json(midi_file)

    if parse_result:
        mvp_json_data, track_end_ticks = parse_result
        print("Successfully parsed MIDI data.")

        # --- Detailed Analysis Step (Post-MVP) ---
        print("\nRequesting detailed analysis from Gemini (or loading from cache)...")
        # Pass input_midi_path for caching
        analysis_result_data = call_gemini_for_detailed_analysis(mvp_json_data, input_midi_path)

        # --- Show Analysis Results to User ---
        if analysis_result_data: # Check if we got a dictionary
            print("Displaying analysis results...")
            # Pass the dictionary to the TUI function
            show_analysis_results("Gemini Detailed Analysis", analysis_result_data)
        else:
            # Error message is now shown within call_gemini_for_detailed_analysis using show_error
            print("Continuing without displaying detailed analysis due to previous error.")
            # Optionally, add a less specific TUI message here if needed, but the specific one is better.
            # show_error("Analysis Info", "Could not retrieve or parse detailed analysis from Gemini / Cache.")

    else:
        error_msg = "Failed to parse MIDI data into JSON."
        print(error_msg, file=sys.stderr)
        show_error("Parsing Error", error_msg)
        sys.exit(1)

    # --- Call Gemini for Generation based on mode ---
    generated_notes_json_text = None
    if mode == 'extend':
        target_track_index = settings['target_track_index']
        generated_notes_json_text = call_gemini_for_extension(
            mvp_json_data,
            settings['bars_to_extend'],
            target_track_index
        )
    elif mode == 'complement':
        generated_notes_json_text = call_gemini_for_complement(mvp_json_data, settings['complement_type'])

    # Check if the call itself failed (returned None)
    if generated_notes_json_text is None:
        # Specific error should have been shown by the called function via show_error
        error_msg = f"Failed to get valid generation response from Gemini for mode '{mode}'. See previous errors."
        print(error_msg, file=sys.stderr)
        # No need for another show_error here unless the previous one wasn't sufficient
        sys.exit(1)

    print(f"Successfully received generation response from Gemini for mode '{mode}'.")

    # --- Parse Gemini Response ---
    print("\nParsing Gemini response...")
    # This should now correctly parse the list of notes for generation
    generated_notes = parse_gemini_response(generated_notes_json_text)

    # Check if parsing failed (returned None)
    if generated_notes is None:
        # Specific error should have been shown by parse_gemini_response via show_error
        error_msg = "Failed to parse valid data from Gemini generation response. See previous errors."
        print(error_msg, file=sys.stderr)
        # No need for another show_error here
        sys.exit(1)

    # Check if the parsed data is the expected type (list for notes)
    if not isinstance(generated_notes, list):
         error_msg = f"Parsed data from Gemini generation response is not a list of notes. Got type: {type(generated_notes)}"
         print(error_msg, file=sys.stderr)
         show_error("Parsing Error", error_msg)
         sys.exit(1)

    # --- Convert to MIDI Events ---
    start_offset = 0
    if mode == 'extend':
        target_track_index = settings['target_track_index']
        # Use the end tick of the selected track
        if target_track_index < len(track_end_ticks):
            start_offset = track_end_ticks[target_track_index]
        else:
            # Fallback or error if index is somehow invalid (shouldn't happen with TUI validation)
            print(f"Error: Invalid target track index {target_track_index}. Defaulting offset to 0.", file=sys.stderr)
            start_offset = 0

    elif mode == 'complement':
        start_offset = 0 # New track starts from time 0

    new_midi_events = generated_notes_to_midi_events(generated_notes, start_offset)

    # --- Add Events to MIDI File ---
    if mode == 'extend':
        target_track_index = settings['target_track_index']
        print(f"\nAppending {len(new_midi_events)} new events to Track {target_track_index}...")
        # Ensure target track index is valid before extending
        if 0 <= target_track_index < len(midi_file.tracks):
            midi_file.tracks[target_track_index].extend(new_midi_events)
            print("Append successful.")
        else:
             error_msg = f"Error: Invalid target track index {target_track_index} for appending events."
             print(error_msg, file=sys.stderr)
             show_error("MIDI Error", error_msg)
             sys.exit(1)

    elif mode == 'complement':
        # --- Check MIDI type before adding track ---
        if midi_file.type == 0:
            print("\nWarning: Original MIDI is Type 0. Adding a track requires converting the output file to Type 1.", file=sys.stderr)
            midi_file.type = 1 # Change type to allow multiple tracks for saving

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
        # Add note about type change if applicable
        if mode == 'complement' and midi_file.type == 1 and len(midi_file.tracks) > 1:
            # Check if it *was* type 0 implicitly by checking if we just set it to 1
            # A more robust check would involve storing the original type earlier
            # For now, assume if it's complement mode, type 1, and >1 track, it was likely converted
            success_msg += " (Note: Output file is Type 1)."

        print(f"\n{success_msg}")
        show_success("Operation Successful", success_msg)
    except Exception as e:
        error_msg = f"Error saving MIDI file: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Save Error", error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
