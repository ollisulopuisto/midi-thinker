"""
MIDI Studio - MIDI Generation and Tab Generator
------------------------------------------------
Generates MIDI files and ASCII guitar tabs from song data.
"""

import song_data
from midiutil import MIDIFile


# --- OSA 1: MIDI ENGINE ---


def generate_midi():
    print(f"\n--- 1. GENERATING MIDI: {song_data.FILENAME} ---")
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
            # Etsi raidan tiedot ID:n perusteella
            t_info = next(t for t in song_data.TRACKS if t["id"] == part["track_id"])

            notes = []

            # Pattern (soita kerran) vs Loop (täytä koko osio)
            if "pattern" in part:
                notes = part["pattern"]
            elif "loop_pattern" in part:
                pat = part["loop_pattern"]
                section_len = section["length_bars"] * 4
                cursor = 0

                # Laske loopin pituus
                loop_len = 4  # Oletus 1 tahti
                if len(pat) > 0:
                    last_note_end = max(pat, key=lambda x: x[1])
                    loop_len = max(4, last_note_end[1] + last_note_end[2])

                while cursor < section_len:
                    for p, t, d, v in pat:
                        if cursor + t < section_len:
                            notes.append((p, t + cursor, d, v))
                    cursor += loop_len

            # Kirjoita MIDI-tiedostoon
            for pitch, start, dur, vel in notes:
                mid.addNote(
                    t_info["id"], t_info["channel"], pitch, bar_offset + start, dur, vel
                )

    with open(song_data.FILENAME, "wb") as f:
        mid.writeFile(f)
    print("   DONE: MIDI file created.")


# --- OSA 2: TAB GENERATOR (DROP D) ---

# Drop D vire: D A D G B e
TUNING_DROPD = {6: 38, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}
STRINGS = {1: "e", 2: "B", 3: "G", 4: "D", 5: "A", 6: "D"}
CHARS_PER_BEAT = 8  # Resoluutio


def get_best_fret(pitch, prev_string=None):
    """Etsii parhaan nauhan ja kielen nuotille (Drop D optimoitu)."""
    candidates = []
    for s_num in range(6, 0, -1):  # Käy kielet läpi 6 -> 1
        base = TUNING_DROPD[s_num]
        fret = pitch - base
        if 0 <= fret <= 22:
            score = 100 if fret == 0 else 0  # Vapaa kieli on paras
            score += 50 if s_num >= 4 else 0  # Paksut kielet riffeille
            score -= 20 if fret > 12 else 0  # Vältä kaulan yläpäätä jos mahd.
            if prev_string and abs(prev_string - s_num) > 1:
                score -= 30  # Vältä suurta kielihyppyä
            candidates.append((score, s_num, fret))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def generate_tabs():
    print("\n--- 2. GENERATING TABS (Drop D) ---")
    print(f"   Song: {song_data.FILENAME} | Tempo: {song_data.TEMPO} bpm")

    # Etsi kaikki raidat joissa lukee "Gtr" tai "Lead"
    gtr_tracks = [
        t for t in song_data.TRACKS if "Gtr" in t["name"] or "Lead" in t["name"]
    ]

    for section in song_data.ARRANGEMENT:
        print(f"\n   [{section['name']}]")
        total_beats = section["length_bars"] * 4

        for t_info in gtr_tracks:
            part = next(
                (p for p in section["parts"] if p["track_id"] == t_info["id"]), None
            )
            if not part:
                continue

            print(f"   Instr: {t_info['name']}")

            # 1. Kerää nuotit (Pattern tai Loop)
            notes_to_show = []
            if "pattern" in part:
                notes_to_show = part["pattern"]
            elif "loop_pattern" in part:
                # Näytä vain max 4 tahtia loopista tilan säästämiseksi
                limit = min(total_beats, 16)
                pat = part["loop_pattern"]
                cursor = 0
                while cursor < limit:
                    for p, t, d, v in pat:
                        if cursor + t < limit:
                            notes_to_show.append((p, t + cursor, d, v))
                    cursor += 4

            # 2. Luo ASCII Grid
            grid = {s: ["-"] * int(total_beats * CHARS_PER_BEAT) for s in range(1, 7)}

            # 3. Sijoita nuotit gridiin
            time_map = {}
            for p, t, d, v in notes_to_show:
                if t not in time_map:
                    time_map[t] = []
                time_map[t].append(p)

            prev_s = None
            for t in sorted(time_map.keys()):
                idx = int(t * CHARS_PER_BEAT)
                chord = sorted(time_map[t])  # Järjestä matalasta korkeaan

                for pitch in chord:
                    res = get_best_fret(pitch, prev_s)
                    if res:
                        s, f = res
                        f_str = str(f)
                        # Kirjoita numero gridiin
                        for char_i, char in enumerate(f_str):
                            if idx + char_i < len(grid[s]):
                                grid[s][idx + char_i] = char
                        prev_s = s

            # 4. Tulosta kielet
            for s in range(1, 7):
                line = "".join(grid[s])
                # Lisää tahtiviivat luettavuuden vuoksi
                formatted = ""
                chunk_size = 4 * CHARS_PER_BEAT
                for i in range(0, len(line), chunk_size):
                    formatted += line[i : i + chunk_size] + "|"
                print(f"   {STRINGS[s]}|{formatted}")
            print("")


if __name__ == "__main__":
    generate_midi()
    generate_tabs()
    print("\n--- STUDIO SESSION COMPLETE ---")
