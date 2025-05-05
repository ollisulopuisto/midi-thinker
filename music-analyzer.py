import google.generativeai as genai
import mido
import os
import re
import time
from dotenv import load_dotenv
import argparse # Added for command-line arguments

# --- Konfiguraatio ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Virhe: Gemini API -avainta ei löytynyt. Aseta se GEMINI_API_KEY ympäristömuuttujaan tai .env-tiedostoon.")
    exit()

genai.configure(api_key=API_KEY)

# Gemini-malli, joka tukee audiota (tarkista saatavilla olevat mallit)
# Käytetään pyydettyä kokeellista mallia
MODEL_NAME = "gemini-2.5-pro-exp-03-25" # <--- PÄIVITETTY TÄHÄN

# MIDI-asetukset
TICKS_PER_BEAT = 480  # Standardi resoluutio
DEFAULT_BPM = 120     # Oletustempo, jos Gemini ei anna sitä
DRUM_CHANNEL = 9      # MIDI-kanava 10 (0-indeksoitu) rummuille
MELODY_CHANNEL = 0    # MIDI-kanava 1
HARMONY_CHANNEL_1 = 1 # MIDI-kanava 2
HARMONY_CHANNEL_2 = 2 # MIDI-kanava 3
CHORD_CHANNEL = 3     # MIDI-kanava 4 (käytetään tekstiviesteille)

# --- Helper-funktiot ---

def upload_audio_file(file_path):
    """Lataa äänitiedoston Gemini API:lle ja palauttaa tiedostoreferenssin."""
    print(f"Ladataan tiedostoa: {file_path}...")
    try:
        # Tarkista tiedoston koko ennen latausta (API:lla voi olla rajoituksia)
        file_size = os.path.getsize(file_path)
        print(f"Tiedoston koko: {file_size / (1024*1024):.2f} MB")
        # Gemini 1.5 Prolla on suuri konteksti-ikkuna, mutta tarkista silti rajoitukset
        # if file_size > YOUR_SIZE_LIMIT_BYTES: # Aseta tarvittaessa kokorajoitus
        #    print("Virhe: Tiedosto on liian suuri.")
        #    return None

        audio_file = genai.upload_file(path=file_path)
        print(f"Tiedoston lataus aloitettu: {audio_file.name}")
        # Odotetaan, että tiedosto on käsitelty (tärkeää!)
        while audio_file.state.name == "PROCESSING":
            print(f"Odetaan tiedoston {audio_file.name} käsittelyä...")
            time.sleep(10) # Pidennä odotusaikaa isommille tiedostoille tai hitaammille malleille
            # Yritä hakea tiedoston tila uudelleen
            try:
                audio_file = genai.get_file(audio_file.name)
            except Exception as e:
                print(f"Virhe haettaessa tiedoston tilaa: {e}. Oletetaan käsittelyn jatkuvan.")
                # Voit lisätä tähän logiikkaa, esim. yrittää uudelleen muutaman kerran ennen luovuttamista

        if audio_file.state.name == "FAILED":
             raise ValueError(f"Tiedoston {file_path} (URI: {audio_file.uri}) lataus tai käsittely epäonnistui.")
        elif audio_file.state.name == "ACTIVE":
            print(f"Tiedosto {audio_file.name} (URI: {audio_file.uri}) ladattu ja valmis.")
            return audio_file
        else:
             print(f"Tiedoston {audio_file.name} tila on odottamaton: {audio_file.state.name}. Yritetään jatkaa...")
             # Voi olla riskialtista jatkaa, mutta annetaan mahdollisuus joskus toimia
             return audio_file

    except Exception as e:
        print(f"Virhe ladatessa tai käsitellessä tiedostoa {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def build_prompt(audio_file_uri):
    """Rakentaa promptin Gemini API:lle käyttäen tiedoston URI:a."""
    # Promptia voi hienosäätää kokeellisen mallin käyttäytymisen mukaan
    return f"""
Analysoi seuraava äänitiedosto URI:lla {audio_file_uri}

Pura siitä seuraavat musiikilliset tiedot mahdollisimman tarkasti ja jäsennellysti MIDI-muunnosta varten. Käytä selkeitä otsikoita ja alla määriteltyä muotoilua tarkasti. Ilmoita ajoitukset sekunteina (float) kappaleen alusta.

1.  **Tempo (BPM):**
    *   Arvioitu keskimääräinen tempo (Beats Per Minute). Esimerkki: `125.5`

2.  **Sävellaji:**
    *   Todennäköisin sävellaji. Käytä muotoa 'Avain Modi' (esim. `C Major`, `A Minor`).

3.  **Sointukierto:**
    *   Tärkeimmät soinnut ja niiden arvioidut alkamisajat sekunteina. Käytä TÄSMÄLLEEN tätä muotoa per rivi: `[aika_sekunteina] - [soinnun_nimi]`
    *   Esimerkki:
        `0.0 - Cmaj7`
        `4.1 - G7`
        `8.0 - Am`

4.  **Rummut ja Perkussiot (Kanava 10):**
    *   Listaa tärkeimpien rumpuäänten (Bassorumpu, Virveli, Hi-Hat (suljettu), Hi-Hat (avoin), Crash, Ride, Tom1, Tom2, etc.) iskuajat sekunteina. Käytä TÄSMÄLLEEN tätä muotoa per rivi: `[aika_sekunteina] - [instrumentti]`
    *   Esimerkki:
        `0.0 - Bassorumpu`
        `0.5 - Hi-Hat (suljettu)`
        `1.0 - Virveli`
        `1.0 - Bassorumpu`
        `1.5 - Hi-Hat (suljettu)`

5.  **Lead-Melodia (Kanava 1):**
    *   Tunnista päämelodiaa soittava instrumentti (jos mahdollista). Mainitse se otsikon alla ennen nuottilistaa.
    *   Listaa melodian nuotit: alkamisaika sekunteina, nuotin nimi oktaavilla (esim. C4, F#5, Bb3), kesto sekunteina. Käytä TÄSMÄLLEEN tätä muotoa per rivi: `[aika_sekunteina] - [nuotti] - [kesto_sekunteina]`
    *   Esimerkki:
        `Instrumentti: Piano`
        `2.1 - G4 - 0.4`
        `2.5 - A4 - 0.4`
        `3.0 - C5 - 0.9`

6.  **Tärkeimmät Harmoniate (Kanavat 2+):**
    *   Tunnista tärkeimmät harmoniaäänet tai -kerrokset (jos erotettavissa). Mainitse instrumentti jos mahdollista.
    *   Listaa harmonian nuotit samaan tapaan kuin Lead-Melodia. Käytä TÄSMÄLLEEN samaa muotoa per rivi. Jos tunnistat useita erillisiä harmonialinjoja, voit luoda alaotsikoita kuten "Harmonia 1 (Jouset):", "Harmonia 2 (Padi):".
    *   Esimerkki:
        `Harmonia 1 (Jouset):`
        `2.1 - E4 - 0.9`
        `4.1 - D4 - 0.9`
        `Harmonia 2 (Padi):`
        `0.0 - C3 - 4.0`
        `4.0 - G2 - 4.0`


Anna vastaus selkeästi jäsenneltynä yllä olevien otsikoiden ja muotoilujen mukaisesti. Tarkkuus ajoituksissa, nuoteissa ja muotoilussa on äärimmäisen tärkeää parserointia varten.
"""

def parse_gemini_response(text):
    """Jäsentää Geminin tekstivastauksen strukturoituun muotoon."""
    data = {
        "tempo": DEFAULT_BPM,
        "key": "C Major", # Oletus
        "chords": [],
        "drums": [],
        "melody": [],
        "harmonies": [] # Yksi lista kaikille, ellei malli käytä alaotsikoita
    }
    current_section = None
    current_harmony_group = None # Seurataan, mihin harmonialinjaan nuotit kuuluvat

    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Tunnista osioiden otsikot (tehdään vähemmän herkäksi pienille muutoksille)
        if re.match(r'^\d?\s*\.?\s*\*\*Tempo', line, re.IGNORECASE): current_section = "tempo"; print("--- Jäsennetään Tempoa ---"); continue
        if re.match(r'^\d?\s*\.?\s*\*\*Sävellaji', line, re.IGNORECASE): current_section = "key"; print("--- Jäsennetään Sävellajia ---"); continue
        if re.match(r'^\d?\s*\.?\s*\*\*Sointukierto', line, re.IGNORECASE): current_section = "chords"; print("--- Jäsennetään Sointuja ---"); continue
        if re.match(r'^\d?\s*\.?\s*\*\*Rummut', line, re.IGNORECASE): current_section = "drums"; print("--- Jäsennetään Rumpuja ---"); continue
        if re.match(r'^\d?\s*\.?\s*\*\*Lead-Melodia', line, re.IGNORECASE): current_section = "melody"; print("--- Jäsennetään Melodiaa ---"); continue
        if re.match(r'^\d?\s*\.?\s*\*\*.*?Harmonia', line, re.IGNORECASE):
             current_section = "harmonies"
             # Tarkista, onko tämä alaotsikko (esim. "Harmonia 1 (Jouset):")
             match_harmony_header = re.match(r'Harmonia\s*\d*\s*(\(.*\))?:?', line, re.IGNORECASE)
             if match_harmony_header:
                 current_harmony_group = match_harmony_header.group(0).strip(': ')
                 print(f"--- Jäsennetään Harmoniaa ({current_harmony_group}) ---")
             else:
                 current_harmony_group = "Default Harmony"
                 print("--- Jäsennetään Harmoniaa (Oletus) ---")
             continue
        
        # Varmista, ettei otsikkoriviä yritetä jäsentää datana
        if line.startswith("**") or re.match(r'^\d\.', line):
             continue


        # Jäsennä dataa osion perusteella
        try:
            if current_section == "tempo":
                # Etsi numero riviltä
                match = re.search(r'(\d+(\.\d+)?)', line)
                if match:
                    data["tempo"] = float(match.group(1))
                    print(f"Tunnistettu tempo: {data['tempo']} BPM")
                    current_section = None # Estää seuraavan rivin lukemisen tempona

            elif current_section == "key":
                # Olettaa, että avain on rivillä esim. "C Major" tai "A Minor"
                match = re.search(r'([A-Ga-g][#b]?\s*(?:Major|Minor|Duuri|Molli))', line, re.IGNORECASE)
                if match:
                    data["key"] = match.group(1).strip()
                    print(f"Tunnistettu sävellaji: {data['key']}")
                    current_section = None # Estää seuraavan rivin lukemisen sävellajina
                else:
                    # Jos ei löydy tarkkaa vastinetta, otetaan koko rivi (voi olla vain "C" tms.)
                    if len(line) > 0 and len(line) < 15: # Heuristinen tarkistus
                         data["key"] = line
                         print(f"Tunnistettu sävellaji (geneerinen): {data['key']}")
                         current_section = None


            elif current_section == "chords":
                # Muoto: [aika_sekunteina] - [soinnun_nimi]
                match = re.match(r'(\d+(?:\.\d+)?)\s*-\s*(.+)', line)
                if match:
                    time_sec = float(match.group(1))
                    chord_name = match.group(2).strip()
                    data["chords"].append({"time": time_sec, "name": chord_name})
                    # print(f"Sointu: {time_sec:.2f}s - {chord_name}")


            elif current_section == "drums":
                 # Muoto: [aika_sekunteina] - [instrumentti]
                match = re.match(r'(\d+(?:\.\d+)?)\s*-\s*(.+)', line)
                if match:
                    time_sec = float(match.group(1))
                    instrument_name = match.group(2).strip()#.lower() # Pidä alkuperäinen kirjainkoko joskus hyödyllinen
                    data["drums"].append({"time": time_sec, "instrument": instrument_name})
                    # print(f"Rumpu: {time_sec:.2f}s - {instrument_name}")


            elif current_section == "melody" or current_section == "harmonies":
                 # Muoto: [aika_sekunteina] - [nuotti] - [kesto_sekunteina]
                 # Salli sekä piste että pilkku desimaalierottimena ja erilaiset välilyönnit
                 match = re.match(r'(\d+(?:[.,]\d+)?)\s*-\s*([A-Ga-g][#b]?\d)\s*-\s*(\d+(?:[.,]\d+)?)', line.replace(',', '.'))
                 if match:
                     time_sec = float(match.group(1))
                     note_name = match.group(2).strip()
                     duration_sec = float(match.group(3))
                     note_data = {"time": time_sec, "note": note_name, "duration": duration_sec}
                     if current_section == "melody":
                         data["melody"].append(note_data)
                         # print(f"Melodia: {time_sec:.2f}s - {note_name} - {duration_sec:.2f}s")
                     else:
                         # Lisää tieto mihin harmoniaryhmään kuuluu, jos tunnistettu
                         note_data["group"] = current_harmony_group if current_harmony_group else "Default Harmony"
                         data["harmonies"].append(note_data)
                         # print(f"Harmonia ({note_data['group']}): {time_sec:.2f}s - {note_name} - {duration_sec:.2f}s")
                 # Tunnista instrumenttirivit
                 elif line.lower().startswith("instrumentti:") and current_section == "melody":
                     print(f"Tunnistettu melodiainstrumentti (info): {line.split(':', 1)[1].strip()}")
                 elif line.lower().startswith("harmonia") and line.endswith(":") and current_section == "harmonies":
                     # Tämä on jo käsitelty otsikkologiikassa, mutta varmuuden vuoksi ohitetaan tässä
                     pass
                 #elif line and (current_section == "melody" or current_section == "harmonies"):
                 #    print(f"Varoitus: Riviä ei voitu jäsentää nuottina ({current_section}): '{line}'")


        except ValueError as e:
            print(f"Varoitus: Virhe jäsentäessä riviä ({current_section}): '{line}'. Virhe: {e}")
        except Exception as e:
            print(f"Odottamaton virhe jäsentäessä riviä ({current_section}): '{line}'. Virhe: {e}")


    # Lajitellaan tapahtumat ajan mukaan käsittelyn helpottamiseksi
    for key in ["chords", "drums", "melody", "harmonies"]:
         if key in data and isinstance(data[key], list):
            data[key].sort(key=lambda x: x.get('time', 0))


    print("Gemini-vastauksen jäsentäminen valmis.")
    # Tulosta yhteenveto tunnistetuista elementeistä
    print(f"  Tempo: {data.get('tempo', 'Ei tunnistettu')}")
    print(f"  Sävellaji: {data.get('key', 'Ei tunnistettu')}")
    print(f"  Sointuja: {len(data.get('chords', []))}")
    print(f"  Rumpu/Perkussioita: {len(data.get('drums', []))}")
    print(f"  Melodianuotteja: {len(data.get('melody', []))}")
    print(f"  Harmonianuotteja: {len(data.get('harmonies', []))}")

    return data

# --- MIDI-muunnosfunktiot ---

def note_name_to_midi(note_name):
    """Muuntaa nuotin nimen (esim. C4, F#5) MIDI-numeroksi."""
    notes = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5,
             'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
    match = re.match(r'([A-Ga-g][#b]?)(\d+)', note_name)
    if not match:
        print(f"Varoitus: Virheellinen nuotin nimi '{note_name}', käytetään C4 (60)")
        return 60 # Oletusarvo virhetilanteessa
    
    name_part = match.group(1)
    octave = int(match.group(2))
    
    # Normalisoi nimi (esim. c#, db -> C#, Db)
    name = name_part[0].upper()
    if len(name_part) > 1:
        name += name_part[1].lower() # Esim. # tai b

    # Muunna flatit sharpeiksi tai päinvastoin tarvittaessa MIDIa varten
    # Tässä esimerkissä oletetaan standardimappaus, jossa C#=Db jne.
    if name not in notes:
         # Kokeile vaihtaa enharmonisesti
         enharmonic_map = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
         sharp_map = {v: k for k, v in enharmonic_map.items()} # Käänteinen mappaus
         
         if name in enharmonic_map:
              original_name = name
              name = enharmonic_map[name]
              # print(f"Huom: Muunnettiin enharmonisesti {original_name} -> {name}")
         elif name in sharp_map:
              original_name = name
              name = sharp_map[name]
              # print(f"Huom: Muunnettiin enharmonisesti {original_name} -> {name}")
         else:
              print(f"Varoitus: Tuntematon nuotin perusnimi '{name_part}' nuotissa '{note_name}', käytetään C4 (60)")
              return 60

    midi_note = notes[name] + (octave + 1) * 12 # MIDI C4 = 60
    # Varmistetaan että nuotti on MIDI-alueella (0-127)
    return max(0, min(127, midi_note))


def drum_name_to_midi(instrument_name):
    """Muuntaa yleisimmät rumpuinstrumenttien nimet General MIDI -numeroiksi (kanava 10)."""
    name = instrument_name.lower().strip()
    # Yritetään olla tarkempia
    if "bass drum" in name or "kick" in name or "bassorumpu" in name: return 36 # Acoustic Bass Drum (usein myös 35 GM2:ssa)
    if "acoustic snare" in name or (("virveli" in name or "snare" in name) and not "electric" in name): return 38
    if "electric snare" in name: return 40
    if "snare" in name or "virveli" in name: return 38 # Oletus snarelle
    if "low floor tom" in name or "floor tom 1" in name: return 41
    if "closed hi-hat" in name or "closed hh" in name or "hi-hat (suljettu)" in name: return 42
    if "high floor tom" in name or "floor tom 2" in name: return 43
    if "pedal hi-hat" in name: return 44
    if "low tom" in name or "tom 3" in name: return 45
    if "open hi-hat" in name or "open hh" in name or "hi-hat (avoin)" in name: return 46
    if "low-mid tom" in name or "tom 2" in name: return 47
    if "hi-mid tom" in name or "tom 1" in name: return 48
    if "crash cymbal 1" in name or "crash 1" in name or "crash" in name: return 49 # Oletus crashille
    if "high tom" in name or "tom 0" in name : return 50
    if "ride cymbal 1" in name or "ride 1" in name or "ride" in name: return 51 # Oletus ridelle
    if "chinese cymbal" in name: return 52
    if "ride bell" in name: return 53
    if "tambourine" in name: return 54
    if "splash cymbal" in name: return 55
    if "cowbell" in name: return 56
    if "crash cymbal 2" in name or "crash 2" in name: return 57
    if "vibraslap" in name: return 58
    if "ride cymbal 2" in name or "ride 2" in name: return 59
    if "hi bongo" in name: return 60
    if "low bongo" in name: return 61
    if "mute hi conga" in name: return 62
    if "open hi conga" in name: return 63
    if "low conga" in name: return 64
    if "high timbale" in name: return 65
    if "low timbale" in name: return 66
    if "hand clap" in name or "clap" in name: return 39
    if "rim shot" in name or "rim" in name: return 37

    # Yleisemmät termit
    if "tom" in name: return 45 # Oletus tomille (Low Tom)
    if "hi-hat" in name or "hh" in name: return 42 # Oletus hi-hatille (Closed)
    if "cymbal" in name: return 49 # Oletus symbaalille (Crash 1)

    # Oletus tuntemattomille äänille
    print(f"Varoitus: Tuntematon rumpuääni '{instrument_name}'. Käytetään Acoustic Snare (38).")
    return 38

def seconds_to_ticks(seconds, bpm, ticks_per_beat):
    """Muuntaa ajan sekunneista MIDI-tickeiksi."""
    if bpm <= 0:
        print("Varoitus: BPM on nolla tai negatiivinen. Käytetään oletusta 120.")
        bpm = 120
    beats = (float(seconds) * float(bpm)) / 60.0
    ticks = int(round(beats * float(ticks_per_beat))) # Pyöristetään lähimpään kokonaiseen tickiin
    return ticks

def midi_key_name(key_string):
    """ Muuntaa 'C Major', 'A Minor' tyyppisen merkkijonon mido-kirjaston vaatimaan muotoon ('C', 'Am'). """
    parts = key_string.split()
    if not parts:
        return 'C' # Oletus

    key = parts[0].capitalize()
    # Varmista, että on sharps/flats mukana
    if len(key) > 1 and key[1] in ['#', 'b']:
        pass # OK
    elif len(key) > 1: # Esim Csharp -> C#
         if key[1:].lower() == 'sharp': key = key[0] + '#'
         elif key[1:].lower() == 'flat': key = key[0] + 'b'
         else: key = key[0] # Ota vain ensimmäinen kirjain, jos ei #/b


    mode = 'major' # Oletus
    if len(parts) > 1 and parts[1].lower() in ['minor', 'molli', 'm']:
        mode = 'minor'

    if mode == 'minor':
        return key + 'm'
    else:
        return key


def create_midi_file(data, output_filename="output.mid"):
    """Luo MIDI-tiedoston jäsennetystä datasta."""
    print(f"Luodaan MIDI-tiedostoa: {output_filename}")
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT) # type=1 for multi-track

    current_bpm = data.get('tempo', DEFAULT_BPM)
    if current_bpm <= 0:
        print(f"Varoitus: Annettu BPM ({current_bpm}) on virheellinen. Käytetään oletusta {DEFAULT_BPM}.")
        current_bpm = DEFAULT_BPM

    # --- Track 0: Meta-viestit (Tempo, Sävellaji, Sointunimet) ---
    meta_track = mido.MidiTrack()
    mid.tracks.append(meta_track)
    meta_track.append(mido.MetaMessage('track_name', name='Meta Info', time=0))
    # Aseta tempo
    tempo_usec = mido.bpm2tempo(current_bpm)
    meta_track.append(mido.MetaMessage('set_tempo', tempo=tempo_usec, time=0))
    # Aseta sävellaji
    key_input = data.get('key', 'C Major')
    mido_key = midi_key_name(key_input)
    meta_track.append(mido.MetaMessage('key_signature', key=mido_key, time=0))
    print(f"Asetetaan MIDI-sävellaji: {mido_key} (alkuperäinen: '{key_input}')")

    # Lisää sointujen nimet tekstiviesteinä tai merkkeriviesteinä
    last_meta_tick = 0
    for chord in data.get("chords", []):
        chord_tick = seconds_to_ticks(chord['time'], current_bpm, TICKS_PER_BEAT)
        delta_time = max(0, chord_tick - last_meta_tick) # Delta-aika ei voi olla negatiivinen
        # Käytä 'marker' tyyppiä, jotkut DAW:t näyttävät ne paremmin
        meta_track.append(mido.MetaMessage('marker', text=chord['name'], time=delta_time))
        last_meta_tick = chord_tick

    # --- Track 1: Rummut ---
    drum_track = mido.MidiTrack()
    mid.tracks.append(drum_track)
    drum_track.append(mido.MetaMessage('track_name', name='Drums', time=0))
    # Kanava 10 on oletus rummuille MIDI-standardissa
    drum_track.append(mido.Message('control_change', control=0, value=0, time=0, channel=DRUM_CHANNEL)) # Bank Select MSB (varmuuden vuoksi)
    drum_track.append(mido.Message('control_change', control=32, value=0, time=0, channel=DRUM_CHANNEL))# Bank Select LSB
    drum_track.append(mido.Message('program_change', program=0, time=0, channel=DRUM_CHANNEL)) # Standard Drum Kit

    drum_events = []
    for hit in data.get("drums", []):
        tick = seconds_to_ticks(hit['time'], current_bpm, TICKS_PER_BEAT)
        note = drum_name_to_midi(hit['instrument'])
        # Lisätään lyhyt Note On ja heti perään Note Off
        drum_events.append({'tick': tick, 'type': 'note_on', 'note': note, 'velocity': 100, 'channel': DRUM_CHANNEL})
        # Lyhyt kesto rumpuäänille (esim. 60 tickiä = ~1/32 nuotti @ 480 TPB)
        duration_ticks = 60 #max(1, int(TICKS_PER_BEAT / 8)) # Vähintään 1 tick
        drum_events.append({'tick': tick + duration_ticks, 'type': 'note_off', 'note': note, 'velocity': 0, 'channel': DRUM_CHANNEL})

    # Lajitellaan rumpu-eventit ja lasketaan delta-ajat
    drum_events.sort(key=lambda x: x['tick'])
    last_drum_tick = 0
    for event in drum_events:
        delta_time = max(0, event['tick'] - last_drum_tick)
        drum_track.append(mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel']))
        last_drum_tick = event['tick']

    # --- Track 2: Melodia ---
    melody_track = mido.MidiTrack()
    mid.tracks.append(melody_track)
    melody_track.append(mido.MetaMessage('track_name', name='Lead Melody', time=0))
    melody_track.append(mido.Message('program_change', program=0, time=0, channel=MELODY_CHANNEL)) # Esim. 0: Acoustic Grand Piano

    note_events_melody = []
    for note_info in data.get("melody", []):
        start_tick = seconds_to_ticks(note_info['time'], current_bpm, TICKS_PER_BEAT)
        duration_ticks = seconds_to_ticks(note_info['duration'], current_bpm, TICKS_PER_BEAT)
        # Varmistetaan minimikesto
        duration_ticks = max(1, duration_ticks)
        end_tick = start_tick + duration_ticks
        midi_note = note_name_to_midi(note_info['note'])

        note_events_melody.append({'tick': start_tick, 'type': 'note_on', 'note': midi_note, 'velocity': 90, 'channel': MELODY_CHANNEL})
        note_events_melody.append({'tick': end_tick, 'type': 'note_off', 'note': midi_note, 'velocity': 0, 'channel': MELODY_CHANNEL})

    # Lajitellaan nuotti-eventit ja lasketaan delta-ajat
    note_events_melody.sort(key=lambda x: x['tick'])
    last_melody_tick = 0
    for event in note_events_melody:
        delta_time = max(0, event['tick'] - last_melody_tick)
        melody_track.append(mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel']))
        last_melody_tick = event['tick']


    # --- Seuraavat raidat: Harmoniat (ryhmiteltynä tai kaikki yhdellä raidalla) ---
    harmony_groups = {}
    for note_info in data.get("harmonies", []):
        group_name = note_info.get("group", "Default Harmony")
        if group_name not in harmony_groups:
            harmony_groups[group_name] = []
        harmony_groups[group_name].append(note_info)

    harmony_channel_map = { # Määritellään kanavat eri harmoniaryhmille
        "Default Harmony": HARMONY_CHANNEL_1,
        # Voit lisätä tähän lisää mappauksia, jos Gemini tunnistaa esim. "(Jouset)"
        "Harmonia 1 (Jouset)": HARMONY_CHANNEL_1,
        "Harmonia 2 (Padi)": HARMONY_CHANNEL_2,
    }
    used_channels = {MELODY_CHANNEL, DRUM_CHANNEL} # Pidä kirjaa käytetyistä kanavista
    next_harmony_channel = HARMONY_CHANNEL_1

    for group_name, notes in harmony_groups.items():
        # Valitse kanava tälle harmoniaryhmälle
        current_harmony_channel = harmony_channel_map.get(group_name)
        if current_harmony_channel is None or current_harmony_channel in used_channels:
             # Etsi seuraava vapaa kanava (vältä rumpukanavaa 9)
             while next_harmony_channel in used_channels or next_harmony_channel == DRUM_CHANNEL:
                 next_harmony_channel += 1
                 if next_harmony_channel > 15: # Loppuivatko kanavat?
                      print("Varoitus: MIDI-kanavat loppuivat, käytetään kanavaa 1 uudelleen.")
                      next_harmony_channel = 1 # Käytä kanavaa 1 uudelleen (ei ihanteellista)
                      break
             current_harmony_channel = next_harmony_channel
             harmony_channel_map[group_name] = current_harmony_channel # Tallenna mappaus
             used_channels.add(current_harmony_channel)
             next_harmony_channel += 1

        print(f"Luodaan harmoniaraita '{group_name}' kanavalle {current_harmony_channel + 1}")
        harmony_track = mido.MidiTrack()
        mid.tracks.append(harmony_track)
        harmony_track.append(mido.MetaMessage('track_name', name=f'Harmony: {group_name}', time=0))
        # Valitse instrumentti (esim. Jouset 48, Padi 89, kuoro 52) - voit tehdä tästä älykkäämmän
        program = 48 # Oletus: Strings
        if "pad" in group_name.lower(): program = 89 # Warm Pad
        elif "choir" in group_name.lower() or "aah" in group_name.lower(): program = 52 # Choir Aahs
        harmony_track.append(mido.Message('program_change', program=program, time=0, channel=current_harmony_channel))

        harmony_events = []
        for note_info in notes:
            start_tick = seconds_to_ticks(note_info['time'], current_bpm, TICKS_PER_BEAT)
            duration_ticks = seconds_to_ticks(note_info['duration'], current_bpm, TICKS_PER_BEAT)
            duration_ticks = max(1, duration_ticks)
            end_tick = start_tick + duration_ticks
            midi_note = note_name_to_midi(note_info['note'])

            harmony_events.append({'tick': start_tick, 'type': 'note_on', 'note': midi_note, 'velocity': 70, 'channel': current_harmony_channel})
            harmony_events.append({'tick': end_tick, 'type': 'note_off', 'note': midi_note, 'velocity': 0, 'channel': current_harmony_channel})

        # Lajitellaan tämän harmoniatrackin eventit ja lasketaan delta-ajat
        harmony_events.sort(key=lambda x: x['tick'])
        last_harmony_tick = 0
        for event in harmony_events:
            delta_time = max(0, event['tick'] - last_harmony_tick)
            harmony_track.append(mido.Message(event['type'], note=event['note'], velocity=event['velocity'], time=delta_time, channel=event['channel']))
            last_harmony_tick = event['tick']

    # Lisää End of Track -viestit jokaiseen raitaan oikealla delta-ajalla
    for i, track in enumerate(mid.tracks):
        last_tick_on_track = sum(msg.time for msg in track)
        # Varmista, että end_of_track tulee *viimeisen* viestin jälkeen kaikilla raidoilla
        # Etsi absoluuttinen maksimiaika kaikilta raidoilta
        max_tick = 0
        for t in mid.tracks:
             max_tick = max(max_tick, sum(msg.time for msg in t))

        # Laske delta aika tämän raidan viimeisestä viestistä kokonaiskestoon
        delta_to_end = max(0, max_tick - last_tick_on_track)
        track.append(mido.MetaMessage('end_of_track', time=delta_to_end))

    # Tallenna MIDI-tiedosto
    try:
        mid.save(output_filename)
        print(f"MIDI-tiedosto tallennettu onnistuneesti: {output_filename}")
    except Exception as e:
        print(f"Virhe tallennettaessa MIDI-tiedostoa: {e}")


# --- Pääohjelma ---
if __name__ == "__main__":
    # --- Argumenttien käsittely ---
    parser = argparse.ArgumentParser(description="Analysoi äänitiedosto Gemini API:lla ja luo MIDI-tiedoston.")
    parser.add_argument("audio_file", help="Polku syötettävään äänitiedostoon (esim. musiikki.mp3)")
    args = parser.parse_args()
    audio_file_path = args.audio_file
    # --- Argumenttien käsittely päättyy ---

    # Poistettu input()-kutsu
    # audio_file_path = input("Anna polku äänitiedostoon (esim. musiikki.mp3 tai /polku/kappale.wav): ")

    if not os.path.exists(audio_file_path):
        print(f"Virhe: Tiedostoa ei löytynyt polusta: {audio_file_path}")
        exit()

    # 1. Lataa audio Geminiin
    uploaded_file = upload_audio_file(audio_file_path)
    if not uploaded_file:
        print("Audion lataus epäonnistui. Ohjelma lopetetaan.")
        exit()

    # Varmista, että saatiin URI
    if not hasattr(uploaded_file, 'uri'):
         print("Virhe: Ladatulta tiedostolta puuttuu URI. API-vastaus saattoi muuttua.")
         # Yritä käyttää nimeä varalta, mutta tämä voi epäonnistua
         file_identifier = uploaded_file.name
    else:
         file_identifier = uploaded_file.uri # Käytä URIa jos saatavilla

    # 2. Rakenna ja lähetä promptti
    # Käytä URIa promptissa
    prompt_content = build_prompt(file_identifier)
    print("\nLähetetään pyyntö Gemini API:lle mallilla {}...".format(MODEL_NAME))
    print("Tämä voi kestää jonkin aikaa riippuen äänitiedoston pituudesta ja mallista.")


    try:
        model = genai.GenerativeModel(MODEL_NAME)
        # generation_config = genai.types.GenerationConfig(
        #      temperature=0.2 # Kokeile säätää lämpötilaa tarkkuuden/luovuuden tasapainottamiseksi
        # )
        # Käytä stream=False saadaksesi koko vastauksen kerralla

        # Try passing prompt and file object in a list, similar to 'contents'
        response = model.generate_content(
            [prompt_content, uploaded_file], # Pass prompt string and uploaded file object
            stream=False
            #generation_config=generation_config
        )

        # Tarkista, että vastaus on olemassa ja sisältää tekstiä
        if not response or not hasattr(response, 'text') or not response.text:
             print("\nVirhe: Gemini API ei palauttanut kelvollista tekstivastausta.")
             print("Mahdollisia syitä: API-virhe, malli ei pystynyt käsittelemään pyyntöä, vastausmuoto tuntematon.")
             # Tulosta koko vastausobjekti debuggausta varten, jos se on olemassa
             if response:
                  print("\n--- Koko Gemini-vastaus (Debug) ---")
                  try:
                      print(response)
                  except Exception as print_e:
                      print(f"Ei voitu tulostaa vastausta: {print_e}")
                  print("-----------------------------------\n")
             exit()


        print("Gemini API -vastaus vastaanotettu.")
        # Tulosta raaka vastaus AINA debuggausta varten, jos jäsentäminen epäonnistuu
        print("\n--- Gemini Raw Response ---")
        print(response.text)
        print("---------------------------\n")


        # 3. Jäsennä vastaus
        print("Aloitetaan vastauksen jäsentäminen...")
        parsed_data = parse_gemini_response(response.text)


        # 4. Luo MIDI-tiedosto
        output_midi_filename = os.path.splitext(os.path.basename(audio_file_path))[0] + ".mid"
        create_midi_file(parsed_data, output_midi_filename)


        # Voit poistaa ladatun tiedoston Geministä, jos haluat siivota tilaa
        # Huom: Poistaminen vaatii tiedoston nimen (ei URIa)
        # try:
        #     print(f"\nYritetään poistaa ladattu tiedosto {uploaded_file.name} Geministä...")
        #     genai.delete_file(uploaded_file.name)
        #     print("Tiedosto poistettu.")
        # except Exception as e:
        #     print(f"Varoitus: Ladatun tiedoston poistaminen epäonnistui: {e}")


    except Exception as e:
        print(f"\nOhjelman suorituksessa tapahtui odottamaton virhe: {e}")
        import traceback
        traceback.print_exc() # Tulostaa yksityiskohtaisemman virheenjäljityksen


    print("\nOhjelman suoritus päättyi.")