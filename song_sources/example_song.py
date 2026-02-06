"""
SONG DATA TEMPLATE
------------------
Copy this file to song_data.py and customize it for your song.

This file contains the song's 'DNA':
- Metadata (filename, tempo, key)
- Tracks (instruments)
- Patterns (musical phrases)
- Arrangement (song structure)
"""


# --- HELPER FUNCTIONS ---
def note(name, octave):
    """Converts note name (e.g. 'C#', 3) to MIDI number."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    try:
        return names.index(name) + (12 * (octave + 1))
    except ValueError:
        return 0


# Drum map (General MIDI)
KICK = 36
SNARE = 38
CHAT = 42  # Closed hi-hat
OHAT = 46  # Open hi-hat


# --- 1. METADATA ---
FILENAME = "my_song.mid"
TEMPO = 120
KEY = "C Major"
TIME_SIGNATURE = "4/4"
AUTHOR = "Your Name"


# --- 2. TRACKS (Instruments) ---
# If name contains "Gtr" or "Lead", ASCII tabs will be generated.
TRACKS = [
    {"id": 0, "name": "Drums", "patch": 0, "channel": 9, "vol": 100},
    {"id": 1, "name": "Lead Gtr", "patch": 30, "channel": 0, "vol": 100},
    {"id": 2, "name": "Bass", "patch": 33, "channel": 2, "vol": 100},
]


# --- 3. PATTERNS ---
# Format: (pitch, start_beat, duration_beats, velocity)

# Simple 4/4 beat
drum_pattern = [
    (KICK, 0, 1, 100),
    (KICK, 2, 1, 100),
    (SNARE, 1, 1, 110),
    (SNARE, 3, 1, 110),
    (CHAT, 0, 0.5, 70),
    (CHAT, 0.5, 0.5, 50),
    (CHAT, 1, 0.5, 70),
    (CHAT, 1.5, 0.5, 50),
    (CHAT, 2, 0.5, 70),
    (CHAT, 2.5, 0.5, 50),
    (CHAT, 3, 0.5, 70),
    (CHAT, 3.5, 0.5, 50),
]

# Simple melody (C major scale snippet)
melody = [
    (note("C", 4), 0, 1, 100),
    (note("D", 4), 1, 1, 100),
    (note("E", 4), 2, 1, 100),
    (note("G", 4), 3, 2, 100),
]

# Bass line
bass_line = [
    (note("C", 2), 0, 2, 90),
    (note("G", 2), 2, 2, 90),
]


# --- 4. ARRANGEMENT ---
ARRANGEMENT = [
    {
        "name": "Intro",
        "start_bar": 0,
        "length_bars": 4,
        "parts": [
            {"track_id": 0, "loop_pattern": drum_pattern},
        ],
    },
    {
        "name": "Verse",
        "start_bar": 4,
        "length_bars": 8,
        "parts": [
            {"track_id": 0, "loop_pattern": drum_pattern},
            {"track_id": 1, "pattern": melody},
            {"track_id": 2, "loop_pattern": bass_line},
        ],
    },
]
