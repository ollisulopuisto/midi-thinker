import pytest
import mido
from midi_generator import note_name_to_midi, seconds_to_ticks

def test_note_name_to_midi_valid():
    assert note_name_to_midi("C4") == 60
    assert note_name_to_midi("A4") == 69
    assert note_name_to_midi("C#4") == 61
    assert note_name_to_midi("Db4") == 61
    assert note_name_to_midi("C-1") == 0
    assert note_name_to_midi("G9") == 127

def test_note_name_to_midi_invalid_format():
    with pytest.raises(ValueError):
        note_name_to_midi("InvalidNote")

def test_note_name_to_midi_invalid_note():
    with pytest.raises(ValueError):
        note_name_to_midi("H4") # H is not valid in English notation

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

