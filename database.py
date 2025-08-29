import sqlite3
import json
from collections import defaultdict

DATABASE_FILE = 'bot_database.db'

def init_db():
    """Initializes the database and creates/updates tables as needed."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Create players table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 500,
            characters TEXT NOT NULL DEFAULT '{}',
            inventory TEXT NOT NULL DEFAULT '{}',
            team TEXT NOT NULL DEFAULT '[]',
            latest_pull_id INTEGER,
            selected_character_id INTEGER,
            next_character_id INTEGER NOT NULL DEFAULT 1,
            last_xp_gain_time REAL NOT NULL DEFAULT 0,
            last_daily_date TEXT,
            daily_streak INTEGER NOT NULL DEFAULT 0,
            rules_accepted INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def get_player(user_id):
    """Fetches a player's data from the database, creating a new entry if needed."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    player_row = cursor.fetchone()
    
    if player_row:
        player_data = {
            "user_id": player_row[0], "coins": player_row[1],
            "characters": json.loads(player_row[2]),
            "inventory": defaultdict(int, json.loads(player_row[3])),
            "team": json.loads(player_row[4]), "latest_pull_id": player_row[5],
            "selected_character_id": player_row[6], "next_character_id": player_row[7],
            "last_xp_gain_time": player_row[8], "last_daily_date": player_row[9],
            "daily_streak": player_row[10], "rules_accepted": player_row[11]
        }
        player_data['characters'] = {int(k): v for k, v in player_data['characters'].items()}
    else:
        cursor.execute("INSERT INTO players (user_id) VALUES (?)", (user_id,))
        conn.commit()
        player_data = {
            "user_id": user_id, "coins": 500, "characters": {},
            "inventory": defaultdict(int), "team": [], "latest_pull_id": None,
            "selected_character_id": None, "next_character_id": 1,
            "last_xp_gain_time": 0, "last_daily_date": None,
            "daily_streak": 0, "rules_accepted": 0
        }
        
    conn.close()
    return player_data

def update_player(user_id, data):
    """Updates a player's data in the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Ensure all character IDs are strings for JSON compatibility
    data['characters'] = {str(k): v for k, v in data.get("characters", {}).items()}
    characters_str = json.dumps(data.get("characters", {}))
    inventory_dict = dict(data.get("inventory", {}))
    inventory_str = json.dumps(inventory_dict)
    team_str = json.dumps(data.get("team", []))
    
    cursor.execute('''
        UPDATE players
        SET coins = ?, characters = ?, inventory = ?, team = ?, latest_pull_id = ?,
            selected_character_id = ?, next_character_id = ?, last_xp_gain_time = ?,
            last_daily_date = ?, daily_streak = ?, rules_accepted = ?
        WHERE user_id = ?
    ''', (
        data.get("coins", 500), characters_str, inventory_str, team_str,
        data.get("latest_pull_id"), data.get("selected_character_id"),
        data.get("next_character_id", 1), data.get("last_xp_gain_time", 0),
        data.get("last_daily_date"), data.get("daily_streak", 0),
        data.get("rules_accepted", 0), user_id
    ))
    
    conn.commit()
    conn.close()

def reset_player(user_id):
    """Resets a single player's data to the default state."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    get_player(user_id) # Ensure player exists
    cursor.execute('''
        UPDATE players
        SET coins = 500, characters = '{}', inventory = '{}', team = '[]', 
            latest_pull_id = NULL, selected_character_id = NULL, next_character_id = 1, 
            last_xp_gain_time = 0, last_daily_date = NULL, daily_streak = 0, rules_accepted = 0
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

def reset_all_players():
    """Drops the players table and re-initializes it, wiping all data."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS players")
    conn.commit()
    conn.close()
    init_db()

