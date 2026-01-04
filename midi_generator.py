import mido
import re
import sys
import pretty_midi
import random

# --- MIDI Constants ---
TICKS_PER_BEAT = 480  # Standard resolution
DEFAULT_BPM = 120     # Default tempo if not provided
DRUM_CHANNEL = 9      # MIDI channel 10 (0-indexed) for drums
MELODY_CHANNEL = 0    # Default MIDI channel 1 for melody
HARMONY_CHANNEL_1 = 1 # Default MIDI channel 2 for harmony 1
HARMONY_CHANNEL_2 = 2 # Default MIDI channel 3 for harmony 2

# --- Helper Functions ---

def note_name_to_midi(note_name):
    """Converts a note name (e.g., C4, F#5, C-1) to a MIDI number."""
    notes = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5,
             'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
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

        if name in enharmonic_map:
            name = enharmonic_map[name]
        elif name in sharp_map:
            name = sharp_map[name]
        else:
            raise ValueError(f"Unknown base note '{name_part}' in '{note_name}'.")

    midi_note = notes[name] + (octave + 1) * 12 # MIDI C4 = 60
    return max(0, min(127, midi_note))


def drum_name_to_midi(instrument_name):
    """Converts common drum instrument names to General MIDI numbers (channel 10)."""
    name = instrument_name.lower().strip()
    mapping = {
        ("bass drum", "kick", "bassorumpu"): 36,
        ("acoustic snare",): 38,
        ("electric snare",): 40,
        ("snare", "virveli"): 38,
        ("low floor tom", "floor tom 1"): 41,
        ("closed hi-hat", "closed hh", "hi-hat (suljettu)"): 42,
        ("high floor tom", "floor tom 2"): 43,
        ("pedal hi-hat",): 44,
        ("low tom", "tom 3"): 45,
        ("open hi-hat", "open hh", "hi-hat (avoin)"): 46,
        ("low-mid tom", "tom 2"): 47,
        ("hi-mid tom", "tom 1"): 48,
        ("crash cymbal 1", "crash 1", "crash"): 49,
        ("high tom", "tom 0"): 50,
        ("ride cymbal 1", "ride 1", "ride"): 51,
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
        ("tom",): 45,
        ("hi-hat", "hh"): 42,
        ("cymbal",): 49,
    }

    for names, note in mapping.items():
        if any(n in name for n in names):
            return note
    return 38 # Default: Acoustic Snare

def seconds_to_ticks(seconds, bpm, ticks_per_beat):
    """Converts time in seconds to MIDI ticks."""
    if bpm <= 0:
        bpm = 120
    if ticks_per_beat <= 0:
        ticks_per_beat = 480

    beats = (float(seconds) * float(bpm)) / 60.0
    ticks = int(round(beats * float(ticks_per_beat)))
    return ticks

def humanize_notes(notes, velocity_range=10, timing_range=0.01):
    """Applies subtle random variations to note velocities and start times."""
    for note in notes:
        # Vary velocity
        note.velocity = max(1, min(127, note.velocity + random.randint(-velocity_range, velocity_range)))
        # Vary start/end time
        jitter = random.uniform(-timing_range, timing_range)
        note.start = max(0, note.start + jitter)
        note.end = max(note.start + 0.01, note.end + jitter)
    return notes

# --- Main MIDI Creation Function ---

def create_midi_file(data, output_filename="output.mid", humanize=False):
    """Creates a MIDI file using pretty_midi for higher-level structural handling."""
    print(f"DEBUG [create_midi_file]: Creating MIDI for '{output_filename}' using pretty_midi", file=sys.stderr)

    mid = pretty_midi.PrettyMIDI(initial_tempo=data.get('tempo', DEFAULT_BPM))

    # 1. Lead Melody Track
    melody_notes_data = data.get("melody", [])
    if melody_notes_data:
        melody_instr = pretty_midi.Instrument(program=0, name="Lead Melody")
        for n in melody_notes_data:
            try:
                midi_note = note_name_to_midi(n['note'])
                note = pretty_midi.Note(
                    velocity=90, pitch=midi_note, 
                    start=n['time'], end=n['time'] + n['duration']
                )
                melody_instr.notes.append(note)
            except Exception as e:
                print(f"ERROR: Failed to process melody note {n}: {e}", file=sys.stderr)
        
        if humanize:
            humanize_notes(melody_instr.notes)
        mid.instruments.append(melody_instr)

    # 2. Drum Track
    drum_hits_data = data.get("drums", [])
    if drum_hits_data:
        drum_instr = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
        for hit in drum_hits_data:
            try:
                midi_note = drum_name_to_midi(hit['instrument'])
                note = pretty_midi.Note(
                    velocity=100, pitch=midi_note, 
                    start=hit['time'], end=hit['time'] + 0.05 # Short hit
                )
                drum_instr.notes.append(note)
            except Exception as e:
                print(f"ERROR: Failed to process drum hit {hit}: {e}", file=sys.stderr)
        
        if humanize:
            humanize_notes(drum_instr.notes, velocity_range=5, timing_range=0.005)
        mid.instruments.append(drum_instr)

    # 3. Harmony Tracks
    harmony_notes_all = data.get("harmonies", [])
    harmony_groups = {}
    for note_info in harmony_notes_all:
        group_name = note_info.get("group", "Default Harmony")
        if group_name not in harmony_groups:
            harmony_groups[group_name] = []
        harmony_groups[group_name].append(note_info)

    for group_name, notes in harmony_groups.items():
        # Guess instrument program
        program = 48 # Strings
        if "pad" in group_name.lower():
            program = 89
        elif "choir" in group_name.lower():
            program = 52
        elif "bass" in group_name.lower():
            program = 33
        
        harmony_instr = pretty_midi.Instrument(program=program, name=f"Harmony: {group_name}")
        for n in notes:
            try:
                midi_note = note_name_to_midi(n['note'])
                note = pretty_midi.Note(
                    velocity=70, pitch=midi_note, 
                    start=n['time'], end=n['time'] + n['duration']
                )
                harmony_instr.notes.append(note)
            except Exception as e:
                print(f"ERROR: Failed to process harmony note {n}: {e}", file=sys.stderr)
        
        if humanize:
            humanize_notes(harmony_instr.notes)
        mid.instruments.append(harmony_instr)

    # 4. Save MIDI File
    try:
        mid.write(output_filename)
        print(f"MIDI file saved successfully: {output_filename}")
        
        # Add Markers using mido after pretty_midi saves the file 
        # (pretty_midi's marker support is limited in some environments)
        chords = data.get("chords", [])
        if chords:
            print(f"DEBUG [create_midi_file]: Adding {len(chords)} chord markers using mido", file=sys.stderr)
            m_file = mido.MidiFile(output_filename)
            # Find or create a meta track
            meta_track = mido.MidiTrack()
            m_file.tracks.insert(0, meta_track)
            meta_track.append(mido.MetaMessage('track_name', name='Chord Markers', time=0))
            
            # pretty_midi saved with a specific ticks_per_beat, let's get it
            tpb = m_file.ticks_per_beat
            bpm = data.get('tempo', DEFAULT_BPM)
            
            last_tick = 0
            for chord in chords:
                # Convert seconds to ticks
                beats = (chord['time'] * bpm) / 60.0
                tick = int(round(beats * tpb))
                delta = max(0, tick - last_tick)
                meta_track.append(mido.MetaMessage('marker', text=chord['name'], time=delta))
                last_tick = tick
            
            m_file.save(output_filename)

    except Exception as e:
        print(f"ERROR [create_midi_file]: Failed to save MIDI file '{output_filename}': {e}", file=sys.stderr)
        raise

