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

def get_user_input():
    """
    Guides the user through a series of prompts to get MIDI processing settings.

    Returns:
        dict: A dictionary containing the user's selections,
              e.g., {'input_path': '...', 'output_path': '...', 'mode': '...', ...}
              Returns None if the user cancels.
    """
    settings = {}
    path_completer = PathCompleter()

    # 1. Get Input Path
    settings['input_path'] = input_dialog(
        title='Input MIDI File',
        text='Enter the path to the input MIDI file:',
        completer=path_completer,
        validator=NotEmptyValidator()
    ).run()
    if settings['input_path'] is None: return None # User cancelled

    # 2. Get Output Path
    default_output = os.path.join(
        os.path.dirname(settings['input_path']),
        f"{os.path.splitext(os.path.basename(settings['input_path']))[0]}_modified.mid"
    )
    settings['output_path'] = input_dialog(
        title='Output MIDI File',
        text='Enter the path for the output MIDI file:',
        default=default_output,
        completer=path_completer,
        validator=NotEmptyValidator()
    ).run()
    if settings['output_path'] is None: return None # User cancelled

    # 3. Get Mode
    mode = radiolist_dialog(
        title='Select Mode',
        text='Choose the operation mode:',
        values=[
            ('extend', 'Extend First Track'),
            ('complement', 'Add Complementary Track')
        ]
    ).run()
    if mode is None: return None # User cancelled
    settings['mode'] = mode

    # 4. Get Mode-Specific Parameters
    if mode == 'extend':
        bars = input_dialog(
            title='Extend Settings',
            text='Enter the number of bars to extend:',
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
    user_settings = get_user_input()
    if user_settings:
        print("\nUser Settings:")
        for key, value in user_settings.items():
            print(f"  {key}: {value}")
    else:
        print("\nUser cancelled.")
