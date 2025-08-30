# webmonitor.py
from flask import Flask, jsonify
import requests
import os
from discord.ext import commands

app = Flask(__name__)

my_secret = os.environ['YOUR_SECRET_Uptimerobot_API_KEY']  # Replace with your actual secret key name
UptimeRobot_API_KEY = my_secret 
UptimeRobot_URL = 'https://api.uptimerobot.com/v2/getMonitors'

@app.route('/monitor_status', methods=['GET'])
def monitor_status():
    params = {'api_key': UptimeRobot_API_KEY, 'format': 'json'}
    response = requests.post(UptimeRobot_URL, data=params)
    if response.status_code == 200:
        data = response.json()
        return jsonify(data['monitors'])
    else:
        return jsonify({'error': 'Failed to fetch monitor status'}), response.status_code

class Webmonitor(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.app = app  # Attach the Flask app to the cog

    @commands.command(name="status")
    async def get_status(self, ctx):
        """Example command to show monitor status"""
        await ctx.send("Fetching monitor status...")
        try:
            response = requests.get("http://0.0.0.0:5000/monitor_status")  
            response.raise_for_status()  
            data = response.json()
            await ctx.send(f"Monitor Status: {data}")  
        except requests.exceptions.RequestException as e:
            await ctx.send(f"Error fetching monitor status: {e}")

async def setup(bot):
    await bot.add_cog(Webmonitor(bot))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Bind to 0.0.0.0 to allow external access
