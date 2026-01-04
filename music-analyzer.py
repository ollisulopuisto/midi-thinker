import google.generativeai as genai
import os
import re
import time
import sys # Import sys for stderr
from dotenv import load_dotenv
import argparse # Added for command-line arguments
from googleapiclient.errors import HttpError # Import HttpError for specific exception handling
from google.api_core import exceptions as google_exceptions # Import for broader API errors
import json # Added for caching
import hashlib # Added for caching
import threading # Added for spinner
import itertools # Added for spinner
import midi_generator # Import the new module

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

# MIDI-asetukset (Keep only those NOT moved to midi_generator)
DEFAULT_BPM = 120     # Oletustempo, jos Gemini ei anna sitä (still needed for parsing)
# TICKS_PER_BEAT, DRUM_CHANNEL etc. are now in midi_generator

# Cache directory
CACHE_DIR = ".music-analyzer-cache"

# --- Spinner Class ---
class Spinner:
    def __init__(self, message="Processing..."):
        self._spinner = itertools.cycle(['-', '/', '|', '\\'])
        self._delay = 0.1
        self._running = False
        self._spinner_thread = None
        self._message = message
        self._stop_event = threading.Event()

    def _spin(self):
        while not self._stop_event.is_set():
            sys.stdout.write(f"\r{self._message} {next(self._spinner)}")
            sys.stdout.flush()
            time.sleep(self._delay)
        # Clear the spinner line
        sys.stdout.write('\r' + ' ' * (len(self._message) + 2) + '\r')
        sys.stdout.flush()

    def start(self):
        if not self._running:
            self._running = True
            self._stop_event.clear()
            self._spinner_thread = threading.Thread(target=self._spin)
            self._spinner_thread.start()

    def stop(self):
        if self._running:
            self._stop_event.set()
            if self._spinner_thread:
                self._spinner_thread.join() # Wait for thread to finish
            self._running = False
# --- End Spinner Class ---

# --- Helper-funktiot ---

def get_cache_filepath(audio_file_path: str) -> str | None:
    """Generates a cache filepath based on the hash of the input audio file."""
    try:
        hasher = hashlib.sha256()
        with open(audio_file_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        return os.path.join(CACHE_DIR, f"{file_hash}.json")
    except Exception as e:
        print(f"Varoitus: Ei voitu luoda cache-avainta tiedostolle {audio_file_path}: {e}", file=sys.stderr)
        return None

def load_from_cache(cache_filepath: str) -> dict | None:
    """Loads analysis data from a cache file."""
    if not cache_filepath or not os.path.exists(cache_filepath):
        return None
    try:
        with open(cache_filepath, 'r') as f:
            cached_data = json.load(f)
        print(f"Ladattu analyysi välimuistista: {cache_filepath}")
        return cached_data
    except json.JSONDecodeError:
        print(f"Varoitus: Virheellinen JSON cache-tiedostossa: {cache_filepath}. Ohitetaan cache.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Varoitus: Ei voitu ladata cache-tiedostosta {cache_filepath}: {e}", file=sys.stderr)
        return None

def save_to_cache(cache_filepath: str, analysis_data: dict):
    """Saves analysis data to a cache file."""
    if not cache_filepath or not analysis_data:
        return
    try:
        with open(cache_filepath, 'w') as f:
            json.dump(analysis_data, f, indent=2)
        print(f"Tallennettu analyysi välimuistiin: {cache_filepath}")
    except Exception as e:
        print(f"Varoitus: Ei voitu tallentaa cache-tiedostoon {cache_filepath}: {e}", file=sys.stderr)

def upload_audio_file(file_path, max_retries=3, initial_delay=2):
    """
    Lataa äänitiedoston Gemini API:lle ja palauttaa tiedostoreferenssin.
    Sisältää uudelleenyrityksen ja spinnerin.
    """
    print(f"Ladataan tiedostoa: {file_path}...")
    retries = 0
    delay = initial_delay
    # last_exception = None
    spinner = Spinner(f"Uploading {os.path.basename(file_path)}...") # Spinner for upload

    try:
        spinner.start() # Start spinner before upload attempt
        while retries <= max_retries:
            try:
                # Tarkista tiedoston koko ennen latausta (API:lla voi olla rajoituksia)
                # file_size = os.path.getsize(file_path)
                # Print size before spinner starts messing with the line too much
                # print(f"Tiedoston koko: {file_size / (1024*1024):.2f} MB") # Moved print

                audio_file = genai.upload_file(path=file_path)
                # print(f"Tiedoston lataus aloitettu: {audio_file.name}") # Spinner handles message

                # Odotetaan, että tiedosto on käsitelty (tärkeää!)
                spinner._message = f"Processing {audio_file.name}..." # Update spinner message
                while audio_file.state.name == "PROCESSING":
                    # print(f"Odetaan tiedoston {audio_file.name} käsittelyä...") # Spinner handles message
                    time.sleep(5) # Check status more frequently while spinner is active
                    try:
                        audio_file = genai.get_file(audio_file.name)
                    except (HttpError, google_exceptions.GoogleAPIError) as e:
                        # Myös tilan haku voi epäonnistua väliaikaisesti
                        print(f"\nVirhe haettaessa tiedoston tilaa: {e}. Oletetaan käsittelyn jatkuvan.", file=sys.stderr)
                        # Voit lisätä tähän logiikkaa, esim. yrittää uudelleen muutaman kerran ennen luovuttamista

                if audio_file.state.name == "FAILED":
                     raise ValueError(f"Tiedoston {file_path} (URI: {audio_file.uri}) lataus tai käsittely epäonnistui.")
                elif audio_file.state.name == "ACTIVE":
                    spinner.stop() # Stop spinner on success
                    print(f"Tiedosto {audio_file.name} (URI: {audio_file.uri}) ladattu ja valmis.")
                    return audio_file
                else:
                     spinner.stop() # Stop spinner even on unexpected state
                     print(f"Tiedoston {audio_file.name} tila on odottamaton: {audio_file.state.name}. Yritetään jatkaa...")
                     return audio_file # Voi olla riskialtista, mutta annetaan mahdollisuus

            except HttpError as e:
                # last_exception = e
                # Tarkista virhekoodi, yritä uudelleen vain tietyissä tapauksissa (5xx virheet)
                if e.resp.status >= 500 and retries < max_retries:
                    spinner.stop() # Stop spinner before printing error and waiting
                    print(f"\nVirhe {e.resp.status} ladatessa tiedostoa (yritys {retries + 1}/{max_retries + 1}). Yritetään uudelleen {delay} sekunnin kuluttua...", file=sys.stderr)
                    time.sleep(delay)
                    retries += 1
                    delay *= 2 # Exponential backoff
                    spinner.start() # Restart spinner for next attempt
                else:
                    raise # Re-raise the exception if not retrying or permanent error
            except google_exceptions.GoogleAPIError as e: # Laajempi Google API -virheiden käsittely
                # last_exception = e
                # Voit tarkentaa tätä, jos tiedät mitkä GoogleAPIError-virheet ovat väliaikaisia
                if retries < max_retries: # Yritä uudelleen yleisille API-virheille varovasti
                    spinner.stop() # Stop spinner before printing error and waiting
                    print(f"\nGoogle API -virhe ladatessa tiedostoa (yritys {retries + 1}/{max_retries + 1}). Yritetään uudelleen {delay} sekunnin kuluttua: {e}", file=sys.stderr)
                    time.sleep(delay)
                    retries += 1
                    delay *= 2
                    spinner.start() # Restart spinner for next attempt
                else:
                    raise # Re-raise the exception if not retrying or permanent error
            except Exception:
                # Muut odottamattomat virheet
                # last_exception = e
                raise # Re-raise immediately for unexpected errors

    except Exception as e: # Catch exceptions raised within the loop or initial setup
        spinner.stop() # Ensure spinner stops on any exception
        print(f"\nOdottamaton virhe ladatessa tai käsitellessä tiedostoa {file_path}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None # Return None on failure
    finally:
        # Ensure spinner is stopped no matter what
        if spinner._running:
            spinner.stop()


    # Jos kaikki uudelleenyritykset epäonnistuivat (should be caught by exceptions now)
    # print(f"Tiedoston {file_path} lataus epäonnistui {max_retries + 1} yrityksen jälkeen.")
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
    *   Tunnista päämelodiaa soittava instrumentti (jos mahdollista). Mainitse se otsikon alla ennen nuottilista.
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
        if re.match(r'^\d?\s*\.?\s*\*\*Tempo', line, re.IGNORECASE):
            current_section = "tempo"
            print("--- Jäsennetään Tempoa ---")
            continue
        if re.match(r'^\d?\s*\.?\s*\*\*Sävellaji', line, re.IGNORECASE):
            current_section = "key"
            print("--- Jäsennetään Sävellajia ---")
            continue
        if re.match(r'^\d?\s*\.?\s*\*\*Sointukierto', line, re.IGNORECASE):
            current_section = "chords"
            print("--- Jäsennetään Sointuja ---")
            continue
        if re.match(r'^\d?\s*\.?\s*\*\*Rummut', line, re.IGNORECASE):
            current_section = "drums"
            print("--- Jäsennetään Rumpuja ---")
            continue
        if re.match(r'^\d?\s*\.?\s*\*\*Lead-Melodia', line, re.IGNORECASE):
            current_section = "melody"
            print("--- Jäsennetään Melodiaa ---")
            continue
        # Käytä searchia harmonian otsikon tunnistamiseen, jotta '*   **Harmonia...*' toimii
        if re.search(r'\*\*.*?Harmonia', line, re.IGNORECASE):
             current_section = "harmonies"
             # Tarkista, onko tämä alaotsikko (esim. "Harmonia 1 (Jouset):")
             # Käytä searchia löytääksesi kuvion mistä tahansa, ottaen huomioon etuliitteet kuten '*  '
             match_harmony_header = re.search(r'Harmonia\s*\d*\s*(\(.*\))?:?', line, re.IGNORECASE) # <-- Käytä searchia
             if match_harmony_header:
                 # Pura nimi luotettavammin, poistaen mahdolliset etu-/jälkiliitteet
                 group_text = match_harmony_header.group(0).strip()
                 # Poista mahdolliset listamerkit tai ylimääräiset merkit
                 group_text = re.sub(r'^[*\-\s`]+', '', group_text) # Poista *, -, välilyönti, ` alusta
                 group_text = group_text.strip(':*` ') # Poista :, *, `, välilyönti lopusta ja alusta
                 current_harmony_group = group_text
                 print(f"--- Jäsennetään Harmoniaa ({current_harmony_group}) ---")
             else:
                 # Jos pääotsikko ilman tarkempaa nimeä, käytä oletusta
                 current_harmony_group = "Default Harmony"
                 print("--- Jäsennetään Harmoniaa (Oletus) ---")
             continue
        
        # Varmista, ettei otsikkoriviä yritetä jäsentää datana (tämä on edelleen hyödyllinen pääotsikoille)
        if line.startswith("**") or re.match(r'^\d\.', line):
             continue


        # Jäsennä dataa osion perusteella
        try:
            if current_section == "tempo":
                # Käytä searchia, se on robustimpi löytämään numeron '*   `123.4`' sisältä
                match = re.search(r'(\d+(\.\d+)?)', line)
                if match:
                    data["tempo"] = float(match.group(1))
                    print(f"Tunnistettu tempo: {data['tempo']} BPM")
                    current_section = None # Estää seuraavan rivin lukemisen tempona

            elif current_section == "key":
                # Käytä searchia, robustimpi
                match = re.search(r'([A-Ga-g][#b]?\s*(?:Major|Minor|Duuri|Molli))', line, re.IGNORECASE)
                if match:
                    data["key"] = match.group(1).strip()
                    print(f"Tunnistettu sävellaji: {data['key']}")
                    current_section = None # Estää seuraavan rivin lukemisen sävellajina
                else:
                    # Yritä purkaa `...` sisältä, jos tarkka kuvio ei täsmää
                    match_generic = re.search(r'`(.+?)`', line)
                    generic_key = match_generic.group(1).strip() if match_generic else line.lstrip('* ').strip() # Ota rivi ilman etuliitettä
                    if len(generic_key) > 0 and len(generic_key) < 20: # Heuristinen tarkistus
                         data["key"] = generic_key
                         print(f"Tunnistettu sävellaji (geneerinen): {data['key']}")
                         current_section = None


            elif current_section == "chords":
                # Käytä searchia ja käsittele valinnaiset backtickit
                # `?(\d+(?:\.\d+)?)`? : Valinnainen `, numero, valinnainen `
                # \s*-\s* : Välilyönti-viiva-välilyönti
                # `?(.+?)`? : Valinnainen `, mikä tahansa merkki (ei-ahne), valinnainen `
                # $ : Rivin loppu (auttaa välttämään osittaisia osumia)
                match = re.search(r'`?(\d+(?:\.\d+)?)`?\s*-\s*`?(.+?)`?$', line)
                if match:
                    time_sec = float(match.group(1))
                    chord_name = match.group(2).strip() # Poista mahdolliset ylimääräiset välilyönnit
                    data["chords"].append({"time": time_sec, "name": chord_name})
                    # print(f"Sointu: {time_sec:.2f}s - {chord_name}")
                # Lisää else if debuggausta varten, jos rivi ei ole vain listamerkki
                # elif line and not line.startswith('*'):
                #    print(f"Varoitus: Riviä ei voitu jäsentää sointuna: '{line}'")


            elif current_section == "drums":
                 # Käytä searchia ja käsittele valinnaiset backtickit (sama kuin soinnuille)
                match = re.search(r'`?(\d+(?:\.\d+)?)`?\s*-\s*`?(.+?)`?$', line)
                if match:
                    time_sec = float(match.group(1))
                    instrument_name = match.group(2).strip()
                    data["drums"].append({"time": time_sec, "instrument": instrument_name})
                    # print(f"Rumpu: {time_sec:.2f}s - {instrument_name}")
                # elif line and not line.startswith('*'):
                #    print(f"Varoitus: Riviä ei voitu jäsentää rumpuna: '{line}'")


            elif current_section == "melody" or current_section == "harmonies":
                 # Käytä searchia ja käsittele valinnaiset backtickit, salli pilkku/piste desimaalierottimena
                 # `?(\d+(?:[.,]\d+)?)`? : Aika
                 # \s*-\s*
                 # `?([A-Ga-g][#b]?\d)`? : Nuotti (esim. C4, F#5)
                 # \s*-\s*
                 # `?(\d+(?:[.,]\d+)?)`? : Kesto
                 match = re.search(r'`?(\d+(?:[.,]\d+)?)`?\s*-\s*`?([A-Ga-g][#b]?\d)`?\s*-\s*`?(\d+(?:[.,]\d+)?)`?', line.replace(',', '.'))
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
                 # Tunnista instrumenttirivit (käytä searchia ja poista backtickit)
                 elif re.search(r'Instrumentti:', line, re.IGNORECASE) and current_section == "melody":
                     instr_name = line.split(':', 1)[1].strip(' `') # Poista myös backtickit
                     print(f"Tunnistettu melodiainstrumentti (info): {instr_name}")
                 # Harmonian alaotsikot käsitellään jo otsikkologiikassa, joten ohita ne tässä
                 elif re.search(r'Harmonia\s*\d*\s*\(.*\)?:\s*$', line, re.IGNORECASE) and current_section == "harmonies":
                     pass # Jo käsitelty
                 # elif line and not line.startswith('*') and not re.search(r'Instrumentti:', line, re.IGNORECASE): # Vältä varoitusta listamerkeistä tai instrumenttiriveistä
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

# --- Pääohjelma ---
if __name__ == "__main__":
    # --- Argumenttien käsittely ---
    parser = argparse.ArgumentParser(description="Analysoi äänitiedosto Gemini API:lla ja luo MIDI-tiedoston.")
    parser.add_argument("audio_file", help="Polku syötettävään äänitiedostoon (esim. musiikki.mp3)")
    parser.add_argument(
        "--force-analyze",
        action="store_true",
        help="Ohita välimuisti ja pakota uusi analyysi Gemini API:lla."
    )
    args = parser.parse_args()
    audio_file_path = args.audio_file
    force_analyze = args.force_analyze
    # --- Argumenttien käsittely päättyy ---

    # Poistettu input()-kutsu
    # audio_file_path = input("Anna polku äänitiedostoon (esim. musiikki.mp3 tai /polku/kappale.wav): ")

    if not os.path.exists(audio_file_path):
        print(f"Virhe: Tiedostoa ei löytynyt polusta: {audio_file_path}")
        exit()

    parsed_data = None
    cache_filepath = get_cache_filepath(audio_file_path)

    # --- Caching Logic ---
    if not force_analyze and cache_filepath:
        cached_data = load_from_cache(cache_filepath)
        if cached_data:
            # Kysy käyttäjältä, haluaako hän käyttää cachea vai analysoida uudelleen
            while True:
                use_cache = input(f"Löytyi analyysi välimuistista ({cache_filepath}). Haluatko käyttää sitä? (k/e): ").lower().strip()
                if use_cache == 'k':
                    parsed_data = cached_data
                    print("Käytetään välimuistissa olevaa analyysia.")
                    break
                elif use_cache == 'e':
                    print("Ohitetaan välimuisti ja suoritetaan uusi analyysi.")
                    # parsed_data pysyy None, jotta API-kutsu suoritetaan
                    break
                else:
                    print("Virheellinen syöte. Vastaa 'k' (kyllä) tai 'e' (ei).")
    elif force_analyze:
        print("Pakotetaan uusi analyysi (--force-analyze).")
    # --- End Caching Logic ---


    if parsed_data is None: # If not found in cache, cache failed, user chose 'e', or --force-analyze was used
        if not force_analyze and cache_filepath and os.path.exists(cache_filepath) and use_cache != 'e': # Avoid redundant message if forced
             print("Analyysia ei löytynyt välimuistista tai uudelleenanalyysi valittu, suoritetaan API-kutsu...")
        # 1. Lataa audio Geminiin
        uploaded_file = upload_audio_file(audio_file_path) # Spinner is now inside this function
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
        # print("Tämä voi kestää jonkin aikaa riippuen äänitiedoston pituudesta ja mallista.") # Spinner will indicate activity

        api_spinner = Spinner("Waiting for Gemini API response...") # Spinner for API call
        response = None # Initialize response to None
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            # generation_config = genai.types.GenerationConfig(
            #      temperature=0.2 # Kokeile säätää lämpötilaa tarkkuuden/luovuuden tasapainottamiseksi
            # )
            # Käytä stream=False saadaksesi koko vastauksen kerralla

            # Try passing prompt and file object in a list, similar to 'contents'
            api_spinner.start() # Start spinner before API call
            response = model.generate_content(
                [prompt_content, uploaded_file], # Pass prompt string and uploaded file object
                stream=False
                #generation_config=generation_config
            )
            api_spinner.stop() # Stop spinner after getting response

            # Tarkista, että vastaus on olemassa ja sisältää tekstiä
            if not response or not hasattr(response, 'text') or not response.text:
                 print("\nVirhe: Gemini API ei palauttanut kelvollista tekstivastausta.")
                 # ... (rest of error handling) ...
                 exit()


            print("Gemini API -vastaus vastaanotettu.")
            # Tulosta raaka vastaus AINA debuggausta varten, jos jäsentäminen epäonnistuu
            print("\n--- Gemini Raw Response ---")
            print(response.text)
            print("---------------------------\n")


            # 3. Jäsennä vastaus
            print("Aloitetaan vastauksen jäsentäminen...")
            parsed_data = parse_gemini_response(response.text)

            # --- Save to Cache ---
            if parsed_data: # Only save if parsing was successful
                save_to_cache(cache_filepath, parsed_data)
            # --- End Save to Cache ---

            # Voit poistaa ladatun tiedoston Geministä, jos haluat siivota tilaa
            # Huom: Poistaminen vaatii tiedoston nimen (ei URIa)
            # try:
            #     print(f"\nYritetään poistaa ladattu tiedosto {uploaded_file.name} Geministä...")
            #     genai.delete_file(uploaded_file.name)
            #     print("Tiedosto poistettu.")
            # except Exception as e:
            #     print(f"Varoitus: Ladatun tiedoston poistaminen epäonnistui: {e}")


        except Exception as e:
            api_spinner.stop() # Ensure spinner stops on exception
            print(f"\nOhjelman suorituksessa tapahtui odottamaton virhe API-kutsun aikana: {e}")
            import traceback
            traceback.print_exc() # Tulostaa yksityiskohtaisemman virheenjäljityksen
            exit() # Exit if API call or parsing failed critically
        finally:
            # Ensure spinner is stopped no matter what
            if api_spinner._running:
                api_spinner.stop()

    # --- End of API call block ---

    # 4. Luo MIDI-tiedosto (tämä suoritetaan aina, joko cachesta tai API-kutsun jälkeen)
    if parsed_data: # Proceed only if we have data (from cache or API)
        output_midi_filename = os.path.splitext(os.path.basename(audio_file_path))[0] + ".mid"
        try:
            # Use the function from the imported module
            midi_generator.create_midi_file(parsed_data, output_midi_filename)
            # Success message is now printed within create_midi_file if successful
        except Exception:
            # Error message is printed within create_midi_file
            print(f"MIDI-tiedoston luonti epäonnistui tiedostoon {output_midi_filename}.", file=sys.stderr)
            # Optionally exit or handle the failure further here
    else:
        print("Analyysidataa ei saatavilla (ei cachesta eikä API:sta). MIDI-tiedostoa ei luoda.")


    print("\nOhjelman suoritus päättyi.")