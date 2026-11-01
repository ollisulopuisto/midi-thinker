"""
MIDI Studio - MIDI Generation and Tab Generator
------------------------------------------------
Generates MIDI files and ASCII guitar tabs from song data.
Output files are saved to the 'songs/' subdirectory.
"""

import os

from midiutil import MIDIFile

import song_data

# Output directory for generated files
OUTPUT_DIR = "songs"


def ensure_output_dir():
    """Creates the output directory if it doesn't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_output_path(filename):
    """Returns the full path for an output file."""
    ensure_output_dir()
    return os.path.join(OUTPUT_DIR, filename)


# --- PART 1: MIDI ENGINE ---


def generate_midi():
    """Generates MIDI file from song_data and saves to songs/ directory."""
    output_path = get_output_path(song_data.FILENAME)
    print(f"\n--- 1. GENERATING MIDI: {output_path} ---")
    mid = MIDIFile(len(song_data.TRACKS))

    # 1. Setup Tracks
    for t in song_data.TRACKS:
        mid.addTrackName(t["id"], 0, t["name"])
        mid.addTempo(t["id"], 0, song_data.TEMPO)
        mid.addProgramChange(t["id"], t["channel"], 0, t["patch"])

    # 2. Process Arrangement
    for section in song_data.ARRANGEMENT:
        bar_offset = section["start_bar"] * 4
        print(f"   Processing Section: {section['name']}")
        mid.addText(0, bar_offset, section["name"])

        for part in section["parts"]:
            # Find track info by ID
            t_info = next(t for t in song_data.TRACKS if t["id"] == part["track_id"])

            notes = []

            # Pattern (play once) vs Loop (fill entire section)
            if "pattern" in part:
                notes = part["pattern"]
            elif "loop_pattern" in part:
                pat = part["loop_pattern"]
                section_len = section["length_bars"] * 4
                cursor = 0

                # Calculate loop length
                loop_len = 4  # Default 1 bar
                if len(pat) > 0:
                    last_note_end = max(pat, key=lambda x: x[1])
                    loop_len = max(4, last_note_end[1] + last_note_end[2])

                while cursor < section_len:
                    for p, t, d, v in pat:
                        if cursor + t < section_len:
                            notes.append((p, t + cursor, d, v))
                    cursor += loop_len

            # Write to MIDI file
            for pitch, start, dur, vel in notes:
                mid.addNote(
                    t_info["id"], t_info["channel"], pitch, bar_offset + start, dur, vel
                )

    with open(output_path, "wb") as f:
        mid.writeFile(f)
    print(f"   DONE: MIDI file created at {output_path}")
    return output_path


# --- PART 2: TAB GENERATOR (DROP D) ---

# Drop D tuning: D A D G B e
TUNING_DROPD = {6: 38, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}
STRINGS = {1: "e", 2: "B", 3: "G", 4: "D", 5: "A", 6: "D"}
CHARS_PER_BEAT = 8  # Resolution


def get_best_fret(pitch, prev_string=None):
    """Finds the best fret and string for a note (Drop D optimized)."""
    candidates = []
    for s_num in range(6, 0, -1):  # Check strings 6 -> 1
        base = TUNING_DROPD[s_num]
        fret = pitch - base
        if 0 <= fret <= 22:
            score = 100 if fret == 0 else 0  # Open string is best
            score += 50 if s_num >= 4 else 0  # Prefer thicker strings for riffs
            score -= 20 if fret > 12 else 0  # Avoid high frets if possible
            if prev_string and abs(prev_string - s_num) > 1:
                score -= 30  # Avoid large string jumps
            candidates.append((score, s_num, fret))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def generate_tabs():
    """Generates ASCII guitar tabs and saves to a .txt file."""
    # Generate tab filename from MIDI filename
    base_name = os.path.splitext(song_data.FILENAME)[0]
    tab_filename = f"{base_name}_tabs.txt"
    output_path = get_output_path(tab_filename)

    lines = []
    lines.append("=" * 60)
    lines.append("GUITAR TABS (Drop D Tuning)")
    lines.append(f"Song: {song_data.FILENAME} | Tempo: {song_data.TEMPO} bpm")
    lines.append("=" * 60)

    print("\n--- 2. GENERATING TABS (Drop D) ---")
    print(f"   Song: {song_data.FILENAME} | Tempo: {song_data.TEMPO} bpm")

    # Find all tracks containing "Gtr" or "Lead"
    gtr_tracks = [
        t for t in song_data.TRACKS if "Gtr" in t["name"] or "Lead" in t["name"]
    ]

    for section in song_data.ARRANGEMENT:
        lines.append(f"\n[{section['name']}]")
        print(f"\n   [{section['name']}]")
        total_beats = section["length_bars"] * 4

        for t_info in gtr_tracks:
            part = next(
                (p for p in section["parts"] if p["track_id"] == t_info["id"]), None
            )
            if not part:
                continue

            lines.append(f"Instrument: {t_info['name']}")
            print(f"   Instr: {t_info['name']}")

            # 1. Collect notes (Pattern or Loop)
            notes_to_show = []
            if "pattern" in part:
                notes_to_show = part["pattern"]
            elif "loop_pattern" in part:
                # Show only max 4 bars of loop to save space
                limit = min(total_beats, 16)
                pat = part["loop_pattern"]
                cursor = 0
                while cursor < limit:
                    for p, t, d, v in pat:
                        if cursor + t < limit:
                            notes_to_show.append((p, t + cursor, d, v))
                    cursor += 4

            # 2. Create ASCII Grid
            grid = {s: ["-"] * int(total_beats * CHARS_PER_BEAT) for s in range(1, 7)}

            # 3. Place notes in grid
            time_map = {}
            for p, t, d, v in notes_to_show:
                if t not in time_map:
                    time_map[t] = []
                time_map[t].append(p)

            prev_s = None
            for t in sorted(time_map.keys()):
                idx = int(t * CHARS_PER_BEAT)
                chord = sorted(time_map[t])  # Sort low to high

                for pitch in chord:
                    res = get_best_fret(pitch, prev_s)
                    if res:
                        s, f = res
                        f_str = str(f)
                        # Write number to grid
                        for char_i, char in enumerate(f_str):
                            if idx + char_i < len(grid[s]):
                                grid[s][idx + char_i] = char
                        prev_s = s

            # 4. Format and output strings
            for s in range(1, 7):
                line = "".join(grid[s])
                # Add bar lines for readability
                formatted = ""
                chunk_size = 4 * CHARS_PER_BEAT
                for i in range(0, len(line), chunk_size):
                    formatted += line[i : i + chunk_size] + "|"
                tab_line = f"{STRINGS[s]}|{formatted}"
                lines.append(tab_line)
                print(f"   {tab_line}")
            lines.append("")
            print()

    # Write tabs to file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"   DONE: Tabs saved to {output_path}")
    return output_path


if __name__ == "__main__":
    midi_path = generate_midi()
    tabs_path = generate_tabs()
    print("\n--- STUDIO SESSION COMPLETE ---")
    print(f"   MIDI: {midi_path}")
    print(f"   Tabs: {tabs_path}")
