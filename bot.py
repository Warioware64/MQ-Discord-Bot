import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
from datetime import datetime
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────
PREFIX = "!"
DB_FILE = "db.json"
FC_REGEX = re.compile(r"^\d{4}-\d{4}-\d{4}$")

GAMES = {
    "mq1": {
        "name": "Magician's Quest: Mysterious Times",
        "short": "MQ1",
        "wiimmfi": "https://wiimmfi.de/stats/game/nameneverds",
        "emoji": "🧙",
    },
    "mq2": {
        "name": "Tongari Boushi to Mahou no Omise",
        "short": "MQ2",
        "wiimmfi": "https://wiimmfi.de/stats/game/@bmo",
        "emoji": "🏪",
    },
    "mq3": {
        "name": "Tongari Boushi to Oshare na Mahou Tsukai",
        "short": "MQ3",
        "wiimmfi": "https://wiimmfi.de/stats/game/tonosmahds",
        "emoji": "👗",
    },
    "mq4": {
        "name": "Tongari Boushi to Mahou no Machi",
        "short": "MQ4",
        "wiimmfi": None,  # 3DS — no Wiimmfi support
        "emoji": "🏙️",
    },
}

GAME_CHOICES = [
    app_commands.Choice(name=f"{v['short']} — {v['name']}", value=k)
    for k, v in GAMES.items()
]

# ── Database helpers ─────────────────────────────────────────────────────────
db_lock = asyncio.Lock()

def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def save_db(data: dict):
    async with db_lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def get_or_create_profile(db: dict, user_id: str, user: discord.User | discord.Member) -> dict:
    if user_id not in db:
        db[user_id] = {
            "player_name": None,
            "school_name": None,
            "friend_codes": {},
            "username": str(user),
            "registered_at": datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC"),
        }
    return db[user_id]

# ── Embed builders ───────────────────────────────────────────────────────────
def build_profile_embed(user: discord.User | discord.Member, profile: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🧙 Magician's Quest — Player Profile",
        color=0x7B4FBF,
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)

    embed.add_field(
        name="Player Name",
        value=profile.get("player_name") or "*Not set*",
        inline=True,
    )
    embed.add_field(
        name="School Name",
        value=profile.get("school_name") or "*Not set*",
        inline=True,
    )

    embed.add_field(name="\u200b", value="**Friend Codes**", inline=False)

    fcs = profile.get("friend_codes", {})
    for key, game in GAMES.items():
        fc = fcs.get(key)
        if game["wiimmfi"]:
            suffix = f" — [Wiimmfi]({game['wiimmfi']})"
        else:
            suffix = " — *(3DS, no Wiimmfi)*"
        value = f"`{fc}`{suffix}" if fc else f"*Not registered*{suffix}"
        embed.add_field(
            name=f"{game['emoji']} {game['short']}",
            value=value,
            inline=False,
        )

    embed.set_footer(text=f"Registered on {profile['registered_at']}")
    return embed

def build_list_embed(db: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🧙 Magician's Quest — Player List",
        color=0x7B4FBF,
        description=f"{len(db)} registered player(s)",
    )
    for user_id, profile in db.items():
        member = guild.get_member(int(user_id))
        discord_name = member.display_name if member else f"Unknown ({user_id})"
        player_name = profile.get("player_name") or "*No name*"
        school_name = profile.get("school_name") or "*No school*"

        fc_lines = []
        for key, game in GAMES.items():
            fc = profile.get("friend_codes", {}).get(key)
            if fc:
                fc_lines.append(f"{game['emoji']} `{fc}`")

        fc_text = "\n".join(fc_lines) if fc_lines else "*No friend codes*"
        embed.add_field(
            name=f"{discord_name} — {player_name} ({school_name})",
            value=fc_text,
            inline=False,
        )

    if not db:
        embed.description = "No players registered yet."
    return embed

# ── Validation ───────────────────────────────────────────────────────────────
def validate_fc(fc: str) -> bool:
    return bool(FC_REGEX.match(fc.strip()))

def format_fc(fc: str) -> str:
    digits = re.sub(r"\D", "", fc)
    if len(digits) == 12:
        return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"
    return fc.strip()

# ── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print("   Slash commands synced.")

# ── /setprofile ──────────────────────────────────────────────────────────────

@tree.command(name="setprofile", description="Set your player name and school name.")
@app_commands.describe(
    player_name="Your in-game player name",
    school_name="Your school name",
)
async def slash_setprofile(interaction: discord.Interaction, player_name: str, school_name: str):
    db = load_db()
    profile = get_or_create_profile(db, str(interaction.user.id), interaction.user)
    profile["player_name"] = player_name
    profile["school_name"] = school_name
    profile["username"] = str(interaction.user)
    db[str(interaction.user.id)] = profile
    await save_db(db)
    embed = build_profile_embed(interaction.user, profile)
    await interaction.response.send_message("✅ Profile updated!", embed=embed)

@bot.command(name="setprofile", help="Set your player name and school. Ex: !setprofile PlayerName SchoolName")
async def prefix_setprofile(ctx: commands.Context, player_name: str = None, school_name: str = None):
    if not player_name or not school_name:
        await ctx.reply("❌ Usage: `!setprofile <PlayerName> <SchoolName>`")
        return
    db = load_db()
    profile = get_or_create_profile(db, str(ctx.author.id), ctx.author)
    profile["player_name"] = player_name
    profile["school_name"] = school_name
    profile["username"] = str(ctx.author)
    db[str(ctx.author.id)] = profile
    await save_db(db)
    embed = build_profile_embed(ctx.author, profile)
    await ctx.reply("✅ Profile updated!", embed=embed)

# ── /addfc ───────────────────────────────────────────────────────────────────

@tree.command(name="addfc", description="Add your Friend Code for a specific game.")
@app_commands.describe(
    game="The game you want to register a Friend Code for",
    fc="Your Friend Code (format: XXXX-XXXX-XXXX)",
)
@app_commands.choices(game=GAME_CHOICES)
async def slash_addfc(interaction: discord.Interaction, game: app_commands.Choice[str], fc: str):
    fc = format_fc(fc)
    if not validate_fc(fc):
        await interaction.response.send_message("❌ Invalid format. Please use `XXXX-XXXX-XXXX`.", ephemeral=True)
        return
    db = load_db()
    profile = get_or_create_profile(db, str(interaction.user.id), interaction.user)
    profile["friend_codes"][game.value] = fc
    db[str(interaction.user.id)] = profile
    await save_db(db)
    game_info = GAMES[game.value]
    await interaction.response.send_message(
        f"✅ Friend Code `{fc}` registered for **{game_info['short']} — {game_info['name']}**!"
    )

@bot.command(name="addfc", help="Add a Friend Code for a game. Ex: !addfc mq1 1234-5678-9012")
async def prefix_addfc(ctx: commands.Context, game: str = None, fc: str = None):
    if not game or not fc:
        games_list = ", ".join(f"`{k}`" for k in GAMES)
        await ctx.reply(f"❌ Usage: `!addfc <game> <XXXX-XXXX-XXXX>`\nGames: {games_list}")
        return
    game = game.lower()
    if game not in GAMES:
        games_list = ", ".join(f"`{k}`" for k in GAMES)
        await ctx.reply(f"❌ Unknown game. Available: {games_list}")
        return
    fc = format_fc(fc)
    if not validate_fc(fc):
        await ctx.reply("❌ Invalid format. Please use `XXXX-XXXX-XXXX`.")
        return
    db = load_db()
    profile = get_or_create_profile(db, str(ctx.author.id), ctx.author)
    profile["friend_codes"][game] = fc
    db[str(ctx.author.id)] = profile
    await save_db(db)
    game_info = GAMES[game]
    await ctx.reply(f"✅ Friend Code `{fc}` registered for **{game_info['short']} — {game_info['name']}**!")

# ── /profile ─────────────────────────────────────────────────────────────────

@tree.command(name="profile", description="Display a player's profile.")
@app_commands.describe(member="The player whose profile you want to see (optional)")
async def slash_profile(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    db = load_db()
    profile = db.get(str(target.id))
    if not profile:
        msg = "❌ You haven't set up a profile yet. Use `/setprofile` to get started." if target == interaction.user \
            else f"❌ {target.display_name} hasn't set up a profile yet."
        await interaction.response.send_message(msg, ephemeral=True)
        return
    embed = build_profile_embed(target, profile)
    await interaction.response.send_message(embed=embed)

@bot.command(name="profile", help="Display a player's profile. Ex: !profile or !profile @user")
async def prefix_profile(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    db = load_db()
    profile = db.get(str(target.id))
    if not profile:
        msg = "❌ You haven't set up a profile yet. Use `!setprofile <PlayerName> <SchoolName>`." if target == ctx.author \
            else f"❌ {target.display_name} hasn't set up a profile yet."
        await ctx.reply(msg)
        return
    embed = build_profile_embed(target, profile)
    await ctx.reply(embed=embed)

# ── /lookup ──────────────────────────────────────────────────────────────────

@tree.command(name="lookup", description="List all registered players.")
async def slash_lookup(interaction: discord.Interaction):
    db = load_db()
    embed = build_list_embed(db, interaction.guild)
    await interaction.response.send_message(embed=embed)

@bot.command(name="lookup", help="List all registered players.")
async def prefix_lookup(ctx: commands.Context):
    db = load_db()
    embed = build_list_embed(db, ctx.guild)
    await ctx.reply(embed=embed)

# ── /removefc ────────────────────────────────────────────────────────────────

@tree.command(name="removefc", description="Remove your Friend Code for a specific game.")
@app_commands.describe(game="The game whose Friend Code you want to remove")
@app_commands.choices(game=GAME_CHOICES)
async def slash_removefc(interaction: discord.Interaction, game: app_commands.Choice[str]):
    db = load_db()
    profile = db.get(str(interaction.user.id))
    if not profile or game.value not in profile.get("friend_codes", {}):
        await interaction.response.send_message(
            f"❌ You don't have a Friend Code registered for **{GAMES[game.value]['short']}**.", ephemeral=True
        )
        return
    del profile["friend_codes"][game.value]
    await save_db(db)
    await interaction.response.send_message(
        f"✅ Friend Code removed for **{GAMES[game.value]['short']} — {GAMES[game.value]['name']}**.", ephemeral=True
    )

@bot.command(name="removefc", help="Remove your Friend Code for a game. Ex: !removefc mq1")
async def prefix_removefc(ctx: commands.Context, game: str = None):
    if not game:
        games_list = ", ".join(f"`{k}`" for k in GAMES)
        await ctx.reply(f"❌ Usage: `!removefc <game>`\nGames: {games_list}")
        return
    game = game.lower()
    if game not in GAMES:
        games_list = ", ".join(f"`{k}`" for k in GAMES)
        await ctx.reply(f"❌ Unknown game. Available: {games_list}")
        return
    db = load_db()
    profile = db.get(str(ctx.author.id))
    if not profile or game not in profile.get("friend_codes", {}):
        await ctx.reply(f"❌ You don't have a Friend Code registered for **{GAMES[game]['short']}**.")
        return
    del profile["friend_codes"][game]
    await save_db(db)
    await ctx.reply(f"✅ Friend Code removed for **{GAMES[game]['short']} — {GAMES[game]['name']}**.")

# ── /unregister ──────────────────────────────────────────────────────────────

@tree.command(name="unregister", description="Delete your entire profile.")
async def slash_unregister(interaction: discord.Interaction):
    db = load_db()
    if str(interaction.user.id) not in db:
        await interaction.response.send_message("❌ You don't have a profile to delete.", ephemeral=True)
        return
    del db[str(interaction.user.id)]
    await save_db(db)
    await interaction.response.send_message("✅ Your profile has been deleted.", ephemeral=True)

@bot.command(name="unregister", help="Delete your entire profile.")
async def prefix_unregister(ctx: commands.Context):
    db = load_db()
    if str(ctx.author.id) not in db:
        await ctx.reply("❌ You don't have a profile to delete.")
        return
    del db[str(ctx.author.id)]
    await save_db(db)
    await ctx.reply("✅ Your profile has been deleted.")

# ── /wiimmfi ─────────────────────────────────────────────────────────────────

@tree.command(name="wiimmfi", description="Show all Wiimmfi online player links.")
async def slash_wiimmfi(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌐 Magician's Quest — Wiimmfi Online",
        description="Check who is currently playing online:",
        color=0x7B4FBF,
    )
    for key, game in GAMES.items():
        value = f"[View online players]({game['wiimmfi']})" if game["wiimmfi"] else "*(3DS — no Wiimmfi support)*"
        embed.add_field(name=f"{game['emoji']} {game['short']} — {game['name']}", value=value, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.command(name="wiimmfi", help="Show all Wiimmfi online player links.")
async def prefix_wiimmfi(ctx: commands.Context):
    embed = discord.Embed(
        title="🌐 Magician's Quest — Wiimmfi Online",
        description="Check who is currently playing online:",
        color=0x7B4FBF,
    )
    for key, game in GAMES.items():
        value = f"[View online players]({game['wiimmfi']})" if game["wiimmfi"] else "*(3DS — no Wiimmfi support)*"
        embed.add_field(name=f"{game['emoji']} {game['short']} — {game['name']}", value=value, inline=False)
    await ctx.reply(embed=embed)

# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise ValueError("Missing DISCORD_TOKEN environment variable.")
    bot.run(token)
