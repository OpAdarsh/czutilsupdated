import sqlite3
import json
from collections import defaultdict
import time

DATABASE_FILE = 'bot_database.db'

def update_db_schema(cursor):
    """Checks for and applies necessary database schema updates."""
    try:
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'last_pull_time' not in columns:
            print("Updating database schema: Adding 'last_pull_time' column...")
            cursor.execute("ALTER TABLE players ADD COLUMN last_pull_time REAL NOT NULL DEFAULT 0")
            print("Schema update complete.")
            
        if 'rank_points' not in columns:
            print("Updating database schema: Adding 'rank_points' column...")
            cursor.execute("ALTER TABLE players ADD COLUMN rank_points INTEGER NOT NULL DEFAULT 0")
            print("Schema update complete.")
    except sqlite3.Error as e:
        print(f"Schema update error (likely column already exists): {e}")

def init_db():
    """Initializes the database and creates/updates tables as needed."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # --- Players Table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 500,
            characters TEXT NOT NULL DEFAULT '{}',
            inventory TEXT NOT NULL DEFAULT '{}',
            team TEXT NOT NULL DEFAULT '{}',
            latest_pull_id INTEGER,
            selected_character_id INTEGER,
            next_character_id INTEGER NOT NULL DEFAULT 1,
            last_xp_gain_time REAL NOT NULL DEFAULT 0,
            last_daily_date TEXT,
            daily_streak INTEGER NOT NULL DEFAULT 0,
            rules_accepted INTEGER NOT NULL DEFAULT 0,
            last_pull_time REAL NOT NULL DEFAULT 0,
            rank_points INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    # Run schema update after table creation
    update_db_schema(cursor)
    
    # --- Market Table ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market (
            listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            character_data TEXT NOT NULL,
            listed_at REAL NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Player Data Functions ---

def get_player(user_id):
    """Fetches a player's data, creating a new entry if one doesn't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    # Use a Row factory to access columns by name
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    player_row = cursor.fetchone()
    
    if player_row:
        player_data = {
            "user_id": player_row['user_id'], 
            "coins": player_row['coins'],
            "characters": json.loads(player_row['characters']),
            "inventory": defaultdict(int, json.loads(player_row['inventory'])),
            "team": json.loads(player_row['team']), 
            "latest_pull_id": player_row['latest_pull_id'],
            "selected_character_id": player_row['selected_character_id'], 
            "next_character_id": player_row['next_character_id'],
            "last_xp_gain_time": player_row['last_xp_gain_time'], 
            "last_daily_date": player_row['last_daily_date'],
            "daily_streak": player_row['daily_streak'], 
            "rules_accepted": player_row['rules_accepted'],
            "last_pull_time": player_row['last_pull_time'],
            "rank_points": player_row['rank_points']
        }
        player_data['characters'] = {int(k): v for k, v in player_data['characters'].items()}
    else:
        cursor.execute("INSERT INTO players (user_id) VALUES (?)", (user_id,))
        conn.commit()
        player_data = {
            "user_id": user_id, "coins": 500, "characters": {},
            "inventory": defaultdict(int), "team": {'1': None, '2': None, '3': None}, 
            "latest_pull_id": None, "selected_character_id": None, 
            "next_character_id": 1, "last_xp_gain_time": 0, 
            "last_daily_date": None, "daily_streak": 0, "rules_accepted": 0,
            "last_pull_time": 0, "rank_points": 0
        }
        
    conn.close()
    return player_data

def update_player(user_id, data):
    """Updates a player's data in the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    data['characters'] = {str(k): v for k, v in data.get("characters", {}).items()}
    characters_str = json.dumps(data.get("characters", {}))
    inventory_dict = dict(data.get("inventory", defaultdict(int)))
    inventory_str = json.dumps(inventory_dict)
    team_str = json.dumps(data.get("team", {'1': None, '2': None, '3': None}))
    
    cursor.execute('''
        UPDATE players
        SET coins = ?, characters = ?, inventory = ?, team = ?, latest_pull_id = ?,
            selected_character_id = ?, next_character_id = ?, last_xp_gain_time = ?,
            last_daily_date = ?, daily_streak = ?, rules_accepted = ?, last_pull_time = ?, rank_points = ?
        WHERE user_id = ?
    ''', (
        data.get("coins", 500), characters_str, inventory_str, team_str,
        data.get("latest_pull_id"), data.get("selected_character_id"),
        data.get("next_character_id", 1), data.get("last_xp_gain_time", 0),
        data.get("last_daily_date"), data.get("daily_streak", 0),
        data.get("rules_accepted", 0), data.get("last_pull_time", 0), data.get("rank_points", 0),
        user_id
    ))
    
    conn.commit()
    conn.close()

def reset_player(user_id):
    """Resets a single player's data to the default state."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO players (user_id) VALUES (?)", (user_id,))
    cursor.execute('''
        UPDATE players
        SET coins = 500, characters = '{}', inventory = '{}', team = '{}', 
            latest_pull_id = NULL, selected_character_id = NULL, next_character_id = 1, 
            last_xp_gain_time = 0, last_daily_date = NULL, daily_streak = 0, last_pull_time = 0, rank_points = 0
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

def reset_all_players():
    """Drops and re-initializes all player-related tables."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS players")
    cursor.execute("DROP TABLE IF EXISTS market")
    conn.commit()
    conn.close()
    init_db()

# --- Market Data Functions ---
def add_market_listing(seller_id, price, character_data):
    """Adds a new character listing to the market."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    character_json = json.dumps(character_data)
    listed_at = time.time()
    
    cursor.execute(
        "INSERT INTO market (seller_id, price, character_data, listed_at) VALUES (?, ?, ?, ?)",
        (seller_id, price, character_json, listed_at)
    )
    listing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return listing_id

def remove_market_listing(listing_id):
    """Removes a character listing from the market."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM market WHERE listing_id = ?", (listing_id,))
    conn.commit()
    conn.close()

def get_market_listing(listing_id):
    """Fetches a single market listing by its ID."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM market WHERE listing_id = ?", (listing_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None
        
    return {
        "listing_id": row[0],
        "seller_id": row[1],
        "price": row[2],
        "character_data": json.loads(row[3]),
        "listed_at": row[4]
    }

def get_all_market_listings():
    """Fetches all active listings from the market."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM market ORDER BY listed_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    listings = []
    for row in rows:
        listings.append({
            "listing_id": row[0],
            "seller_id": row[1],
            "price": row[2],
            "character_data": json.loads(row[3]),
            "listed_at": row[4]
        })
    return listings

def get_leaderboard(limit=10):
    """Fetches the top players by rank points for the leaderboard."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, rank_points 
        FROM players 
        WHERE rank_points > 0 
        ORDER BY rank_points DESC 
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    leaderboard = []
    for row in rows:
        leaderboard.append({
            "user_id": row['user_id'],
            "rank_points": row['rank_points']
        })
    
    return leaderboard
