import logging
import os
import platform
import subprocess

from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.shortcuts import (
    button_dialog,
    checkboxlist_dialog,
    input_dialog,
    message_dialog,
    radiolist_dialog,
)
from prompt_toolkit.validation import ValidationError, Validator

logger = logging.getLogger(__name__)

class NumberValidator(Validator):
    """Validates that input is a positive integer."""
    def validate(self, document):
        text = document.text
        if text and text.isdigit() and int(text) > 0:
            pass
        else:
            raise ValidationError(
                message='Please enter a positive number',
                cursor_position=len(text))

class NotEmptyValidator(Validator):
    """Validates that input is not empty."""
    def validate(self, document):
        text = document.text.strip()
        if not text:
            raise ValidationError(
                message='This field cannot be empty',
                cursor_position=len(text))

def select_input_file():
    """
    Prompts the user to select the input MIDI file using a dialog.

    Returns:
        str: The selected input file path, or None if cancelled.
    """
    path_completer = PathCompleter()
    input_path = input_dialog(
        title='Input MIDI File',
        text='Enter the path to the input MIDI file:',
        completer=path_completer,
        validator=NotEmptyValidator()
    ).run()
    return input_path


def get_user_input(input_path: str, num_tracks: int, midi_type: int = 1):
    """
    Guides the user through prompts for output path, mode, and parameters,
    using the provided input_path, number of tracks, and MIDI type.

    Args:
        input_path (str): The path to the input MIDI file.
        num_tracks (int): The number of tracks in the input MIDI file.
        midi_type (int): The MIDI file type (0 or 1). Defaults to 1.

    Returns:
        dict: A dictionary containing the user's selections (excluding input_path),
              e.g., {'output_path': '...', 'mode': '...', 'target_track_indices': [0], ...}
              Returns None if the user cancels any step.
    """
    settings = {}
    path_completer = PathCompleter()

    # 1. Get Output Path (Input path is already known)
    default_output = os.path.join(
        os.path.dirname(input_path),
        f"{os.path.splitext(os.path.basename(input_path))[0]}_modified.mid"
    )
    settings['output_path'] = input_dialog(
        title='Output MIDI File',
        text='Enter the path for the output MIDI file:',
        default=default_output,
        completer=path_completer,
        validator=NotEmptyValidator()
    ).run()
    if settings['output_path'] is None:
        return None # User cancelled

    # 2. Get Mode
    mode = radiolist_dialog(
        title='Select Mode',
        text='Choose the operation mode:',
        values=[
            ('extend', 'Extend Track'),
            ('complement', 'Add Complementary Track')
        ]
    ).run()
    if mode is None:
        return None # User cancelled
    settings['mode'] = mode

    # 3. Get Mode-Specific Parameters
    if mode == 'extend':
        # 3a. Select Tracks to Extend (if multiple tracks exist)
        target_track_indices = [0]
        if num_tracks > 1:
            track_values = [(str(i), f"Track {i}") for i in range(num_tracks)]
            selected_tracks = checkboxlist_dialog(
                title='Select Tracks to Extend',
                text=f'Which tracks do you want to extend? (0-{num_tracks-1})',
                values=track_values,
                default_values=['0'] if num_tracks > 0 else []
            ).run()
            if selected_tracks is None:
                return None # User cancelled
            if not selected_tracks:
                # Fallback to Track 0 if none selected
                target_track_indices = [0]
            else:
                target_track_indices = [int(i) for i in selected_tracks]
        else:
            print("Only one track found. Extending Track 0.")
            # target_track_indices remains [0]

        settings['target_track_indices'] = target_track_indices

        # 3b. Get Bars to Extend
        bars = input_dialog(
            title='Extend Settings',
            text='Enter the number of bars to extend the selected tracks:',
            default='4',
            validator=NumberValidator()
        ).run()
        if bars is None:
            return None # User cancelled
        settings['bars_to_extend'] = int(bars)

    elif mode == 'complement':
        comp_type = input_dialog(
            title='Complement Settings',
            text='Enter the type of complement (e.g., bassline, harmony, counter-melody):',
            default='bassline',
            validator=NotEmptyValidator()
        ).run()
        if comp_type is None:
            return None # User cancelled
        settings['complement_type'] = comp_type

        # 3c. Select Instrument for Complement
        instrument_values = [
            ('0', 'Acoustic Grand Piano'),
            ('32', 'Acoustic Bass'),
            ('33', 'Electric Bass (finger)'),
            ('48', 'String Ensemble 1'),
            ('52', 'Choir Aahs'),
            ('61', 'Brass Section'),
            ('73', 'Flute'),
            ('80', 'Lead 1 (square)'),
            ('81', 'Lead 2 (sawtooth)'),
            ('89', 'Pad 2 (warm)'),
        ]
        selected_instr_str = radiolist_dialog(
            title='Select Instrument',
            text='Choose an instrument for the new track:',
            values=instrument_values,
            default='32' if 'bass' in comp_type.lower() else '0'
        ).run()
        if selected_instr_str is None:
            return None # User cancelled
        settings['instrument_program'] = int(selected_instr_str)
    
    # 4. Get Optional Style/Variation
    style_variation = input_dialog(
        title='Style/Variation (Optional)',
        text='Describe any variation in style, rhythm, or dynamics (e.g., "more energetic", "quieter and sparser"):'
    ).run()
    # It's ok if this is None (user pressed cancel) or empty, we'll just ignore it.
    settings['style_variation'] = style_variation if style_variation else ""

    # 5. Humanize Option
    humanize = button_dialog(
        title='Humanize Output',
        text='Do you want to apply subtle randomization to velocities and timing (Humanize)?',
        buttons=[
            ('Yes', True),
            ('No', False)
        ]
    ).run()
    settings['humanize'] = humanize if humanize is not None else False

    return settings

def open_file_folder(file_path):
    """Opens the folder containing the file in the OS file explorer."""
    folder = os.path.dirname(os.path.abspath(file_path))
    if platform.system() == "Windows":
        os.startfile(folder)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", folder])
    else:
        try:
            subprocess.Popen(["xdg-open", folder])
        except Exception:
            logger.exception("open_file_folder failed")
            # Fallback if xdg-open not available

def show_success_with_action(title, text, file_path):
    """Displays a success message and offers to open the containing folder."""
    result = button_dialog(
        title=title,
        text=text,
        buttons=[
            ('Open Folder', True),
            ('Close', False)
        ]
    ).run()
    if result:
        open_file_folder(file_path)

def ask_refine_or_save():
    """Prompts the user to either accept the generation or refine it."""
    return button_dialog(
        title='Refinement',
        text='How do you like this version? You can save it or ask Gemini to refine it with feedback.',
        buttons=[
            ('Accept & Save', 'save'),
            ('Refine with Feedback', 'refine'),
            ('Cancel', 'cancel')
        ]
    ).run()

def get_refinement_feedback():
    """Prompts the user for feedback on how to refine the generation."""
    return input_dialog(
        title='Refine Generation',
        text='What would you like to change? (e.g., "more bass", "too many notes", "syncopate the rhythm"):'
    ).run()

def show_error(title, text):
    """Displays an error message dialog."""
    # Remove the style argument to avoid the AttributeError
    message_dialog(title=title, text=text).run()

def show_success(title, text):
    """Displays a success message dialog."""
    message_dialog(title=title, text=text).run()


def show_main_menu():
    """
    Displays the main menu for selecting the operation mode.
    
    Returns:
        str: 'modify' to modify existing MIDI, 'generate' to generate new song,
             or None if cancelled.
    """
    return radiolist_dialog(
        title='MIDI Thinker',
        text='What would you like to do?',
        values=[
            ('modify', 'Modify Existing MIDI - Extend or add tracks to an existing file'),
            ('generate', 'Generate New Song - Create a new MIDI from song data'),
        ]
    ).run()


def get_song_generation_config():
    """
    Prompts the user to configure song generation parameters.
    
    Returns:
        dict: Configuration with filename, tempo, etc. or None if cancelled.
    """
    config = {}
    
    # 1. Output filename
    config['filename'] = input_dialog(
        title='Output Filename',
        text='Enter the output MIDI filename:',
        default='my_song.mid',
        validator=NotEmptyValidator()
    ).run()
    if config['filename'] is None:
        return None
    
    # Ensure .mid extension
    if not config['filename'].endswith('.mid'):
        config['filename'] += '.mid'
    
    # 2. Tempo
    tempo = input_dialog(
        title='Tempo',
        text='Enter the tempo in BPM:',
        default='120',
        validator=NumberValidator()
    ).run()
    if tempo is None:
        return None
    config['tempo'] = int(tempo)
    
    # 3. Generate tabs?
    generate_tabs = button_dialog(
        title='Generate Tabs',
        text='Do you want to generate ASCII guitar tabs (Drop D tuning)?',
        buttons=[
            ('Yes', True),
            ('No', False)
        ]
    ).run()
    config['generate_tabs'] = generate_tabs if generate_tabs is not None else False
    
    return config


def show_generation_preview(tracks, arrangement):
    """
    Shows a preview of what will be generated.
    
    Args:
        tracks: List of track dictionaries
        arrangement: List of arrangement sections
    """
    lines = ["=== Song Preview ===\n"]
    
    lines.append("TRACKS:")
    for t in tracks:
        lines.append(f"  {t['id']}: {t['name']} (Ch {t['channel']}, Patch {t['patch']})")
    
    lines.append("\nARRANGEMENT:")
    for section in arrangement:
        lines.append(f"  {section['name']}: {section['length_bars']} bars (starting bar {section['start_bar']})")
        for part in section['parts']:
            track_name = next((t['name'] for t in tracks if t['id'] == part['track_id']), f"Track {part['track_id']}")
            pattern_type = 'loop' if 'loop_pattern' in part else 'pattern'
            lines.append(f"    - {track_name} ({pattern_type})")
    
    message_dialog(title='Generation Preview', text='\n'.join(lines)).run()


def select_song_source():
    """
    Scans song_sources/ directory for .py files and lets user select one.
    Falls back to song_data.py if no files found or user wants default.
    
    Returns:
        str: Path to the selected song source file, or None if cancelled.
    """
    import os
    
    source_dir = "song_sources"
    song_files = []
    
    # Scan for .py files in song_sources/
    if os.path.isdir(source_dir):
        for f in sorted(os.listdir(source_dir)):
            if f.endswith('.py') and not f.startswith('__'):
                song_files.append(f)
    
    # Build selection values
    values = [('song_data.py', 'song_data.py (default)')]
    for f in song_files:
        values.append((os.path.join(source_dir, f), f"{f} (from {source_dir}/)"))
    
    if len(values) == 1:
        # Only default available, just use it
        return 'song_data.py'
    
    result = radiolist_dialog(
        title='Select Song Source',
        text='Choose a song data file to generate from:',
        values=values
    ).run()
    
    return result

def show_analysis_results(title: str, analysis_data: dict | None):
    """
    Displays the structured analysis results from a dictionary in a message dialog.
    Formats the output as plain text key-value pairs.

    Args:
        title (str): The title for the dialog window.
        analysis_data (dict | None): A dictionary containing the analysis results
                                     (e.g., {"key_signature": "Cmaj", "tempo_bpm": 120, ...})
                                     or None if analysis failed.
    """
    if not analysis_data or not isinstance(analysis_data, dict):
        display_text = "Analysis data is not available or is in an invalid format."
    else:
        # Format the dictionary into a readable plain text string
        lines = []
        # Define the desired order and friendly names for keys
        display_order = {
            "key_signature": "Key Signature",
            "tempo_bpm": "Tempo (BPM)",
            "time_signature": "Time Signature",
            "style_genre": "Style/Genre",
            "harmony_description": "Harmony"
        }
        for key, friendly_name in display_order.items():
            value = analysis_data.get(key, "N/A") # Get value or default to "N/A"
            # Simple key: value format
            lines.append(f"{friendly_name}: {value}")

        # Add any extra keys found in the data that weren't in the display_order
        for key, value in analysis_data.items():
            if key == "sections" and isinstance(value, list):
                lines.append("\nSong Sections:")
                for section in value:
                    name = section.get("name", "Unknown")
                    start = section.get("start_tick", 0)
                    end = section.get("end_tick", 0)
                    lines.append(f"  - {name}: {start} to {end} ticks")
            elif key not in display_order:
                 # Simple formatting for unexpected keys
                 friendly_name = key.replace('_', ' ').title()
                 lines.append(f"{friendly_name}: {value}")

        display_text = "\n".join(lines) # Join lines with single newline

    # Use message_dialog which handles multi-line text well
    message_dialog(title=title, text=display_text).run()

# Example usage (for testing tui.py directly)
if __name__ == '__main__':
    test_input_path = select_input_file()
    if test_input_path:
        # Simulate having loaded the file to get track count (replace with actual loading if needed for testing)
        try:
            # Dummy check for existence
            if not os.path.exists(test_input_path):
                 raise FileNotFoundError
            # Minimal load just to get track count for testing
            import mido
            mid = mido.MidiFile(test_input_path)
            track_count = len(mid.tracks)
            print(f"Selected input file: {test_input_path} (Tracks: {track_count})")
            user_settings = get_user_input(test_input_path, track_count)
            if user_settings:
                print("\nUser Settings (excluding input path):")
                for key, value in user_settings.items():
                    print(f"  {key}: {value}")
            else:
                print("\nUser cancelled during settings input.")
        except FileNotFoundError:
             print(f"Error: Test input file not found at '{test_input_path}'")
        except Exception as e:
            logger.exception("show_analysis_results failed")
            print(f"Error loading test file: {e}")

        # Example of showing analysis results
        print("\n--- Testing show_analysis_results ---")
        sample_analysis_good = {
            "key_signature": "Amin",
            "tempo_bpm": 95,
            "time_signature": "4/4",
            "style_genre": "Lo-fi Hip Hop",
            "harmony_description": "Uses minor chords and some borrowed chords.",
            "unexpected_field": "Some extra info"
        }
        print("Showing sample analysis (good data):")
        show_analysis_results("Sample Analysis", sample_analysis_good)

        print("\nShowing sample analysis (bad data - None):")
        show_analysis_results("Sample Analysis Failed", None)

        print("\nShowing sample analysis (bad data - list):")
        show_analysis_results("Sample Analysis Invalid", ["list", "not", "dict"])
        print("--- End testing show_analysis_results ---")

    else:
        print("\nUser cancelled input file selection.")
