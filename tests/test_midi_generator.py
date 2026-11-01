import mido
import pytest

from midi_generator import drum_name_to_midi, note_name_to_midi, seconds_to_ticks


def test_note_name_to_midi_valid():
    assert note_name_to_midi("C4") == 60
    assert note_name_to_midi("A4") == 69
    assert note_name_to_midi("C#4") == 61
    assert note_name_to_midi("Db4") == 61
    assert note_name_to_midi("c4") == 60
    assert note_name_to_midi("bb3") == 58
    assert note_name_to_midi("C-1") == 0
    assert note_name_to_midi("G9") == 127
    # Note boundary clipping
    assert note_name_to_midi("C-2") == 0
    assert note_name_to_midi("G10") == 127

def test_note_name_to_midi_invalid_format():
    with pytest.raises(ValueError):
        note_name_to_midi("InvalidNote")

def test_note_name_to_midi_invalid_note():
    with pytest.raises(ValueError):
        note_name_to_midi("H4") # H is not valid in English notation

def test_note_name_to_midi_lru_cache():
    """Verifies that note_name_to_midi utilizes its lru_cache."""
    note_name_to_midi.cache_clear()
    info_before = note_name_to_midi.cache_info()
    assert info_before.hits == 0

    # First call - cache miss
    res1 = note_name_to_midi("D4")
    # Second call - cache hit
    res2 = note_name_to_midi("D4")
    assert res1 == res2 == 62

    info_after = note_name_to_midi.cache_info()
    assert info_after.hits >= 1

def test_drum_name_to_midi_exact_and_alias():
    """Tests exact matches, Finnish/alternative aliases, case and whitespace handling."""
    assert drum_name_to_midi("kick") == 36
    assert drum_name_to_midi("bass drum") == 36
    assert drum_name_to_midi("bassorumpu") == 36
    assert drum_name_to_midi("  KICK  ") == 36
    assert drum_name_to_midi("snare") == 38
    assert drum_name_to_midi("virveli") == 38
    assert drum_name_to_midi("closed hi-hat") == 42
    assert drum_name_to_midi("closed hh") == 42
    assert drum_name_to_midi("hi-hat (suljettu)") == 42
    assert drum_name_to_midi("crash cymbal 1") == 49
    assert drum_name_to_midi("cowbell") == 56

def test_drum_name_to_midi_substring():
    """Tests fallback substring matching when exact alias isn't matched."""
    # Substring matching for phrases containing the instrument name
    assert drum_name_to_midi("acoustic snare drum") == 38
    assert drum_name_to_midi("electric snare sound") == 40
    assert drum_name_to_midi("loud kick beat") == 36

def test_drum_name_to_midi_fallback():
    """Tests unknown instrument names falling back to default snare (38)."""
    assert drum_name_to_midi("unknown_percussion") == 38
    assert drum_name_to_midi("synthesizer") == 38

def test_seconds_to_ticks():
    # 120 BPM = 2 beats per second. 480 ticks per beat.
    # 1 second = 2 beats = 960 ticks.
    assert seconds_to_ticks(1.0, 120, 480) == 960
    assert seconds_to_ticks(0.5, 120, 480) == 480

def test_create_midi_file(tmp_path):
    """Tests the full MIDI creation process from a sample data dict."""
    from midi_generator import create_midi_file
    
    data = {
        "tempo": 120,
        "key": "C Major",
        "chords": [{"time": 0.0, "name": "C"}],
        "drums": [{"time": 0.0, "instrument": "kick"}],
        "melody": [{"time": 0.0, "note": "C4", "duration": 1.0}],
        "harmonies": [{"group": "Pad", "note": "E3", "time": 0.0, "duration": 4.0}]
    }
    
    output_file = tmp_path / "test_output.mid"
    create_midi_file(data, output_filename=str(output_file), humanize=True)
    
    assert output_file.exists()
    # Basic check of file content
    mid = mido.MidiFile(str(output_file))
    assert len(mid.tracks) > 0

