**Project Title:** Gemini MIDI Modifier

**1. Introduction**

This project aims to create a tool that leverages the Gemini API to analyze and modify MIDI files based on user requests. The tool will allow users to load existing MIDI data, have it analyzed for musical structure (melody, harmony, chords), and then generate new MIDI data that extends or complements the original in musically coherent ways.

**2. Core Functionality**

*   **MIDI Input:** Load a standard MIDI file (.mid) provided by the user.
*   **MIDI Analysis (via Gemini):**
    *   Send relevant information extracted from the MIDI file (e.g., note sequences, timing, potentially track information) to the Gemini API.
    *   Prompt Gemini to identify:
        *   Main melody lines.
        *   Harmonic structure (chord progressions).
        *   Overall musical style/genre (if possible).
*   **User Interaction:**
    *   Present the analysis results to the user (optional, TBD).
    *   Prompt the user to choose a modification type:
        *   **Extend:** Generate additional musical material that continues the existing MIDI data in a similar style, potentially introducing variations.
        *   **Complement:** Generate new musical parts (e.g., bass line, harmony voices, counter-melody) that fit musically with the original MIDI data.
        *   *(Future: Other modification types like style transfer, simplification, etc.)*
    *   Allow the user to provide specific parameters (e.g., desired length of extension, type of complementary part).
*   **MIDI Generation (via Gemini):**
    *   Send the original MIDI information (or a representation of it), the analysis results, and the user's request to the Gemini API.
    *   Prompt Gemini to generate the new musical material in a structured format that can be converted back to MIDI.
*   **MIDI Output:**
    *   Combine the original MIDI data (if applicable) with the newly generated data.
    *   Save the resulting composition as a new standard MIDI file (.mid).

**3. Key Components & Technologies**

*   **Programming Language:** Python (recommended due to available libraries for MIDI and API interaction).
*   **MIDI Library:** A library capable of parsing, manipulating, and writing MIDI files (e.g., `mido`, `pretty_midi`).
*   **Gemini API Client:** Google AI Python SDK (`google-generativeai`) or direct REST API calls.
*   **User Interface:** Initially, a Command-Line Interface (CLI) for simplicity. A Graphical User Interface (GUI) could be a future enhancement.
*   **Data Representation:** Define a suitable intermediate representation for musical data exchanged with the Gemini API (e.g., text-based notation like ABC notation, simplified JSON structure, or potentially direct MIDI event descriptions if feasible).

**4. Workflow**

1.  User runs the program, providing the path to an input MIDI file.
2.  Program loads and parses the MIDI file using the chosen library.
3.  Program extracts relevant musical information.
4.  Program sends extracted information to Gemini for analysis.
5.  Program receives analysis (melody, harmony, chords).
6.  Program prompts the user for the desired modification type and parameters.
7.  Program constructs a generation prompt for Gemini, including original data context, analysis, and user request.
8.  Program sends the generation prompt to Gemini.
9.  Program receives the generated musical data representation from Gemini.
10. Program parses the generated data and converts it into MIDI events.
11. Program combines original and generated MIDI data as required by the modification type.
12. Program saves the final result as a new MIDI file.
13. Program informs the user of the output file location.

**5. Potential Challenges & Considerations**

*   **MIDI Complexity:** MIDI files can have multiple tracks, complex timing, instrument changes, and control messages. The initial version might focus on single-track melodies or simplified multi-track structures.
*   **Gemini Prompt Engineering:** Crafting effective prompts for both analysis and generation will be crucial and likely require iteration. Representing MIDI data effectively for the LLM is key.
*   **Musical Coherence:** Ensuring the generated output is musically valid and fits well with the original material is a primary challenge. Gemini's musical understanding will be tested.
*   **API Limitations:** Rate limits, input token limits, and the cost of API calls need to be considered.
*   **Determinism:** LLM outputs are often non-deterministic, meaning multiple runs with the same input might yield different results.

**6. Refinement Questions**

*   How should the MIDI data be represented when sending it to Gemini? (e.g., Note names and durations? Simplified piano roll? ABC notation?)
*   What level of detail is required from the Gemini analysis? Is just identifying the main melody enough, or do we need precise chord voicings?
*   For the "Extend" function, how much control should the user have over the variation?
*   For the "Complement" function, how will the program handle multiple existing tracks in the input MIDI? Should the user specify which track to complement?
*   How should errors (e.g., invalid MIDI, API errors, unparseable Gemini output) be handled?

Please review this initial draft. Let me know your thoughts, and we can refine it further before proceeding.