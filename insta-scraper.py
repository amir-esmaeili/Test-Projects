import instaloader
import spacy
import os
import getpass
import emoji
import pycountry
import pandas as pd
import time
import random
import json
import requests

ROTATE_PROXY = "http://vmebstzw-rotate:bji9bkkcz9ew@p.webshare.io:80/"


CACHE_DIR = "cache"
SESSION_FILES = [
    {"username": "account1", "file": "./session_account1"},
    {"username": "account2", "file": "./session_account2"},
]

DELAY_MIN = 60      # 1 minutes
DELAY_MAX = 120      # 2 minutes
LONG_COOLDOWN_MIN = 600  # 10 minutes
LONG_COOLDOWN_MAX = 900  # 15 minutes

FIND_MAX_RETRIES = 3

def create_country_allowlist():
    country_names = set()
    for country in pycountry.countries:
        country_names.add(country.name.title())
        if hasattr(country, 'official_name'):
            country_names.add(country.official_name.title())
    return country_names

def is_false_positive(entity_text, full_bio_text):
    ambiguous_terms = {
        "Ai": ["intelligence", "engineer", "msc", "machine learning", "researcher", "data"],
        "It": ["information", "technology", "tech", "developer"],
        "Art": ["artist", "design", "creative", "gallery"],
        "Ml": ["machine learning", "engineer", "data", "msc"]
    }
    normalized_entity = entity_text.title()
    if normalized_entity in ambiguous_terms:
        bio_lower = full_bio_text.lower()
        for keyword in ambiguous_terms[normalized_entity]:
            if keyword in bio_lower:
                return True
    return False


try:
    NLP = spacy.load("xx_ent_wiki_sm")
except Exception as e:
    print("Failed to load spaCy model 'xx_ent_wiki_sm'. Install with:")
    print("python -m spacy download xx_ent_wiki_sm")
    raise


def extract_locations_from_bio(bio, country_allowlist):
    doc = NLP(bio or "")
    text_locations = []
    for ent in doc.ents:
        if ent.label_ in ["LOC", "GPE"]:
            if not is_false_positive(ent.text, bio):
                text_locations.append(ent.text)

    flag_locations = []
    for item in emoji.emoji_list(bio or ""):
        emoji_char = item['emoji']
        emoji_name = emoji.demojize(emoji_char)
        if emoji_name.startswith(':'):
            country_candidate = (
                emoji_name.strip(':')
                .replace('_', ' ')
                .replace('flag for ', '')
                .title()
            )
            if country_candidate in country_allowlist:
                flag_locations.append(country_candidate)

    all_locations = text_locations + flag_locations
    unique_locations = list(dict.fromkeys(all_locations))
    if not unique_locations:
        return ["-NO LOCATION FOUND-"]
    return unique_locations


def ensure_cache_dir(path=CACHE_DIR):
    os.makedirs(path, exist_ok=True)

def cache_bio(username, bio, cache_dir=CACHE_DIR):
    ensure_cache_dir(cache_dir)
    cache_path = os.path.join(cache_dir, f"{username}.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"biography": bio}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_cached_bio(username, cache_dir=CACHE_DIR):
    cache_path = os.path.join(cache_dir, f"{username}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached.get("biography", "")
        except Exception:
            return ""
    return ""

def set_rotating_proxy_for_instaloader(L, rotate_proxy_url):
    if not rotate_proxy_url:
        return
    if not hasattr(L.context, "_session") or L.context._session is None:
        L.context._session = requests.Session()
    L.context._session.proxies = {"http": rotate_proxy_url, "https": rotate_proxy_url}
    L.context._session.trust_env = False

def test_rotate_proxy(rotate_proxy_url, timeout=8):
    """Quick smoke test for rotate endpoint."""
    if not rotate_proxy_url:
        print("No rotate proxy configured.")
        return False
    try:
        r = requests.get("https://httpbin.org/ip", proxies={"http": rotate_proxy_url, "https": rotate_proxy_url}, timeout=timeout)
        print("Rotate proxy test OK:", r.status_code, r.text.strip())
        return True
    except Exception as e:
        print("Rotate proxy test failed:", e)
        return False


def load_sessions(session_files=SESSION_FILES):
    sessions = []
    for s in session_files:
        L = instaloader.Instaloader()
        try:
            L.load_session_from_file(s["username"], s["file"])
            sessions.append({"L": L, "username": s["username"], "session_file": s["file"]})
            print(f"Loaded session for '{s['username']}' successfully!")
        except Exception as e:
            print(f"Could not load session for {s['username']}: {e}")
    if not sessions:
        print("No sessions loaded. Please create and save sessions with instaloader first.")
        exit()
    return sessions

def reload_session(session_obj):
    """Reload session from file (session_obj is dict returned from load_sessions)."""
    L = session_obj["L"]
    username = session_obj.get("username")
    session_file = session_obj.get("session_file")
    if username and session_file:
        L.load_session_from_file(username, session_file)
        print(f"Session refreshed for '{username}'.")
    else:
        raise RuntimeError("Cannot reload session - missing username/session_file.")


def find_location_in_bio(username_to_check, session_obj, country_allowlist, cache_dir=CACHE_DIR, max_retries=FIND_MAX_RETRIES):
    """
    session_obj is a dict: {'L': Instaloader(), 'username': ..., 'session_file': ...}
    We will set the rotating proxy on session_obj['L'] temporarily before making the request.
    """
    if not username_to_check or pd.isna(username_to_check):
        return ["-NO ID-"]

    ensure_cache_dir(cache_dir)
    cache_path = os.path.join(cache_dir, f"{username_to_check}.json")

    # Try cache first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            bio = cached_data.get("biography", "")
            if bio:
                print(f"-> Loaded cached bio for {username_to_check}")
                return extract_locations_from_bio(bio, country_allowlist)
        except Exception:
            pass

    L = session_obj["L"]
    print(f"\nProcessing ID: {username_to_check} with session '{session_obj.get('username')}'...")

    if ROTATE_PROXY:
        try:
            set_rotating_proxy_for_instaloader(L, ROTATE_PROXY)
        except Exception as e:
            print("Failed to set rotating proxy on Instaloader session:", e)

    retries = max_retries
    while retries > 0:
        try:
            profile = instaloader.Profile.from_username(L.context, username_to_check)
            bio = profile.biography or ""

            # Cache for next runs
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({"biography": bio}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            if not bio:
                return ["-NO BIO-"]

            return extract_locations_from_bio(bio, country_allowlist)

        except instaloader.exceptions.ProfileNotExistsException:
            print(f"-> Profile '{username_to_check}' not found.")
            return ["-PROFILE NOT FOUND-"]
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            print(f"-> Profile '{username_to_check}' is private.")
            return ["-PRIVATE PROFILE-"]
        except instaloader.exceptions.LoginRequiredException:
            print(f"-> Session expired. Attempting re-login.")
            try:
                reload_session(session_obj)
                continue
            except Exception as e:
                print(f"   Failed to re-login: {e}")
                return ["-SESSION ERROR-"]
        except Exception as e:
            err = str(e)
            if "401 Unauthorized" in err or "429 Too Many Requests" in err or "Please wait a few minutes" in err:
                print(f"-> RATE LIMITED on '{username_to_check}': {err}")
                retries -= 1
                if retries > 0:
                    cooldown = random.uniform(LONG_COOLDOWN_MIN, LONG_COOLDOWN_MAX)
                    print(f"   Cooling down for {cooldown/60:.2f} minutes. {retries} retries left.")
                    time.sleep(cooldown)
                else:
                    print(f"   All retries failed for '{username_to_check}'. Marking as error.")
                    return ["-RATE LIMIT ERROR-"]
            else:
                print(f"-> Unexpected error for '{username_to_check}': {e}")
                return ["-ERROR-"]

    return ["-UNKNOWN FAILURE-"]


if __name__ == "__main__":
    print("Building country database...")
    COUNTRY_ALLOWLIST = create_country_allowlist()

    sessions = load_sessions()
    num_sessions = len(sessions)

    if ROTATE_PROXY:
        print("\nTesting rotate proxy endpoint...")
        good = test_rotate_proxy(ROTATE_PROXY)
        if not good:
            print("Rotate proxy test failed. The script will still attempt to run, but you may get errors or rate limits.")
        else:
            print("Rotate proxy endpoint tested OK (requests will be routed through it for fetches).")

    print("\n--- CSV Processing ---")
    input_csv_path = input("Enter the path to your input CSV file: ")
    output_csv_path = input("Enter the path for your final output CSV: ")

    df_input = pd.read_csv(input_csv_path)
    id_column = 'string_list_data/0/value'
    link_column = 'string_list_data/0/href'

    if not all(col in df_input.columns for col in [id_column, link_column]):
        print("Error: Required columns not found in CSV.")
        exit()

    results_list = []
    total_rows = len(df_input)
    ensure_cache_dir(CACHE_DIR)

    for index, row in df_input.iterrows():
        insta_id = row[id_column]
        insta_link = row[link_column]

        session_obj = sessions[index % num_sessions]

        time.sleep(random.uniform(0.5, 2.0))

        locations = find_location_in_bio(insta_id, session_obj, COUNTRY_ALLOWLIST)
        location_str = ", ".join(locations)

        results_list.append({'link': insta_link, 'id': insta_id, 'location': location_str})
        print(f"-> Result: {location_str}")
        print(f"--- Progress: {index + 1}/{total_rows} ---")

        if (index + 1) % 10 == 0 or (index + 1) == total_rows:
            df_results = pd.DataFrame(results_list)
            df_results.to_csv(output_csv_path, index=False)
            print(f"\nProgress saved to {output_csv_path}.\n")

        if (index + 1) % 10 == 0:
            long_cooldown = random.uniform(LONG_COOLDOWN_MIN, LONG_COOLDOWN_MAX)
            print(f"Taking long cooldown of {long_cooldown/60:.2f} minutes to avoid rate limits...")
            time.sleep(long_cooldown)
        else:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f"Waiting {delay/60:.2f} minutes before next profile...")
            time.sleep(delay)

    print(f"\n✅ All done! Final results saved to '{output_csv_path}'.")
