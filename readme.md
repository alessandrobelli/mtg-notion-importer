# 🌟 Magic: The Gathering Card Importer for Notion 🌟

This script imports Magic: The Gathering cards from the Scryfall API to a Notion database. It creates or updates pages for each card, adding relevant card information and images. 

## 📦 Requirements

- Python 3.6+
- `python-dotenv`
- `notion-client`
- `colorama`
- `tqdm`
- `requests`

## 🎯 Features

- Imports cards from all available sets in Scryfall API
- Updates existing card pages in the Notion database
- Creates new card pages if they don't exist
- Adds relevant card information, such as name, type, mana cost, set, rarity, and more
- Extracts and displays card keywords
- Handles images and adds them to the card page
- Retries API calls in case of failures

## 📝 How to Use

1. Install the required packages using pip:

```bash
pip install python-dotenv notion-client colorama tqdm requests
```

2. Create a .env file in the same directory as the script and add your Notion API key and the database ID:

```makefile
NOTION_API_KEY=<your_notion_api_key>
DATABASE_ID=<your_database_id>
```

3. Run the script:

```bash
python <script_name>.py
```

The script will fetch all available sets and cards from the Scryfall API and update or create card pages in the specified Notion database.

## 📖 Code Overview

The code is organized into several functions:

- update_or_create_page(): Updates or creates a card page in the Notion database
- create_table_block(): Creates a table block for a card page
- format_legalities(): Formats card legalities for display in the Notion database
- get_card_by_scryfall_id(): Searches for a card in the Notion database using its Scryfall ID
- extract_keywords(): Extracts card keywords from the card's oracle text
- import_cards(): Main function that imports cards from the Scryfall API to the Notion database

### 🚀 Start Importing Cards

Run the script to start importing cards to your Notion database. The script will display a progress bar for each set as it processes the cards.

## Notion Database Structure for Magic: The Gathering Collection

Below is the structure of the Notion database for managing your Magic: The Gathering card collection:

| Column Name      | Column Type   | Content                                                                                         |
|------------------|---------------|-------------------------------------------------------------------------------------------------|
| Name             | Title         | card.get("name", "")                                                                            |
| Type             | Multi-select  | [t for t in card.get("type_line", "").split(" // ")]                                           |
| Mana Cost        | Rich Text     | card.get("mana_cost", "")                                                                       |
| Set              | Multi-select  | card.get("set_name", "")                                                                        |
| Rarity           | Select        | card.get("rarity", "").capitalize()                                                             |
| Text             | Rich Text     | card.get("oracle_text", "")                                                                     |
| Flavor Text      | Rich Text     | card.get("flavor_text", "")                                                                     |
| Power            | Rich Text     | card.get("power", "")                                                                           |
| Toughness        | Rich Text     | card.get("toughness", "")                                                                       |
| Power/Toughness  | Rich Text     | f"{card.get('power', '')}/{card.get('toughness', '')}"                                         |
| Loyalty          | Number        | int(card.get("loyalty", 0)) if card.get("loyalty") else None                                   |
| Legalities       | Multi-select  | format_legalities(card.get("legalities", {}))                                                   |
| Artist           | Rich Text     | card.get("artist", "")                                                                          |
| Keywords         | Multi-select  | extract_keywords(card.get("oracle_text", ""))                                                   |
| Scryfall ID      | Rich Text     | card.get("id", "")