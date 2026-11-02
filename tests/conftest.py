"""Pytest configuration - adds project root to sys.path for imports."""
import sys
from pathlib import Path

# Add project root to Python path so tests can import modules
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


import mido
import pytest


@pytest.fixture
def type0_midi_path(tmp_path):
    """Generate the formerly untracked fixture without an external binary file."""
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend([
        mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120)),
        mido.MetaMessage('key_signature', key='C'),
        mido.MetaMessage('time_signature', numerator=4, denominator=4),
        mido.Message('program_change', program=1),
    ])
    for pitch, duration in [(60, 480), (64, 480), (67, 960)]:
        track.append(mido.Message('note_on', note=pitch, velocity=64, time=0))
        track.append(mido.Message('note_off', note=pitch, velocity=0, time=duration))
    path = tmp_path / 'test_midi_type0.mid'
    midi.save(path)
    return path
