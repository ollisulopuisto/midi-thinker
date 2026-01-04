import os
import sys
import importlib.util
import mido

# Helper to import module with a hyphen in its name
def import_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Path to music-analyzer.py
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
analyzer_path = os.path.join(project_root, 'music-analyzer.py')
music_analyzer = import_module_from_path('music_analyzer', analyzer_path)
imagine_music = import_module_from_path('imagine_music', os.path.join(project_root, 'imagine-music.py'))


# --- Tests for music-analyzer.py ---

def test_parse_gemini_response_valid_json():
    """Tests parsing of a valid JSON string from Gemini."""
    valid_json_string = """
    ```json
    {
      "tempo": 125.5,
      "key": "A Minor",
      "chords": [{"time": 0.5, "name": "Am"}],
      "drums": [{"time": 0.0, "instrument": "Kick"}],
      "melody": [{"time": 1.0, "note": "A4", "duration": 0.5}],
      "harmonies": []
    }
    ```
    """
    parsed_data = music_analyzer.parse_gemini_response(valid_json_string)
    assert parsed_data is not None
    assert parsed_data["tempo"] == 125.5
    assert parsed_data["key"] == "A Minor"
    assert len(parsed_data["drums"]) == 1
    assert parsed_data["melody"][0]["note"] == "A4"

def test_parse_gemini_response_invalid_json():
    """Tests handling of an invalid JSON string."""
    invalid_json_string = "This is not JSON."
    parsed_data = music_analyzer.parse_gemini_response(invalid_json_string)
    assert parsed_data is None

def test_parse_gemini_response_empty_string():
    """Tests handling of an empty string."""
    parsed_data = music_analyzer.parse_gemini_response("")
    assert parsed_data is None

def test_parse_gemini_extension_with_meta():
    """Tests parsing of a hypothetical extension response that includes meta changes."""
    # This simulates what we WANT Gemini to be able to return
    extension_json = """
    ```json
    {
      "0": [
        { "pitch": 60, "start_tick": 0, "duration_tick": 480, "velocity": 90 }
      ],
      "meta_changes": [
        { "type": "tempo", "bpm": 140, "tick": 0 },
        { "type": "key_signature", "key": "G", "tick": 0 },
        { "type": "time_signature", "numerator": 3, "denominator": 4, "tick": 0 }
      ]
    }
    ```
    """
    parsed_data = imagine_music.parse_gemini_response(extension_json)
    assert parsed_data is not None
    assert "0" in parsed_data
    assert "meta_changes" in parsed_data
    assert parsed_data["meta_changes"][0]["bpm"] == 140
    assert parsed_data["meta_changes"][2]["numerator"] == 3

def test_parse_gemini_multi_track_complement():
    """Tests parsing of a complement response that suggests multiple new tracks."""
    complement_json = """
    ```json
    {
      "tracks": [
        {
          "name": "Bassline",
          "instrument_program": 32,
          "notes": [{ "pitch": 36, "start_tick": 0, "duration_tick": 480, "velocity": 80 }]
        },
        {
          "name": "Drums",
          "instrument_program": 0,
          "is_drum": true,
          "notes": [{ "pitch": 36, "start_tick": 0, "duration_tick": 60, "velocity": 100 }]
        }
      ]
    }
    ```
    """
    parsed_data = imagine_music.parse_gemini_response(complement_json)
    assert parsed_data is not None
    assert "tracks" in parsed_data
    assert len(parsed_data["tracks"]) == 2
    assert parsed_data["tracks"][1]["is_drum"] is True

def test_parse_gemini_analysis_with_sections():
    """Tests parsing of an analysis response that includes song sections."""
    analysis_json = """
    ```json
    {
      "key_signature": "Cmaj",
      "tempo_bpm": 120,
      "time_signature": "4/4",
      "style_genre": "Pop",
      "harmony_description": "I-V-vi-IV",
      "sections": [
        { "name": "Intro", "start_tick": 0, "end_tick": 1920 },
        { "name": "Verse", "start_tick": 1920, "end_tick": 3840 }
      ]
    }
    ```
    """
    parsed_data = imagine_music.parse_gemini_response(analysis_json)
    assert parsed_data is not None
    assert "sections" in parsed_data
    assert len(parsed_data["sections"]) == 2
    assert parsed_data["sections"][1]["name"] == "Verse"

def test_midi_cloning_for_refinement():
    """Verifies that we can clone a MidiFile to allow non-destructive refinement."""
    test_midi_path = "tests/fixtures/test_midi_type0.mid"
    original_mid = mido.MidiFile(test_midi_path)
    original_note_count = len([m for m in original_mid.tracks[0] if m.type == 'note_on'])

    # "Clone" by saving to buffer or just re-opening
    # In mido, there isn't a deepcopy, so we'll test the logic of starting from original each time
    clone_mid = mido.MidiFile(test_midi_path)
    
    # Modify clone
    clone_mid.tracks[0].append(mido.Message('note_on', note=70, velocity=64, time=0))
    
    assert len(clone_mid.tracks[0]) > len(original_mid.tracks[0])
    assert len([m for m in clone_mid.tracks[0] if m.type == 'note_on']) == original_note_count + 1

# --- Tests for imagine-music.py ---

def test_parse_midi_to_mvp_json_type0():
    """Tests parsing of a simple Type 0 MIDI file."""
    test_midi_path = "tests/fixtures/test_midi_type0.mid"
    mid = mido.MidiFile(test_midi_path)
    
    json_data, track_end_ticks = imagine_music.parse_midi_to_mvp_json(mid)

    assert json_data is not None
    assert track_end_ticks is not None

    # Check meta messages
    assert json_data['tempo'] == mido.bpm2tempo(120)
    assert json_data['key_signature'] == 'C'
    assert json_data['time_signature']['numerator'] == 4
    assert json_data['ticks_per_beat'] == mid.ticks_per_beat
    
    # Check meta_changes
    assert 'meta_changes' in json_data
    assert len(json_data['meta_changes']) >= 3
    # Check for tempo change
    tempo_changes = [c for c in json_data['meta_changes'] if c['type'] == 'tempo']
    assert len(tempo_changes) > 0
    assert tempo_changes[0]['bpm'] == 120

    # Check track structure
    assert len(json_data['tracks']) == 1
    track_data = json_data['tracks'][0]

    # Check instrument and notes
    assert track_data['instrument_program'] == 1
    notes = track_data['notes']
    assert len(notes) == 3

    # Check first note
    assert notes[0]['pitch'] == 60 # C4
    assert notes[0]['start_tick'] == 0
    assert notes[0]['duration_tick'] == 480
    assert notes[0]['velocity'] == 64

    # Check third note
    assert notes[2]['pitch'] == 67 # G4
    assert notes[2]['start_tick'] == 960
    assert notes[2]['duration_tick'] == 960
    
    # Check end tick calculation
    assert len(track_end_ticks) == 1
    assert track_end_ticks[0] == 1920