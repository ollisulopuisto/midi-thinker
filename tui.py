import os
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import radiolist_dialog, input_dialog, message_dialog
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.completion import PathCompleter

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


def get_user_input(input_path: str, num_tracks: int):
    """
    Guides the user through prompts for output path, mode, and parameters,
    using the provided input_path and number of tracks.

    Args:
        input_path (str): The path to the input MIDI file.
        num_tracks (int): The number of tracks in the input MIDI file.

    Returns:
        dict: A dictionary containing the user's selections (excluding input_path),
              e.g., {'output_path': '...', 'mode': '...', 'target_track_index': 0, ...}
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
    if settings['output_path'] is None: return None # User cancelled

    # 2. Get Mode
    mode = radiolist_dialog(
        title='Select Mode',
        text='Choose the operation mode:',
        values=[
            ('extend', 'Extend Track'),
            ('complement', 'Add Complementary Track')
        ]
    ).run()
    if mode is None: return None # User cancelled
    settings['mode'] = mode

    # 3. Get Mode-Specific Parameters
    if mode == 'extend':
        # 3a. Select Track to Extend (if multiple tracks exist)
        target_track_index = 0
        if num_tracks > 1:
            track_values = [(str(i), f"Track {i}") for i in range(num_tracks)]
            selected_track_str = radiolist_dialog(
                title='Select Track to Extend',
                text=f'Which track do you want to extend? (0-{num_tracks-1})',
                values=track_values
            ).run()
            if selected_track_str is None: return None # User cancelled
            target_track_index = int(selected_track_str)
        else:
            print("Only one track found. Extending Track 0.")
            # target_track_index remains 0

        settings['target_track_index'] = target_track_index

        # 3b. Get Bars to Extend
        bars = input_dialog(
            title='Extend Settings',
            text=f'Enter the number of bars to extend Track {target_track_index}:',
            default='4',
            validator=NumberValidator()
        ).run()
        if bars is None: return None # User cancelled
        settings['bars_to_extend'] = int(bars)

    elif mode == 'complement':
        comp_type = input_dialog(
            title='Complement Settings',
            text='Enter the type of complement (e.g., bassline, harmony, counter-melody):',
            default='bassline',
            validator=NotEmptyValidator()
        ).run()
        if comp_type is None: return None # User cancelled
        settings['complement_type'] = comp_type

    return settings

def show_error(title, text):
    """Displays an error message dialog."""
    message_dialog(title=title, text=text, style='class:error').run()

def show_success(title, text):
    """Displays a success message dialog."""
    message_dialog(title=title, text=text).run()

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
             print(f"Error loading test file: {e}")

    else:
        print("\nUser cancelled input file selection.")
