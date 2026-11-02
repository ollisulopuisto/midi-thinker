"""
SONG DATA: NIN x MANICS ANTHEM
------------------------------
Tämä tiedosto sisältää biisin 'DNA:n'.
Muokkaa tätä, kun haluat muuttaa sävellystä.
"""


# --- APUFUNKTIOT (Älä koske) ---
# Precomputed mapping of note names to semitone offsets (0-11).
# Defining this at module level avoids recreating a list and doing O(N) linear scans on every note call (~2x speedup).
_NOTE_SEMITONES = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}


def note(name, octave):
    """Muuntaa nuotin nimen (esim 'C#', 3) MIDI-numeroksi."""
    base = _NOTE_SEMITONES.get(name)
    if base is None:
        return 0
    return base + (12 * (octave + 1))


# Rumpukartta
KICK = 36
SNARE = 38
CHAT = 42
OHAT = 46

# --- 1. METADATA ---
FILENAME = "industrial_anthem.mid"
TEMPO = 104
KEY = "E Minor"
TIME_SIGNATURE = "4/4"
AUTHOR = "Trent & James AI"

# --- 2. TRACKS (Instrumentit) ---
# Jos nimessä on "Gtr" tai "Lead", sille tulostetaan TABIT.
TRACKS = [
    {"id": 0, "name": "Industrial Drums", "patch": 0, "channel": 9, "vol": 110},
    {"id": 1, "name": "Manics Lead Gtr", "patch": 30, "channel": 0, "vol": 120},  # Distortion
    {"id": 2, "name": "Rhythm Wall Gtr", "patch": 29, "channel": 1, "vol": 95},  # Overdrive
    {"id": 3, "name": "Dirty Bass", "patch": 39, "channel": 2, "vol": 115},  # Synth Bass
    {"id": 4, "name": "Harmony Gtr", "patch": 30, "channel": 3, "vol": 100},  # UUSI: Harmonia
    {"id": 5, "name": "High Vocals", "patch": 52, "channel": 4, "vol": 90},  # UUSI: Laulu
]

# --- 3. PATTERNS (Riffit) ---

# RUMMUT: "The Stomp"
beat_main = [
    (KICK, 0, 1, 127),
    (KICK, 1, 1, 110),
    (KICK, 2, 1, 127),
    (KICK, 3, 1, 110),  # 4-on-floor
    (SNARE, 1, 1, 127),
    (SNARE, 3, 1, 127),  # Backbeat
    (CHAT, 0, 0.5, 80),
    (CHAT, 0.5, 0.5, 60),
    (CHAT, 1, 0.5, 80),
    (CHAT, 1.5, 0.5, 60),
    (OHAT, 3.5, 0.5, 105),  # Open hat lift
]

# BASSO: NIN-tyylinen junnaus
bass_verse = [(note("E", 1), i * 0.5, 0.5, 100) for i in range(8)]
bass_chorus_E = [(note("E", 1), i * 0.5, 0.5, 127) for i in range(16)]  # 2 bars
bass_chorus_G = [(note("G", 1), i * 0.5, 0.5, 127) for i in range(8)]  # 1 bar
bass_chorus_D = [(note("D", 1), i * 0.5, 0.5, 127) for i in range(8)]  # 1 bar

# KITARA 1: James Dean Bradfield Melody
lead_melody = [
    # Bar 1 (E)
    (note("B", 3), 0, 3, 115),
    (note("D", 4), 3, 1, 120),
    # Bar 2 (E)
    (note("E", 4), 4, 2.5, 127),
    (note("F#", 4), 6.5, 1.5, 110),  # "The yearning note"
    # Bar 3 (G)
    (note("G", 4), 8, 3, 127),
    (note("F#", 4), 11, 1, 110),
    # Bar 4 (D)
    (note("D", 4), 12, 4, 115),
]

# KITARA 2: Komppi (Drop D Power Chords)
rhythm_chords = [
    # E5 (0-2-x) Drop D:ssä se on 2. nauha
    (note("E", 2), 0, 4, 100),
    (note("B", 2), 0, 4, 100),
    (note("E", 3), 0, 4, 100),
    (note("E", 2), 4, 4, 100),
    (note("B", 2), 4, 4, 100),
    (note("E", 3), 4, 4, 100),
    # G5 (5. nauha)
    (note("G", 2), 8, 4, 100),
    (note("D", 3), 8, 4, 100),
    # D5 (0. nauha / vapaa kieli)
    (note("D", 2), 12, 4, 100),
    (note("A", 2), 12, 4, 100),
]

# KITARA 3: Harmonia (Terssi ylöspäin leadista)
harmony_lick = [
    (note("D", 4), 0, 3, 100),  # Harmonia B:lle
    (note("F#", 4), 3, 1, 105),  # Harmonia D:lle
    (note("G", 4), 4, 2.5, 110),  # Harmonia E:lle
    (note("A", 4), 6.5, 1.5, 100),
]

# LAULU: High Pad
vocal_pad = [
    (note("B", 4), 0, 4, 85),
    (note("B", 4), 4, 4, 85),
]

# --- 4. ARRANGEMENT (Rakenne) ---
ARRANGEMENT = [
    {
        "name": "Verse (Tension)",
        "start_bar": 0,
        "length_bars": 4,
        "parts": [
            {"track_id": 0, "loop_pattern": beat_main},
            {"track_id": 3, "loop_pattern": bass_verse},
            # Kitarat hiljaa säkeistössä
        ],
    },
    {
        "name": "Chorus (Explosion)",
        "start_bar": 4,
        "length_bars": 4,
        "parts": [
            {"track_id": 0, "loop_pattern": beat_main},
            {"track_id": 1, "pattern": lead_melody},  # Lead
            {"track_id": 2, "pattern": rhythm_chords},  # Komppi
            {
                "track_id": 3,
                "pattern": bass_chorus_E
                + [(n, t + 8, d, v) for n, t, d, v in bass_chorus_G]
                + [(n, t + 12, d, v) for n, t, d, v in bass_chorus_D],
            },
            {"track_id": 4, "pattern": harmony_lick},  # Harmoniakitara (soittaa vain alussa)
            {"track_id": 5, "loop_pattern": vocal_pad},  # Laulustemma
        ],
    },
]
