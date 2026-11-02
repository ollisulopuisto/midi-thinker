import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys

import mido
from dotenv import load_dotenv
from google import genai

from tui import (
    ask_refine_or_save,
    get_refinement_feedback,
    get_song_generation_config,
    get_user_input,
    select_input_file,
    select_song_source,
    show_analysis_results,
    show_error,
    show_generation_preview,
    show_main_menu,
    show_success_with_action,
)

logger = logging.getLogger(__name__)

# Default values if not found in MIDI
DEFAULT_TEMPO = 500000  # 120 bpm
DEFAULT_KEY = "Cmaj"
DEFAULT_TIME_SIGNATURE = {"numerator": 4, "denominator": 4} # Add default time signature
# Instrument program numbers (General MIDI)
DEFAULT_INSTRUMENT = 0 # Acoustic Grand Piano
ACOUSTIC_BASS = 32
DEFAULT_COMPLEMENT_INSTRUMENT = ACOUSTIC_BASS

MODEL_NAME = "gemini-2.0-flash" # Updated model name

def parse_midi_to_mvp_json(midi_file: mido.MidiFile):
    """
    Parses a loaded MIDI file (Type 0 or 1) to extract notes, instruments,
    tempo, key, and time signature into the MVP JSON format.
    Also returns the end tick of each track.
    """
    # Initialize with defaults
    tempo = DEFAULT_TEMPO
    key_signature = DEFAULT_KEY
    time_signature_data = DEFAULT_TIME_SIGNATURE.copy()
    
    meta_changes = []
    all_tracks_data = []
    track_end_ticks = []

    # Helper to process meta messages from a track
    def process_meta(msg, current_tick):
        nonlocal tempo, key_signature
        if msg.type == 'set_tempo':
            meta_changes.append({
                "type": "tempo",
                "tick": current_tick,
                "tempo": msg.tempo,
                "bpm": round(60_000_000 / msg.tempo) if msg.tempo > 0 else "N/A"
            })
        elif msg.type == 'key_signature':
            meta_changes.append({
                "type": "key_signature",
                "tick": current_tick,
                "key": msg.key
            })
        elif msg.type == 'time_signature':
            meta_changes.append({
                "type": "time_signature",
                "tick": current_tick,
                "numerator": msg.numerator,
                "denominator": msg.denominator
            })

    if midi_file.type == 0:
        print("Parsing Type 0 MIDI file (single track)...")
        if not midi_file.tracks:
            return None, None

        track = midi_file.tracks[0]
        notes = []
        current_time_ticks = 0
        active_notes = {}
        first_program_change = None
        found_program_change = False

        for msg in track:
            if msg.is_meta:
                process_meta(msg, current_time_ticks)

            if not found_program_change and msg.type == 'program_change':
                first_program_change = msg.program
                found_program_change = True

            current_time_ticks += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes[msg.note] = (current_time_ticks, msg.velocity)
            elif (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)) and msg.note in active_notes:
                start_tick, velocity = active_notes.pop(msg.note)
                duration_tick = current_time_ticks - start_tick
                if duration_tick >= 0:
                    notes.append({
                        "pitch": msg.note,
                        "start_tick": start_tick,
                        "duration_tick": duration_tick,
                        "velocity": velocity
                    })

        all_tracks_data.append({
            "instrument_program": first_program_change if found_program_change else 0,
            "notes": notes
        })
        track_end_ticks.append(current_time_ticks)

    elif midi_file.type == 1:
        print("Parsing Type 1 MIDI file (multiple tracks)...")
        
        # In Type 1, Meta events are usually in Track 0
        for i, track in enumerate(midi_file.tracks):
            notes = []
            current_time_ticks = 0
            active_notes = {}
            first_program_change = None
            found_program_change = False

            for msg in track:
                if msg.is_meta:
                    process_meta(msg, current_time_ticks)

                if not found_program_change and msg.type == 'program_change':
                    first_program_change = msg.program
                    found_program_change = True

                current_time_ticks += msg.time

                if msg.type == 'note_on' and msg.velocity > 0:
                    active_notes[msg.note] = (current_time_ticks, msg.velocity)
                elif (msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)) and msg.note in active_notes:
                    start_tick, velocity = active_notes.pop(msg.note)
                    duration_tick = current_time_ticks - start_tick
                    if duration_tick >= 0:
                        notes.append({
                            "pitch": msg.note,
                            "start_tick": start_tick,
                            "duration_tick": duration_tick,
                            "velocity": velocity
                        })

            all_tracks_data.append({
                "instrument_program": first_program_change if found_program_change else 0,
                "notes": notes
            })
            track_end_ticks.append(current_time_ticks)

    # Set initial values for the top level from the first detected events
    for change in meta_changes:
        if change['type'] == 'tempo' and tempo == DEFAULT_TEMPO:
            tempo = change['tempo']
        elif change['type'] == 'key_signature' and key_signature == DEFAULT_KEY:
            key_signature = change['key']
        elif change['type'] == 'time_signature' and time_signature_data == DEFAULT_TIME_SIGNATURE:
            time_signature_data = {"numerator": change['numerator'], "denominator": change['denominator']}

    mvp_representation = {
        "tempo": tempo,
        "key_signature": key_signature,
        "time_signature": time_signature_data,
        "meta_changes": meta_changes,
        "ticks_per_beat": midi_file.ticks_per_beat,
        "tracks": all_tracks_data
    }

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
        logger.exception("get_cache_filepath failed")
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
        logger.exception("load_analysis_from_cache failed")
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
        logger.exception("save_analysis_to_cache failed")
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
        client = genai.Client(api_key=api_key)

        # Calculate BPM for prompt context
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
- \"key_signature\": String (e.g., \"Cmaj\", \"Amin\") - Confirm or identify the most likely overall key signature.
- \"tempo_bpm\": Integer - Confirm or identify the primary tempo in BPM.
- \"time_signature\": String (e.g., \"4/4\", \"3/4\") - Confirm the primary time signature ({ts_str} was detected initially).
- \"style_genre\": String - Briefly describe the likely musical style or genre (e.g., \"Classical\", \"Jazz Ballad\", \"Electronic Dance\").
- \"harmony_description\": String - Briefly describe the basic harmonic structure (e.g., \"Simple diatonic chords\", \"Modal harmony\", \"Uses extended jazz chords\").
- \"sections\": List of objects - Identify the likely song sections (e.g., Intro, Verse, Chorus, Outro). Each object should have:
    - \"name\": String (the name of the section)
    - \"start_tick\": Integer (absolute tick where it starts)
    - \"end_tick\": Integer (absolute tick where it ends)

Example JSON Output:
```json
{{
  "key_signature": "Gmaj",
  "tempo_bpm": 140,
  "time_signature": "4/4",
  "style_genre": "Pop Rock",
  "harmony_description": "Primarily uses I-V-vi-IV progression.",
  "sections": [
    {{ "name": "Intro", "start_tick": 0, "end_tick": 1920 }},
    {{ "name": "Verse 1", "start_tick": 1920, "end_tick": 5760 }}
  ]
}}
```

Analysis JSON:
"""
        print("\n--- Sending Detailed Analysis Prompt to Gemini (Requesting JSON) ---")
        # print(prompt) # Uncomment to debug
        print("--- End Detailed Analysis Prompt ---")

        print("\nCalling Gemini API for detailed analysis...")
        
        # New SDK Generation
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        print("Received detailed analysis response from Gemini.")

        if not response.text:
            error_msg = "Gemini detailed analysis response was empty."
            print(error_msg, file=sys.stderr)
            show_error("Gemini Analysis Error", error_msg)
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

    except Exception as e:
        logger.exception("call_gemini_for_detailed_analysis failed")
        error_msg = f"Unexpected error during detailed Gemini analysis: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Analysis Error", error_msg)
        return None

def call_gemini_for_extension(mvp_json_data: dict, bars_to_extend: int, target_track_indices: list[int], style_variation: str = "", sections: list | None = None, feedback: str = "", previous_response: str = ""):
    """
    Constructs a prompt and calls the Gemini API to generate extended notes
    for the specified target tracks, using all tracks as context.
    Can also handle refinement based on feedback.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        return None

    try:
        client = genai.Client(api_key=api_key)

        ticks_per_beat = mvp_json_data.get('ticks_per_beat', 480)
        time_sig = mvp_json_data.get('time_signature', DEFAULT_TIME_SIGNATURE)
        numerator = time_sig.get('numerator', DEFAULT_TIME_SIGNATURE['numerator'])
        ticks_per_bar = ticks_per_beat * numerator
        target_extension_ticks = ticks_per_bar * bars_to_extend

        tracks_str = ", ".join([f"Track {i}" for i in target_track_indices])
        extension_request = (f"Extend the musical piece by approximately {bars_to_extend} bars "
                             f"(target duration: around {target_extension_ticks} ticks). "
                             f"Generate new notes for the following tracks: {tracks_str}. "
                             f"Use the existing notes from all tracks as musical context.")
        if sections:
            sections_str = ", ".join([f"{s.get('name')} ({s.get('start_tick')}-{s.get('end_tick')})" for s in sections])
            extension_request += f" The current song structure is: {sections_str}."
        if style_variation:
            extension_request += f" Apply the following style variation: '{style_variation}'."
        
        refinement_context = ""
        if feedback and previous_response:
            refinement_context = f"\n\n**REFINEMENT REQUEST**:\nYou previously suggested the following notes:\n{previous_response}\n\nThe user liked it but has the following feedback for refinement: '{feedback}'.\nPlease generate a NEW version that incorporates this feedback while maintaining the overall context."


        prompt = f"""
You are a MIDI music generation assistant.
Analyze the provided musical data in JSON format which contains multiple tracks.
Generate new musical material that extends the piece in a similar style.

**IMPORTANT**: Generate new notes for the following tracks: {tracks_str}.
You can use the content of other tracks as musical context for your generation.

**OPTIONAL**: You may also suggest shifts in tempo or key signature at the start of the extension.
To do this, include a \"meta_changes\" key in your output JSON.

Input Data (Multiple Tracks):
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {extension_request}{refinement_context}

Output ONLY a JSON object containing:
1. A key for each track index (e.g., \"0\", \"1\") with a list of note objects.
2. (Optional) A \"meta_changes\" key with a list of objects like:
   - {{ \"type\": \"tempo\", \"bpm\": 140, \"tick\": 0 }}
   - {{ \"type\": \"key_signature\", \"key\": \"G\", \"tick\": 0 }}
   - {{ \"type\": \"time_signature\", \"numerator\": 3, \"denominator\": 4, \"tick\": 0 }}
   Note: \"tick\" is relative to the start of the extension.

Each note object must have \"pitch\", \"start_tick\", \"duration_tick\", and \"velocity\".
The \"start_tick\" for the new notes should be relative to the beginning of the *extension* (i.e., start from 0 or a small positive value).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format:
```json
{{
  \"0\": [
    {{ \"pitch\": 60, \"start_tick\": 0, \"duration_tick\": 480, \"velocity\": 90 }}
  ],
  \"meta_changes\": [
    {{ \"type\": \"tempo\", \"bpm\": 130, \"tick\": 0 }}
  ]
}}
```

Generated Notes JSON:
"""
        print(f"\n--- Sending Prompt to Gemini (Extend Tracks: {target_track_indices}) ---")
        print("--- End Prompt ---")

        print("\nCalling Gemini API...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        print("Received response from Gemini.")

        if not response.text:
            error_msg = "Gemini extension response was empty."
            print(error_msg, file=sys.stderr)
            show_error("Gemini Extension Error", error_msg)
            return None

        return response.text

    except Exception as e:
        logger.exception("call_gemini_for_extension failed")
        error_msg = f"Unexpected error calling Gemini API for extension: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Error", error_msg)
        return None

def call_gemini_for_complement(mvp_json_data: dict, complement_type: str, style_variation: str = "", instrument_hint: int | None = None, feedback: str = "", previous_response: str = ""):
    """
    (Post-MVP)
    Constructs a prompt and calls the Gemini API to generate new complementary tracks.
    Can also handle refinement based on feedback.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.", file=sys.stderr)
        return None

    try:
        client = genai.Client(api_key=api_key)

        key_signature = mvp_json_data.get('key_signature', DEFAULT_KEY)
        tempo_microseconds = mvp_json_data.get('tempo', DEFAULT_TEMPO)
        bpm = round(60_000_000 / tempo_microseconds) if tempo_microseconds > 0 else "N/A"

        generation_request = f"Generate new musical parts to complement the existing tracks. The parts should be a '{complement_type}'."
        if instrument_hint is not None:
            generation_request += f" One of the tracks should ideally use instrument program {instrument_hint}."
        if "bassline" in complement_type.lower():
             generation_request += " Focus on lower registers and provide harmonic support."
        elif "harmony" in complement_type.lower():
             generation_request += " Focus on chords or pads that fit the existing harmony."
        elif "counter-melody" in complement_type.lower():
             generation_request += " Create independent melodic lines that interact interestingly with the existing melody/melodies."
        else:
             generation_request += " Generate notes that musically fit well with the existing material."
        
        if style_variation:
            generation_request += f" Apply the following style variation: '{style_variation}'."
        
        refinement_context = ""
        if feedback and previous_response:
            refinement_context = f"\n\n**REFINEMENT REQUEST**:\nYou previously suggested the following arrangement:\n{previous_response}\n\nThe user has the following feedback for refinement: '{feedback}'.\nPlease generate a NEW version that incorporates this feedback."


        prompt = f"""
You are a MIDI music composition assistant.
Analyze the provided musical data (JSON format, multiple tracks).
Generate one or more *new* musical tracks as specified in the request.

Input Data (Multiple Tracks):
```json
{json.dumps(mvp_json_data, indent=2)}
```

Request: {generation_request}
The piece is in {key_signature} at approximately {bpm} BPM.{refinement_context}

Output ONLY a JSON object with a \"tracks\" key, which is a list of track objects.
Each track object should contain:
- \"name\": String (e.g., \"Bassline\", \"Pad\")
- \"instrument_program\": Integer (General MIDI program number)
- \"is_drum\": Boolean (true if this is a drum track on Channel 10)
- \"notes\": A list of note objects, each with \"pitch\", \"start_tick\", \"duration_tick\", and \"velocity\".

The \"start_tick\" for the new notes should be relative to the beginning of the piece (i.e., start from 0 or a small positive value, aligning with the original structure).
Do not include the original notes in the output.
Ensure the output is valid JSON.

Example output format:
```json
{{
  \"tracks\": [
    {{
      \"name\": \"Acoustic Bass\",
      \"instrument_program\": 32,
      \"notes\": [
        {{ \"pitch\": 36, \"start_tick\": 0, \"duration_tick\": 960, \"velocity\": 80 }}
      ]
    }}
  ]
}}
```

Generated Notes JSON:
"""
        print("\n--- Sending Complement Prompt to Gemini ---")
        print("--- End Complement Prompt ---")

        print("\nCalling Gemini API for complement generation...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        print("Received complement response from Gemini.")

        if not response.text:
            error_msg = "Gemini complement response was empty."
            print(error_msg, file=sys.stderr)
            show_error("Gemini Complement Error", error_msg)
            return None

        return response.text

    except Exception as e:
        logger.exception("call_gemini_for_complement failed")
        error_msg = f"Unexpected error calling Gemini API for complement: {e}"
        print(error_msg, file=sys.stderr)
        show_error("Gemini Error", error_msg)
        return None

def parse_gemini_response(json_text: str):
    """
    Cleans and parses the JSON string potentially returned by Gemini.
    """
    if not json_text:
        print("Error: Received empty response text from Gemini.", file=sys.stderr)
        return None

    cleaned_text = json_text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned_text, re.IGNORECASE | re.DOTALL)
    if match:
        cleaned_text = match.group(1).strip()

    if not cleaned_text:
        return None

    try:
        parsed_data = json.loads(cleaned_text)
        print(f"Successfully parsed JSON data from Gemini response (Type: {type(parsed_data)}).")
        return parsed_data
    except Exception as e:
        logger.exception("parse_gemini_response failed")
        print(f"Error parsing Gemini response: {e}", file=sys.stderr)
        show_error("JSON Parsing Error", f"Failed to parse Gemini's response.\nDetails: {e}")
        return None

def generated_notes_to_midi_events(generated_notes: list, start_offset_ticks: int):
    """
    Converts a list of note dictionaries (from parsed JSON) into a list of
    mido MIDI messages with correct delta times, offset by start_offset_ticks.
    """
    events = []
    for note in generated_notes:
        try:
            pitch = int(note['pitch'])
            start_tick = int(note['start_tick']) + start_offset_ticks
            duration_tick = int(note['duration_tick'])
            velocity = int(note['velocity'])
            end_tick = start_tick + duration_tick

            pitch = max(0, min(127, pitch))
            velocity = max(0, min(127, velocity))
            duration_tick = max(duration_tick, 0)

            if velocity == 0:
                 events.append({'type': 'note_off', 'tick': start_tick, 'pitch': pitch, 'velocity': 0})
            else:
                events.append({'type': 'note_on', 'tick': start_tick, 'pitch': pitch, 'velocity': velocity})
                events.append({'type': 'note_off', 'tick': end_tick, 'pitch': pitch, 'velocity': 0})

        except Exception as e:
            logger.exception("generated_notes_to_midi_events failed")
            print(f"Warning: Skipping note due to error {e}: {note}", file=sys.stderr)
            continue

    events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))

    midi_messages = []
    last_event_tick = start_offset_ticks
    for event in events:
        delta_time = event['tick'] - last_event_tick
        delta_time = max(delta_time, 0)

        midi_messages.append(mido.Message(
            event['type'],
            note=event['pitch'],
            velocity=event['velocity'],
            time=delta_time
        ))
        last_event_tick = event['tick']

    print(f"Converted {len(generated_notes)} notes into {len(midi_messages)} MIDI messages.")
    return midi_messages


def humanize_mido_events(messages, velocity_range=10, timing_range=5):
    """Applies subtle random variations to mido messages (velocity and delta time)."""
    for msg in messages:
        if msg.type == 'note_on' and msg.velocity > 0:
            msg.velocity = max(1, min(127, msg.velocity + random.randint(-velocity_range, velocity_range)))

        jitter = random.randint(-timing_range, timing_range)
        msg.time = max(0, msg.time + jitter)
    return messages


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Modify or extend a MIDI file using Gemini.")
    parser.add_argument("-i", "--input", type=str, help="Path to the input MIDI file.")
    parser.add_argument("-g", "--generate", action="store_true", help="Generate new song from song_data.py")
    args = parser.parse_args()

    # If --generate flag is passed, go directly to generation
    if args.generate:
        main_mode = 'generate'
    elif args.input:
        main_mode = 'modify'
    else:
        # Show main menu
        main_mode = show_main_menu()
        if not main_mode:
            sys.exit(0)

    # --- GENERATE MODE ---
    if main_mode == 'generate':
        import importlib.util
        
        # Select song source file
        song_source_path = select_song_source()
        if not song_source_path:
            sys.exit(0)
        
        # Dynamically load the song_data module from the selected file
        try:
            spec = importlib.util.spec_from_file_location("song_data", song_source_path)
            song_data = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(song_data)
        except Exception as e:
            logger.exception("main failed")
            show_error("Import Error", f"Could not load song source '{song_source_path}': {e}")
            sys.exit(1)
        
        try:
            import studio
            # Inject the loaded song_data into studio module
            studio.song_data = song_data
        except ImportError as e:
            show_error("Import Error", f"Could not import studio module: {e}")
            sys.exit(1)
        
        # Show preview of what will be generated
        show_generation_preview(song_data.TRACKS, song_data.ARRANGEMENT)
        
        # Get optional config overrides (use song_data defaults)
        config = get_song_generation_config()
        if not config:
            sys.exit(0)
        
        # Override song_data values if user provided different ones
        if config['filename']:
            song_data.FILENAME = config['filename']
        if config['tempo']:
            song_data.TEMPO = config['tempo']
        
        # Generate MIDI
        print(f"\nGenerating: {song_data.FILENAME} at {song_data.TEMPO} BPM")
        print(f"Source: {song_source_path}")
        midi_path = studio.generate_midi()
        
        # Generate tabs if requested
        tabs_path = None
        if config.get('generate_tabs'):
            tabs_path = studio.generate_tabs()
        
        # Show success with path to open
        message = f"Created: {midi_path}\nTempo: {song_data.TEMPO} BPM\nSource: {song_source_path}"
        if tabs_path:
            message += f"\nTabs: {tabs_path}"
        
        show_success_with_action("Generation Complete", message, midi_path)
        print("\n--- STUDIO SESSION COMPLETE ---")
        sys.exit(0)

    # --- MODIFY MODE ---
    input_midi_path = args.input or select_input_file()
    if not input_midi_path:
        sys.exit(0)

    try:
        print(f"\nLoading MIDI file: {input_midi_path}")
        original_midi = mido.MidiFile(input_midi_path)
        if not original_midi.tracks:
             sys.exit(1)
        
        midi_type = original_midi.type
        num_logical_tracks = len(original_midi.tracks) if midi_type != 0 else 1

    except Exception as e:
        logger.exception("main failed")
        print(f"Error loading MIDI: {e}", file=sys.stderr)
        sys.exit(1)

    settings = get_user_input(input_midi_path, num_logical_tracks, midi_type)
    if not settings:
        sys.exit(0)

    output_midi_path = settings['output_path']
    mode = settings['mode']

    parse_result = parse_midi_to_mvp_json(original_midi)
    if not parse_result or parse_result[0] is None:
        sys.exit(1)
    
    mvp_json_data, _track_end_ticks = parse_result
    analysis_result_data = call_gemini_for_detailed_analysis(mvp_json_data, input_midi_path)
    if analysis_result_data:
        show_analysis_results("Gemini Detailed Analysis", analysis_result_data)

    current_feedback = ""
    previous_response_text = ""
    
    while True:
        # Clone the original MIDI structure for this refinement step
        # Since we can't deepcopy easily, we'll start with a fresh load or clone
        working_midi = mido.MidiFile(input_midi_path)
        
        generated_json_text = None
        if mode == 'extend':
            generated_json_text = call_gemini_for_extension(
                mvp_json_data, settings['bars_to_extend'], settings['target_track_indices'],
                settings.get('style_variation', ''), analysis_result_data.get('sections'),
                current_feedback, previous_response_text
            )
        elif mode == 'complement':
            generated_json_text = call_gemini_for_complement(
                mvp_json_data, settings['complement_type'], settings.get('style_variation', ''),
                settings.get('instrument_program'), current_feedback, previous_response_text
            )

        if generated_json_text is None:
            sys.exit(1)

        previous_response_text = generated_json_text
        generated_notes = parse_gemini_response(generated_json_text)
        if generated_notes is None:
            sys.exit(1)

        # Apply generated content to working_midi
        start_offset = 0
        if mode == 'extend':
            suggested_meta = generated_notes.get("meta_changes", [])
            if suggested_meta and len(working_midi.tracks) > 0:
                meta_track = working_midi.tracks[0]
                if meta_track and meta_track[-1].is_meta and meta_track[-1].type == 'end_of_track':
                    meta_track.pop()
                for change in suggested_meta:
                    if change.get("type") == "tempo" and change.get("bpm"):
                        meta_track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(change.get("bpm")), time=0))
                    elif change.get("type") == "key_signature" and change.get("key"):
                        try:
                            meta_track.append(mido.MetaMessage('key_signature', key=change.get("key"), time=0))
                        except Exception:
                            logger.exception("main failed")
                    elif change.get("type") == "time_signature" and change.get("numerator") and change.get("denominator"):
                        meta_track.append(mido.MetaMessage('time_signature', numerator=change.get("numerator"), denominator=change.get("denominator"), time=0))
                meta_track.append(mido.MetaMessage('end_of_track', time=0))

            for track_idx_str, notes in generated_notes.items():
                if track_idx_str == "meta_changes":
                    continue
                try: 
                    t_idx = int(track_idx_str)
                    actual_idx = t_idx if midi_type != 0 else 0
                    if 0 <= actual_idx < len(working_midi.tracks):
                        target_track = working_midi.tracks[actual_idx]
                        if target_track and target_track[-1].is_meta and target_track[-1].type == 'end_of_track':
                            target_track.pop()
                        events = generated_notes_to_midi_events(notes, start_offset)
                        if settings.get('humanize'):
                            humanize_mido_events(events)
                        target_track.extend(events)
                        target_track.append(mido.MetaMessage('end_of_track', time=0))
                except Exception:
                    logger.exception("main failed")
                    continue

        elif mode == 'complement':
            if working_midi.type == 0:
                working_midi.type = 1
            for gen_track in generated_notes.get("tracks", []):
                new_track = mido.MidiTrack()
                working_midi.tracks.append(new_track)
                new_track.append(mido.MetaMessage('track_name', name=gen_track.get("name", "New Track"), time=0))
                channel = 9 if gen_track.get("is_drum") else 0
                new_track.append(mido.Message('program_change', program=gen_track.get("instrument_program", 0), time=0, channel=channel))
                events = generated_notes_to_midi_events(gen_track.get("notes", []), start_offset)
                if settings.get('humanize'):
                    humanize_mido_events(events)
                for msg in events:
                    msg.channel = channel
                new_track.extend(events)
                new_track.append(mido.MetaMessage('end_of_track', time=0))

        # Ask user for refinement
        action = ask_refine_or_save()
        if action == 'save':
            try:
                working_midi.save(output_midi_path)
                show_success_with_action("Success", f"Saved to {output_midi_path}", output_midi_path)
                break
            except Exception as e:
                logger.exception("main failed")
                show_error("Save Error", str(e))
                break
        elif action == 'refine':
            feedback = get_refinement_feedback()
            if feedback:
                current_feedback = feedback
            else:
                continue
        else:
            break

if __name__ == "__main__":
    main()
