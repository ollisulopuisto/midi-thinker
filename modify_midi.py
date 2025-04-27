import argparse
import mido
import sys

def main():
    parser = argparse.ArgumentParser(description="Modify a MIDI file using Gemini.")
    parser.add_argument("input_midi_path", help="Path to the input MIDI file.")
    parser.add_argument("output_midi_path", help="Path to save the modified MIDI file.")
    parser.add_argument("bars_to_extend", type=int, help="Number of bars to extend the first track by.") # TODO: Later change to ticks or handle bar conversion

    args = parser.parse_args()

    print(f"Loading MIDI file: {args.input_midi_path}")

    try:
        midi_file = mido.MidiFile(args.input_midi_path)
        print(f"Successfully loaded MIDI file. Type: {midi_file.type}, Ticks per beat: {midi_file.ticks_per_beat}")
        # TODO: Check if Type 1 as per MVP spec simplification?

    except FileNotFoundError:
        print(f"Error: Input MIDI file not found at {args.input_midi_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading MIDI file: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Placeholder for next steps ---
    print("MIDI loaded. Next steps: Parse data, call Gemini, modify, save.")
    print(f"Requested extension: {args.bars_to_extend} bars.")
    print(f"Output will be saved to: {args.output_midi_path}")
    # --- End Placeholder ---


if __name__ == "__main__":
    main()
