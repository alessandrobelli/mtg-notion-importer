import os
from httpx import TimeoutException
import requests
from notion_client import Client
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image
from tqdm import tqdm
from urllib.parse import urlparse
from colorama import Fore, Style, init
import logging
import os
import time
from requests.exceptions import HTTPError
import notion_client.errors
import json
from tenacity import retry, stop_after_attempt, wait_exponential

# Create the logs directory if it doesn't exist
if not os.path.exists("logs"):
    os.makedirs("logs")

# Configure logging
logging.basicConfig(filename="logs/logfile.txt", level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

init(autoreset=True)

tqdm_color = f"{Fore.CYAN}{Style.BRIGHT}"
tqdm_settings = {
    "bar_format": f"{tqdm_color}{{desc}}: {{percentage:3.0f}}%|{{bar:10}}| {{n_fmt}}/{{total_fmt}}",
    "colour": "cyan",
}


load_dotenv()
total_cards = 0
current_card = 0

notion = Client(auth=os.environ["NOTION_API_KEY"],notion_version="2025-09-03")


DB_ID = os.environ["DATABASE_ID"]  # This must be the Notion database UUID from the URL
db_obj = notion.databases.retrieve(database_id=DB_ID)  # OK with the new API [web:24]
DATA_SOURCE_ID = db_obj["data_sources"][0]["id"]       # Use for queries only [web:49]

# Add this function to get the most recent card from your Notion database
def get_most_recent_card():
    res = notion.data_sources.query(
        data_source_id=DATA_SOURCE_ID,
        sorts=[{"property": "updated_at", "direction": "descending"}],
    )  # note: “sorts”, plural [web:49][web:21]
    results = res.get("results", [])
    return results[0] if results else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def update_or_create_page(card, existing_page=None):

    # The same code as before to prepare the new_page and base_page_update/create
    image_uris = card.get("image_uris", {})
    max_retries = 3
    retry_interval = 5  # seconds
    type_line = card.get("type_line", "").split(" // ")
    new_page = {
        "Name": {"title": [{"text": {"content": card.get("name", "")}}]},
        "Type": {"multi_select": [{"name": t} for t in type_line if t]},  # Check if t is not empty
        "Mana Cost": {"rich_text": [{"text": {"content": card.get("mana_cost", "")}}]},
        "Set": {"multi_select": [{"name": card.get("set_name", "").replace(',', ' ')}]},
        "Rarity": {"select": {"name": card.get("rarity", "").capitalize()}},
        "Text": {"rich_text": [{"text": {"content": card.get("oracle_text", "")}}]},
        "Flavor Text": {"rich_text": [{"text": {"content": card.get("flavor_text", "")}}]},
        "Power": {"rich_text": [{"text": {"content": card.get("power", "")}}]},
        "Toughness": {"rich_text": [{"text": {"content": card.get("toughness", "")}}]},
        "Power/Toughness": {"rich_text": [{"text": {"content": f"{card.get('power', '')}/{card.get('toughness', '')}" if card.get('power', '').replace('.', '', 1).isdigit() and card.get('toughness', '').replace('.', '', 1).isdigit() else ""}}]},
        "Loyalty": {"rich_text": [{"text": {"content": f"{card.get('loyalty', '')}" if card.get('loyalty', '').replace('.', '', 1).isdigit() else ""}}]},
        "Legalities": {"multi_select": format_legalities(card.get("legalities", {}))},
        "Artist": {"rich_text": [{"text": {"content": card.get("artist", "")}}]},
        "Keywords": {"multi_select": extract_keywords(card.get("oracle_text", ""))},
        "Scryfall ID": {"rich_text": [{"text": {"content": card.get("id", "")}}]},
    }

    if image_uris and "png" in image_uris:
        new_page["Illustration"] = {
            "files": [{"name": card.get("name", ""), "external": {"url": image_uris["png"]}}]
        }
    if existing_page:
        for attempt in range(max_retries):
            try:
                base_page_update = {
                    "properties": new_page,
                }

                if "png" in image_uris:
                    base_page_update["cover"] = {"type": "external",
                                                 "external": {"url": image_uris["png"]}}

                if "small" in image_uris:
                    base_page_update["icon"] = {"type": "external",
                                                "external": {"url": image_uris["small"]}}

                notion.pages.update(existing_page["id"], **base_page_update)

                # Retrieve the child blocks of the existing page
                child_blocks = notion.blocks.children.list(existing_page["id"])

                # Find the table block and delete it
                for block in child_blocks["results"]:
                    if block["type"] == "table":
                        notion.blocks.delete(block["id"])
                        break

                # Create a new table block and append it to the existing page's content
                created_table_block = create_table_block(card)
                notion.blocks.children.append(
                    existing_page["id"], children=[created_table_block])

                break  # Break the loop if the API call is successful
            except (HTTPError, TimeoutException) as e:
                if (isinstance(e, HTTPError) and e.response.status_code == 502 or isinstance(e, TimeoutException)) and attempt < max_retries - 1:
                        time.sleep(retry_interval)
                        logging.warning(
                            f"Error updating card '{card['name']}': {e}. Retrying...")
                else:
                    raise e
    else:
        for attempt in range(max_retries):
            try:
                base_page_create = {
                    "parent": {"database_id": os.environ["DATABASE_ID"]},
                    "properties": new_page,
                }

                if "png" in image_uris:
                    base_page_create["cover"] = {"type": "external",
                                                 "external": {"url": image_uris["png"]}}

                if "small" in image_uris:
                    base_page_create["icon"] = {"type": "external",
                                                "external": {"url": image_uris["small"]}}

                created_page = notion.pages.create(**base_page_create)

                # Generate the table and add it as a child block inside the page content
                table_block = create_table_block(card)
                notion.blocks.children.append(
                    created_page["id"], children=[table_block])

                break  # Break the loop if the API call is successful
            except (HTTPError, TimeoutException) as e:
                if (isinstance(e, HTTPError) and e.response.status_code == 502 or isinstance(e, TimeoutException)) and attempt < max_retries - 1:
                    time.sleep(retry_interval)
                    logging.warning(
                        f"Error creating card '{card['name']}': {e}. Retrying...")
                else:
                    raise e

    return


def create_table_block(card):
    preview_data = card.get("preview", {})
    prices_data = card.get("prices", {})
    related_uris_data = card.get("related_uris", {})
    purchase_uris_data = card.get("purchase_uris", {})

    table_data = {}
    table_data.update(preview_data)
    table_data.update(prices_data)
    table_data.update(related_uris_data)
    table_data.update(purchase_uris_data)

    def is_url(value):
        parsed = urlparse(value)
        return bool(parsed.scheme and parsed.netloc)

    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 2,
            "has_column_header": False,
            "has_row_header": False,
            "children": [
                {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"text": {"content": key}}],
                            [{"text": {"content": str(value), "link": {
                                "url": value} if is_url(str(value)) else None}}],
                        ]
                    }
                }
                for key, value in table_data.items()
            ],
        },
    }

    return table_block


def format_legalities(legalities):
    formatted_legalities = []
    for k, v in legalities.items():
        if v != 'not_legal':
            formatted_legalities.append({"name": f"{k}: {v}"})
    return formatted_legalities


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def get_card_by_scryfall_id(scryfall_id):
    retries = 3
    for i in range(retries):
        try:
            existing_card = notion.data_sources.query(
                **{
                    "data_source_id": DATA_SOURCE_ID,
                    "filter": {
                        "property": "Scryfall ID",
                        "rich_text": {
                            "equals": scryfall_id
                        }
                    }
                }
            ).get("results")
            return existing_card[0] if existing_card else None
        except (notion_client.errors.HTTPResponseError, TimeoutException) as e:
            if (isinstance(e, notion_client.errors.HTTPResponseError) and e.status_code == 502 or
                    isinstance(e, TimeoutException)) and i < retries - 1:
                time.sleep(2**(i+1))  # Exponential backoff
                continue
            else:
                raise e


def extract_keywords(oracle_text):
    mtg_keywords = [
        "Deathtouch",
        "Defender",
        "Double strike",
        "Equip",
        "First strike",
        "Flash",
        "Flying",
        "Haste",
        "Hexproof",
        "Indestructible",
        "Intimidate",
        "Lifelink",
        "Menace",
        "Protection",
        "Reach",
        "Shroud",
        "Trample",
        "Vigilance",
        "Ward",
        "Adapt",
        "Affinity",
        "Aftermath",
        "Amass",
        "Annihilator",
        "Ascend",
        "Awaken",
        "Battalion",
        "Bestow",
        "Bloodthirst",
        "Cascade",
        "Changeling",
        "Cipher",
        "Convoke",
        "Crew",
        "Dash",
        "Delve",
        "Devour",
        "Dredge",
        "Evoke",
        "Exalted",
        "Explore",
        "Extort",
        "Fabricate",
        "Fading",
        "Fateful hour",
        "Ferocious",
        "Flicker",
        "Forecast",
        "Fortify",
        "Graft",
        "Gravestorm",
        "Heroic",
        "Improvise",
        "Ingest",
        "Kicker",
        "Landfall",
        "Level up",
        "Madness",
        "Mentor",
        "Metalcraft",
        "Miracle",
        "Morph",
        "Mutate",
        "Ninjutsu",
        "Persist",
        "Proliferate",
        "Raid",
        "Rally",
        "Rampage",
        "Rebound",
        "Reinforce",
        "Renown",
        "Replicate",
        "Retrace",
        "Riot",
        "Scavenge",
        "Scry",
        "Shadow",
        "Skulk",
        "Soulbond",
        "Splice",
        "Storm",
        "Strive",
        "Suspend",
        "Totem armor",
        "Transfigure",
        "Transmute",
        "Undying",
        "Unearth",
        "Vanishing",
        "Vigor",
        "Wither"
    ]

    found_keywords = [kw for kw in mtg_keywords if kw.lower()
                      in oracle_text.lower()]
    return [{"name": kw} for kw in found_keywords]


def import_cards():
    global total_cards
    notion = Client(auth=os.environ["NOTION_API_KEY"],notion_version="2025-09-03",)

    # Prompt the user to choose whether to continue or start from the beginning
    user_input = input(
        "Do you want to continue from the last card fetched in Notion? (yes/no): ").lower()
    continue_from_last = user_input == "yes" or user_input == "y"


    sets_url = "https://api.scryfall.com/sets"
    response = requests.get(sets_url)

    if response.status_code == 200:
        sets = response.json()["data"]

        if continue_from_last:
            most_recent_card = get_most_recent_card()
            
            if most_recent_card:
                # Get the set of the most recent card
                most_recent_set = most_recent_card["properties"]["Set"]["multi_select"][0]["name"]
                
                # Remove sets from the list until you find the most recent card's set
                while sets and sets[0]["name"] != most_recent_set:
                    sets.pop(0)


        for mtg_set in sets:
            set_code = mtg_set["code"]
            logging.info(f"Fetching cards from set: {mtg_set['name']}")

            has_more = True
            search_url = f"https://api.scryfall.com/cards/search?order=set&q=e:{set_code}&unique=prints"

            while has_more:
                response = requests.get(search_url)

                if response.status_code == 200:
                    cards = response.json()["data"]
                    has_more = response.json()["has_more"]
                    search_url = response.json(
                    )["next_page"] if has_more else None
                    total_cards = len(cards)

                    for card in tqdm(cards, desc=f"Processing cards for {mtg_set['name']}", **tqdm_settings):
                        existing_card = get_card_by_scryfall_id(card["id"])

                        if existing_card:
                            update_or_create_page(
                                card, existing_page=existing_card)
                        else:
                            update_or_create_page(card)

                else:
                    logging.info(
                        f"Failed to fetch cards from set {set_code}. Status code: {response.status_code}")
                    break
    else:
        logging.info(
            f"Failed to fetch sets from Scryfall API. Status code: {response.status_code}")

import_cards()
