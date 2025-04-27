import argparse
import mido
import sys
import json # Added import

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


def main():
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

    # --- Placeholder for next steps ---
    print("Next steps: Call Gemini, modify based on response, save.")
    # ... existing placeholder code ...

if __name__ == "__main__":
    main()
