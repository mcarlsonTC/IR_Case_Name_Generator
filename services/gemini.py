import os
import random
import logging
import pandas as pd
from google import genai

logger = logging.getLogger(__name__)

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client

_locale_df = None

def get_locale_df() -> pd.DataFrame:
    global _locale_df
    if _locale_df is None:
        _locale_df = pd.read_excel("data/ZIP_Locale_Detail.xls")
    return _locale_df

def get_random_city() -> tuple[str, str]:
    df = get_locale_df()
    row = df[["PHYSICAL CITY", "PHYSICAL STATE"]].dropna().drop_duplicates().sample(1).iloc[0]
    city_slug = row["PHYSICAL CITY"].lower().strip().replace(" ", "-")
    display = f"{row['PHYSICAL CITY'].strip()}, {row['PHYSICAL STATE'].strip()}"
    return city_slug, display

def generate_case_name(existing_cases: list[str]) -> tuple[str, str]:
    for attempt in range(3):
        city_slug, city_display = get_random_city()
        year = __import__("datetime").datetime.utcnow().year
        case_name = f"{year}-ir-{city_slug}"

        if case_name not in existing_cases:
            return case_name, city_display

        logger.warning(f"Duplicate '{case_name}' on attempt {attempt + 1}, retrying...")

    city_slug, city_display = get_random_city()
    return f"{year}-ir-{city_slug}", city_display

def generate_ir_briefing(case_name: str, city_display: str) -> str:
    prompt = f"""
    You are posting the opening message to a new incident response Slack channel.

    Channel name: {case_name}
    City: {city_display}

    Write the message in exactly this format:

    IR Case Channel: {case_name}

    City: {city_display}
    [write a fun, quirky 4-6 sentence paragraph about the history and lore of {city_display}. Include a humorous or unusual local legend, historical fact, or quirky detail. Make it entertaining and engaging. DO NOT include a welcome to 'city' at the beginning. DO NOT mention anything about incident response in the welcome message.]

    Return only the message text. No markdown headers. No extra commentary.
    """

    try:
        response = get_client().models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini briefing error: {e}")
        return f"IR Case Channel: {case_name}\n\nCity: {city_display}\n\nNew IR case is now active."

def generate_custom_briefing(case_name: str) -> str:
    """Generate a haiku about the custom case name instead of a city blurb."""
    prompt = f"""
    You are posting the opening message to a new incident response Slack channel.
    The channel was given a custom name: {case_name}

    Write the message in exactly this format:

    IR Case Channel: {case_name}

    [Write a single haiku (3 lines, 5-7-5 syllables) inspired by the name "{case_name}". Make it dramatic, ominous, or darkly humorous — fitting for a security incident.]

    Return only the message text. No markdown headers. No labels. No extra commentary.
    """

    try:
        response = get_client().models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini custom briefing error: {e}")
        return f"IR Case Channel: {case_name}\n\nNew IR case is now active."
