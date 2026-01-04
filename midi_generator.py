import mido
import re
import sys

# --- MIDI Constants ---
TICKS_PER_BEAT = 480  # Standard resolution
DEFAULT_BPM = 120     # Default tempo if not provided
DRUM_CHANNEL = 9      # MIDI channel 10 (0-indexed) for drums
MELODY_CHANNEL = 0    # Default MIDI channel 1 for melody
HARMONY_CHANNEL_1 = 1 # Default MIDI channel 2 for harmony 1
HARMONY_CHANNEL_2 = 2 # Default MIDI channel 3 for harmony 2
# CHORD_CHANNEL = 3     # MIDI channel 4 (used for meta messages in original)

# --- Helper Functions with Debugging ---

def note_name_to_midi(note_name):
    """Converts a note name (e.g., C4, F#5, C-1) to a MIDI number."""
    notes = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5,
             'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
    # Allow negative octaves: e.g. C-1
    match = re.match(r'([A-Ga-g][#b]?)(-?\d+)', note_name)
    if not match:
        raise ValueError(f"Invalid note name format '{note_name}'. Expected format like 'C4', 'F#5', 'C-1'.")

    name_part = match.group(1)
    octave = int(match.group(2))

    name = name_part[0].upper()
    if len(name_part) > 1:
        name += name_part[1].lower() # Handle # or b

    if name not in notes:
        enharmonic_map = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
        sharp_map = {v: k for k, v in enharmonic_map.items()}

        original_name = name
        if name in enharmonic_map:
            name = enharmonic_map[name]
            print(f"DEBUG [note_name_to_midi]: Enharmonic conversion {original_name} -> {name}", file=sys.stderr)
        elif name in sharp_map:
            name = sharp_map[name]
            print(f"DEBUG [note_name_to_midi]: Enharmonic conversion {original_name} -> {name}", file=sys.stderr)
        else:
            raise ValueError(f"Unknown base note '{name_part}' in '{note_name}'.")

    midi_note = notes[name] + (octave + 1) * 12 # MIDI C4 = 60
    clamped_midi_note = max(0, min(127, midi_note))
    if clamped_midi_note != midi_note:
        print(f"DEBUG [note_name_to_midi]: Clamped MIDI note {midi_note} to {clamped_midi_note} for '{note_name}'.", file=sys.stderr)

    # print(f"DEBUG [note_name_to_midi]: Converted '{note_name}' -> {clamped_midi_note}", file=sys.stderr)
    return clamped_midi_note


def drum_name_to_midi(instrument_name):
    """Converts common drum instrument names to General MIDI numbers (channel 10)."""
    name = instrument_name.lower().strip()
    mapping = {
        ("bass drum", "kick", "bassorumpu"): 36,
        ("acoustic snare",): 38, # More specific first
        ("electric snare",): 40,
        ("snare", "virveli"): 38, # General snare
        ("low floor tom", "floor tom 1"): 41,
        ("closed hi-hat", "closed hh", "hi-hat (suljettu)"): 42,
        ("high floor tom", "floor tom 2"): 43,
        ("pedal hi-hat",): 44,
        ("low tom", "tom 3"): 45,
        ("open hi-hat", "open hh", "hi-hat (avoin)"): 46,
        ("low-mid tom", "tom 2"): 47,
        ("hi-mid tom", "tom 1"): 48,
        ("crash cymbal 1", "crash 1", "crash"): 49, # General crash
        ("high tom", "tom 0"): 50,
        ("ride cymbal 1", "ride 1", "ride"): 51, # General ride
        ("chinese cymbal",): 52,
        ("ride bell",): 53,
        ("tambourine",): 54,
        ("splash cymbal",): 55,
        ("cowbell",): 56,
        ("crash cymbal 2", "crash 2"): 57,
        ("vibraslap",): 58,
        ("ride cymbal 2", "ride 2"): 59,
        ("hi bongo",): 60,
        ("low bongo",): 61,
        ("mute hi conga",): 62,
        ("open hi conga",): 63,
        ("low conga",): 64,
        ("high timbale",): 65,
        ("low timbale",): 66,
        ("hand clap", "clap"): 39,
        ("rim shot", "rim"): 37,
        ("tom",): 45, # General tom
        ("hi-hat", "hh"): 42, # General hi-hat
        ("cymbal",): 49, # General cymbal
    }

    for names, note in mapping.items():
        if any(n in name for n in names):
            print(f"DEBUG [drum_name_to_midi]: Mapped '{instrument_name}' -> {note}", file=sys.stderr)
            return note

    print(f"DEBUG [drum_name_to_midi]: Unknown drum sound '{instrument_name}'. Defaulting to Acoustic Snare (38).", file=sys.stderr)
    return 38 # Default: Acoustic Snare

def seconds_to_ticks(seconds, bpm, ticks_per_beat):
    """Converts time in seconds to MIDI ticks."""
    if bpm <= 0:
        print(f"DEBUG [seconds_to_ticks]: Invalid BPM ({bpm}). Using default 120.", file=sys.stderr)
        bpm = 120
    if ticks_per_beat <= 0:
        print(f"DEBUG [seconds_to_ticks]: Invalid ticks_per_beat ({ticks_per_beat}). Using default 480.", file=sys.stderr)
        ticks_per_beat = 480

    beats = (float(seconds) * float(bpm)) / 60.0
    ticks = int(round(beats * float(ticks_per_beat)))
    print(f"DEBUG [seconds_to_ticks]: {seconds:.3f}s @ {bpm} BPM, {ticks_per_beat} TPB -> {beats:.3f} beats -> {ticks} ticks", file=sys.stderr)
    return ticks

def midi_key_name(key_string):
    """ Converts 'C Major', 'A Minor' style string to mido's format ('C', 'Am'). """
    print(f"DEBUG [midi_key_name]: Input key string: '{key_string}'", file=sys.stderr)
    parts = key_string.split()
    if not parts:
        print("DEBUG [midi_key_name]: Empty key string, defaulting to 'C'.", file=sys.stderr)
        return 'C'

    key = parts[0].capitalize()
    # Ensure sharps/flats are handled correctly
    if len(key) > 1 and key[1] in ['#', 'b']:
        pass # Already correct format like C# or Bb
    elif len(key) > 1: # Handle Csharp, Gflat etc.
         if key[1:].lower() == 'sharp':
             key = key[0] + '#'
         elif key[1:].lower() == 'flat':
             key = key[0] + 'b'
         else:
             key = key[0] # Fallback: just take the first letter

    mode = 'major' # Default
    if len(parts) > 1 and parts[1].lower() in ['minor', 'molli', 'm']:
        mode = 'minor'

    mido_key = key + 'm' if mode == 'minor' else key
    print(f"DEBUG [midi_key_name]: Converted to mido key: '{mido_key}'", file=sys.stderr)
    return mido_key

# --- Main MIDI Creation Function ---

def create_midi_file(data, output_filename="output.mid", ticks_per_beat=TICKS_PER_BEAT):
    """Creates a MIDI file from the structured analysis data."""
    print(f"DEBUG [create_midi_file]: Starting MIDI creation for '{output_filename}'", file=sys.stderr)
    print(f"DEBUG [create_midi_file]: Input data keys: {list(data.keys())}", file=sys.stderr)

    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    print(f"DEBUG [create_midi_file]: Initialized MidiFile type=1, ticks_per_beat={ticks_per_beat}", file=sys.stderr)

    current_bpm = data.get('tempo', DEFAULT_BPM)
    if current_bpm <= 0:
        print(f"DEBUG [create_midi_file]: Invalid BPM ({current_bpm}) in data. Using default {DEFAULT_BPM}.", file=sys.stderr)
        current_bpm = DEFAULT_BPM
    print(f"DEBUG [create_midi_file]: Using BPM: {current_bpm}", file=sys.stderr)

    # --- Track 0: Meta Messages ---
    meta_track = mido.MidiTrack()
    mid.tracks.append(meta_track)
    meta_track.append(mido.MetaMessage('track_name', name='Meta Info', time=0))
    print("DEBUG [create_midi_file]: Added Meta Info track.", file=sys.stderr)

    # Set Tempo
    try:
        tempo_usec = mido.bpm2tempo(current_bpm)
        meta_track.append(mido.MetaMessage('set_tempo', tempo=tempo_usec, time=0))
        print(f"DEBUG [create_midi_file]: Set tempo: {current_bpm} BPM ({tempo_usec} usec/beat)", file=sys.stderr)
    except ValueError as e:
        print(f"ERROR [create_midi_file]: Failed to convert BPM {current_bpm} to tempo: {e}. Skipping tempo message.", file=sys.stderr)


    # Set Key Signature
    key_input = data.get('key', 'C Major')
    try:
        mido_key = midi_key_name(key_input)
        meta_track.append(mido.MetaMessage('key_signature', key=mido_key, time=0))
        print(f"DEBUG [create_midi_file]: Set key signature: '{mido_key}' (from '{key_input}')", file=sys.stderr)
    except Exception as e:
        print(f"ERROR [create_midi_file]: Failed to set key signature from '{key_input}': {e}. Skipping key signature.", file=sys.stderr)


    # Add Chord Markers
    last_meta_tick = 0
    chords = data.get("chords", [])
    print(f"DEBUG [create_midi_file]: Processing {len(chords)} chords for markers.", file=sys.stderr)
    for i, chord in enumerate(chords):
        try:
            chord_time_sec = chord.get('time')
            chord_name = chord.get('name')
            if chord_time_sec is None or chord_name is None:
                print(f"DEBUG [create_midi_file]: Skipping chord {i} due to missing time/name: {chord}", file=sys.stderr)
                continue

            chord_tick = seconds_to_ticks(chord_time_sec, current_bpm, ticks_per_beat)
            delta_time = max(0, chord_tick - last_meta_tick)
            meta_track.append(mido.MetaMessage('marker', text=chord_name, time=delta_time))
            print(f"DEBUG [create_midi_file]: Added chord marker: '{chord_name}' at tick {chord_tick} (delta {delta_time})", file=sys.stderr)
            last_meta_tick = chord_tick
        except Exception as e:
            print(f"ERROR [create_midi_file]: Failed to process chord marker {i} ({chord}): {e}", file=sys.stderr)

    # --- Track 1: Drums ---
    drum_track = mido.MidiTrack()
    mid.tracks.append(drum_track)
    drum_track.append(mido.MetaMessage('track_name', name='Drums', time=0))
    # Set channel to drums (channel 10 = index 9)
    drum_track.append(mido.Message('program_change', program=0, time=0, channel=DRUM_CHANNEL)) # Standard Drum Kit
    print(f"DEBUG [create_midi_file]: Added Drum track on channel {DRUM_CHANNEL + 1}.", file=sys.stderr)

    drum_events = []
    drum_hits = data.get("drums", [])
    print(f"DEBUG [create_midi_file]: Processing {len(drum_hits)} drum hits.", file=sys.stderr)
    for i, hit in enumerate(drum_hits):
        try:
            hit_time_sec = hit.get('time')
            instrument_name = hit.get('instrument')
            if hit_time_sec is None or instrument_name is None:
                 print(f"DEBUG [create_midi_file]: Skipping drum hit {i} due to missing time/instrument: {hit}", file=sys.stderr)
                 continue

            tick = seconds_to_ticks(hit_time_sec, current_bpm, ticks_per_beat)
            note = drum_name_to_midi(instrument_name)
            velocity = 100 # Default velocity for drums
            duration_ticks = 60 # Short duration for drum hits

            drum_events.append({'tick': tick, 'type': 'note_on', 'note': note, 'velocity': velocity, 'channel': DRUM_CHANNEL})
            drum_events.append({'tick': tick + duration_ticks, 'type': 'note_off', 'note': note, 'velocity': 0, 'channel': DRUM_CHANNEL})
            # print(f"DEBUG [create_midi_file]: Prepared drum event: {instrument_name} (note {note}) at tick {tick}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR [create_midi_file]: Failed to process drum hit {i} ({hit}): {e}", file=sys.stderr)


    # Sort drum events and add to track
    drum_events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1)) # Note_off first at same tick
    last_drum_tick = 0
    for event in drum_events:
        delta_time = max(0, event['tick'] - last_drum_tick)
        msg = mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel'])
        drum_track.append(msg)
        # print(f"DEBUG [create_midi_file]: Added drum message: {msg}", file=sys.stderr)
        last_drum_tick = event['tick']
    print(f"DEBUG [create_midi_file]: Added {len(drum_track) - 2} messages to Drum track.", file=sys.stderr) # -2 for name and program change

    # --- Track 2: Melody ---
    melody_track = mido.MidiTrack()
    mid.tracks.append(melody_track)
    melody_track.append(mido.MetaMessage('track_name', name='Lead Melody', time=0))
    melody_track.append(mido.Message('program_change', program=0, time=0, channel=MELODY_CHANNEL)) # Default: Piano
    print(f"DEBUG [create_midi_file]: Added Melody track on channel {MELODY_CHANNEL + 1}.", file=sys.stderr)

    note_events_melody = []
    melody_notes = data.get("melody", [])
    print(f"DEBUG [create_midi_file]: Processing {len(melody_notes)} melody notes.", file=sys.stderr)
    for i, note_info in enumerate(melody_notes):
        try:
            time_sec = note_info.get('time')
            note_name = note_info.get('note')
            duration_sec = note_info.get('duration')
            if time_sec is None or note_name is None or duration_sec is None:
                print(f"DEBUG [create_midi_file]: Skipping melody note {i} due to missing data: {note_info}", file=sys.stderr)
                continue

            start_tick = seconds_to_ticks(time_sec, current_bpm, ticks_per_beat)
            duration_ticks = seconds_to_ticks(duration_sec, current_bpm, ticks_per_beat)
            duration_ticks = max(1, duration_ticks) # Ensure minimum duration
            end_tick = start_tick + duration_ticks
            midi_note = note_name_to_midi(note_name)
            velocity = 90 # Default velocity

            note_events_melody.append({'tick': start_tick, 'type': 'note_on', 'note': midi_note, 'velocity': velocity, 'channel': MELODY_CHANNEL})
            note_events_melody.append({'tick': end_tick, 'type': 'note_off', 'note': midi_note, 'velocity': 0, 'channel': MELODY_CHANNEL})
            # print(f"DEBUG [create_midi_file]: Prepared melody event: {note_name} (note {midi_note}) at tick {start_tick}, duration {duration_ticks}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR [create_midi_file]: Failed to process melody note {i} ({note_info}): {e}", file=sys.stderr)

    # Sort melody events and add to track
    note_events_melody.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))
    last_melody_tick = 0
    for event in note_events_melody:
        delta_time = max(0, event['tick'] - last_melody_tick)
        msg = mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel'])
        melody_track.append(msg)
        # print(f"DEBUG [create_midi_file]: Added melody message: {msg}", file=sys.stderr)
        last_melody_tick = event['tick']
    print(f"DEBUG [create_midi_file]: Added {len(melody_track) - 2} messages to Melody track.", file=sys.stderr)

    # --- Subsequent Tracks: Harmonies ---
    harmony_groups = {}
    harmony_notes_all = data.get("harmonies", [])
    print(f"DEBUG [create_midi_file]: Processing {len(harmony_notes_all)} harmony notes.", file=sys.stderr)
    for note_info in harmony_notes_all:
        group_name = note_info.get("group", "Default Harmony")
        if group_name not in harmony_groups:
            harmony_groups[group_name] = []
        harmony_groups[group_name].append(note_info)
    print(f"DEBUG [create_midi_file]: Found harmony groups: {list(harmony_groups.keys())}", file=sys.stderr)

    # Define channel mapping (can be expanded)
    harmony_channel_map = {
        "Default Harmony": HARMONY_CHANNEL_1,
        "Harmonia 1 (Jouset)": HARMONY_CHANNEL_1, # Example mapping
        "Harmonia 2 (Padi)": HARMONY_CHANNEL_2,   # Example mapping
    }
    used_channels = {MELODY_CHANNEL, DRUM_CHANNEL}
    next_available_channel = HARMONY_CHANNEL_1 # Start searching from here

    for group_name, notes in harmony_groups.items():
        print(f"DEBUG [create_midi_file]: Processing harmony group '{group_name}' with {len(notes)} notes.", file=sys.stderr)

        # Assign channel
        current_harmony_channel = harmony_channel_map.get(group_name)
        if current_harmony_channel is None or current_harmony_channel in used_channels:
            print(f"DEBUG [create_midi_file]: Channel for '{group_name}' not pre-defined or already used. Finding next available.", file=sys.stderr)
            while next_available_channel in used_channels or next_available_channel == DRUM_CHANNEL:
                next_available_channel += 1
                if next_available_channel > 15:
                    print("DEBUG [create_midi_file]: Ran out of MIDI channels! Reusing channel 1.", file=sys.stderr)
                    next_available_channel = 1 # Fallback, avoid drum channel 9
                    if next_available_channel == DRUM_CHANNEL:
                        next_available_channel += 1 # Skip drum channel again
                    break
            current_harmony_channel = next_available_channel
            harmony_channel_map[group_name] = current_harmony_channel # Store for potential future use
            used_channels.add(current_harmony_channel)
            next_available_channel += 1 # Move to the next for the subsequent group
        else:
            used_channels.add(current_harmony_channel) # Mark pre-defined channel as used

        print(f"DEBUG [create_midi_file]: Assigning channel {current_harmony_channel + 1} to group '{group_name}'.", file=sys.stderr)

        harmony_track = mido.MidiTrack()
        mid.tracks.append(harmony_track)
        harmony_track.append(mido.MetaMessage('track_name', name=f'Harmony: {group_name}', time=0))

        # Set instrument (basic guess based on name)
        program = 48 # Default: Strings
        if "pad" in group_name.lower():
            program = 89 # Warm Pad
        elif "choir" in group_name.lower() or "aah" in group_name.lower():
            program = 52 # Choir Aahs
        elif "bass" in group_name.lower():
            program = 33 # Electric Bass (finger)
        harmony_track.append(mido.Message('program_change', program=program, time=0, channel=current_harmony_channel))
        print(f"DEBUG [create_midi_file]: Set instrument for '{group_name}' to program {program} on channel {current_harmony_channel + 1}.", file=sys.stderr)

        harmony_events = []
        for i, note_info in enumerate(notes):
            try:
                time_sec = note_info.get('time')
                note_name = note_info.get('note')
                duration_sec = note_info.get('duration')
                if time_sec is None or note_name is None or duration_sec is None:
                    print(f"DEBUG [create_midi_file]: Skipping harmony note {i} in group '{group_name}' due to missing data: {note_info}", file=sys.stderr)
                    continue

                start_tick = seconds_to_ticks(time_sec, current_bpm, ticks_per_beat)
                duration_ticks = seconds_to_ticks(duration_sec, current_bpm, ticks_per_beat)
                duration_ticks = max(1, duration_ticks)
                end_tick = start_tick + duration_ticks
                midi_note = note_name_to_midi(note_name)
                velocity = 70 # Default velocity for harmony

                harmony_events.append({'tick': start_tick, 'type': 'note_on', 'note': midi_note, 'velocity': velocity, 'channel': current_harmony_channel})
                harmony_events.append({'tick': end_tick, 'type': 'note_off', 'note': midi_note, 'velocity': 0, 'channel': current_harmony_channel})
                # print(f"DEBUG [create_midi_file]: Prepared harmony event for '{group_name}': {note_name} (note {midi_note}) at tick {start_tick}", file=sys.stderr)
            except Exception as e:
                 print(f"ERROR [create_midi_file]: Failed to process harmony note {i} in group '{group_name}' ({note_info}): {e}", file=sys.stderr)


        # Sort harmony events and add to track
        harmony_events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))
        last_harmony_tick = 0
        for event in harmony_events:
            delta_time = max(0, event['tick'] - last_harmony_tick)
            msg = mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel'])
            harmony_track.append(msg)
            # print(f"DEBUG [create_midi_file]: Added harmony message to '{group_name}': {msg}", file=sys.stderr)
            last_harmony_tick = event['tick']
        print(f"DEBUG [create_midi_file]: Added {len(harmony_track) - 2} messages to Harmony track '{group_name}'.", file=sys.stderr)


    # --- Add End of Track messages ---
    print("DEBUG [create_midi_file]: Adding End of Track messages.", file=sys.stderr)
    # Find the absolute maximum tick across all tracks
    max_tick = 0
    for i, track in enumerate(mid.tracks):
        current_track_tick = sum(msg.time for msg in track)
        print(f"DEBUG [create_midi_file]: Track {i} current end tick (before EOT): {current_track_tick}", file=sys.stderr)
        max_tick = max(max_tick, current_track_tick)
    print(f"DEBUG [create_midi_file]: Overall max tick across tracks: {max_tick}", file=sys.stderr)

    for i, track in enumerate(mid.tracks):
        last_tick_on_track = sum(msg.time for msg in track)
        delta_to_end = max(0, max_tick - last_tick_on_track)
        track.append(mido.MetaMessage('end_of_track', time=delta_to_end))
        print(f"DEBUG [create_midi_file]: Added end_of_track to Track {i} with delta {delta_to_end}", file=sys.stderr)

    # --- Save MIDI File ---
    try:
        print(f"DEBUG [create_midi_file]: Attempting to save MIDI file to '{output_filename}'", file=sys.stderr)
        mid.save(output_filename)
        print(f"MIDI file saved successfully: {output_filename}") # Keep non-debug message for success
    except Exception as e:
        print(f"ERROR [create_midi_file]: Failed to save MIDI file '{output_filename}': {e}", file=sys.stderr)
        # Re-raise the exception so the caller knows saving failed
        raise

