# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import json
import os
import random
import math

# --- Helper for loading static game data ---
def load_json_data(filename):
    """Helper function to load data from a JSON file."""
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: {filename} not found or is improperly formatted.")
        return {}

class StatsCog(commands.Cog, name="Stat Calculations"):
    """Handles all core logic for character stats, IVs, and items."""
    def __init__(self, bot):
        self.bot = bot
        self.characters = load_json_data('characters.json')
        self.items = load_json_data('items.json')

    def _calculate_stats(self, base_stats, individual_ivs, level):
        """Calculates a character's stats based on the Pokémon formula."""
        final_stats = {}
        for stat_name, base_value in base_stats.items():
            iv = individual_ivs.get(stat_name, 0)
            if stat_name.upper() == "HP":
                stat_val = math.floor(((2 * base_value + iv) * level / 100) + level + 10)
            else:
                stat_val = math.floor(((2 * base_value + iv) * level / 100) + 5)
            final_stats[stat_name] = max(1, stat_val)
        return final_stats
        
    def get_character_display_stats(self, character_instance):
        """Gets final stats for a character, including level, IVs, and item boosts."""
        base_char_data = self.characters.get(character_instance['name'])
        if not base_char_data:
            return character_instance.get('stats', {})

        stat_keys = ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']
        base_stats = {k: v for k, v in base_char_data.items() if k in stat_keys}

        calculated_stats = self._calculate_stats(
            base_stats,
            character_instance.get('individual_ivs', {}),
            character_instance.get('level', 1)
        )

        if character_instance.get('equipped_item'):
            item_name_full = character_instance['equipped_item']
            item_type, rarity = item_name_full.rsplit(' ', 1)
            item_data = self.items.get(item_type, {}).get(rarity)
            if item_data:
                stat_to_boost = item_data['stat']
                boost_percent = item_data['boost']
                if stat_to_boost in calculated_stats:
                    boost_amount = math.floor(base_stats[stat_to_boost] * (boost_percent / 100))
                    calculated_stats[stat_to_boost] += boost_amount
        
        return calculated_stats

    def _generate_ivs_with_distribution(self, stats_keys):
        """Generates IVs for stats based on a specific weighted distribution."""
        iv_ranges = [
            (95, 100), (91, 94.99), (88, 90.99), (84, 87.99), 
            (80, 83.99), (1, 5), (5.01, 79.99)
        ]
        weights = [0.1, 0.5, 2, 3, 5, 10, 79.4]
        
        chosen_range = random.choices(iv_ranges, weights=weights, k=1)[0]
        target_iv_percent = random.uniform(chosen_range[0], chosen_range[1])
        
        num_stats = len(stats_keys)
        max_total_iv_points = 31 * num_stats
        total_points_to_distribute = int((target_iv_percent / 100) * max_total_iv_points)
        
        ivs = {stat: 0 for stat in stats_keys}
        points_remaining = total_points_to_distribute
        
        while points_remaining > 0:
            stat_to_increment = random.choice(list(stats_keys))
            if ivs[stat_to_increment] < 31:
                ivs[stat_to_increment] += 1
                points_remaining -= 1
                
        return ivs

    def calculate_damage(self, attacker, defender, attack):
        """Calculates the damage dealt by an attack."""
        base_damage = attack.get('power', 0)
        is_special = attack.get('type') == 'special'
        attack_stat_name = 'SP_ATK' if is_special else 'ATK'
        defense_stat_name = 'SP_DEF' if is_special else 'DEF'
        
        attack_stat = attacker['stats'][attack_stat_name]
        defense_stat = defender['stats'][defense_stat_name]

        is_crit = random.randint(1, 100) <= 5 # 5% crit chance
        damage_multiplier = 1.5 if is_crit else 1.0

        damage = max(1, round((((2 * attacker['level'] / 5 + 2) * base_damage * attack_stat / defense_stat) / 50 + 2) * damage_multiplier))
        
        return {'damage': damage, 'crit': is_crit}

    def _scale_character_to_level(self, base_char, level):
        """Creates a character instance scaled to a specific level (for AI battles)."""
        cz_cog = self.bot.get_cog("Core Gameplay")
        if not cz_cog: return None # Failsafe
        
        instance = cz_cog._create_character_instance(base_char)
        for stat in instance['individual_ivs']:
            instance['individual_ivs'][stat] = random.randint(24, 31)
        
        total_iv_points = sum(instance['individual_ivs'].values())
        max_possible_iv_points = 31 * len(instance['individual_ivs'])
        instance['iv'] = round((total_iv_points / max_possible_iv_points) * 100, 2) if max_possible_iv_points > 0 else 0
        
        stat_keys = ['HP', 'ATK', 'DEF', 'SPD', 'SP_ATK', 'SP_DEF']
        base_stats = {k: v for k, v in base_char.items() if k in stat_keys}
        instance['stats'] = self._calculate_stats(base_stats, instance['individual_ivs'], level)
        
        instance['level'] = level
        return instance

async def setup(bot):
    await bot.add_cog(StatsCog(bot))

