# bot.py
from __future__ import annotations

import asyncio
from typing import Dict, Any

from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from openai import OpenAI

from config_starz import (
    DISCORD_BOT_TOKEN,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    TICKET_CATEGORY_IDS,
    AI_CONTROL_ROLES,
    load_style_text,
    load_rules_text,
    load_zorp_guide_text,
    load_raffle_text,
)

from starz_core.startup import run_startup_checks, send_startup_embed
from starz_core.commands import load_all_commands

# ✅ ADD: system bootstraps
from starz_core.rcon.bootstrap import start_rcon_system
from starz_core.printpos.bootstrap import start_printpos_system

# =========================
# SANITY CHECKS
# =========================
if not DISCORD_BOT_TOKEN:
    raise SystemExit("DISCORD_BOT_TOKEN missing")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY missing")

# =========================
# DISCORD + AI CLIENT
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

client_ai = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=30.0,
    max_retries=3,
)

# =========================
# GLOBAL STATE (MINIMAL)
# =========================
ticket_sessions: Dict[int, Dict[str, Any]] = {}

# Text blocks used by ticket router (loaded once)
style_text = load_style_text()
rules_text = load_rules_text()
zorp_guide_text = load_zorp_guide_text()
raffle_text = load_raffle_text()

# One-time boot guard (on_ready can fire more than once)
_systems_started: bool = False

# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    global _systems_started

    print(f"[BOT] Logged in as {bot.user} ({bot.user.id})")

    ok, failures = run_startup_checks()
    await send_startup_embed(
        bot,
        ok,
        failures,
        channel_id=1325974275504738415,
    )

    # Register slash commands (imports/registers via starz_core/commands.py)
    load_all_commands(bot)

    try:
        synced = await bot.tree.sync()
        print(f"[BOT] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[BOT] Slash sync failed: {e}")

    # ✅ START BACKEND SYSTEMS (only once)
    if not _systems_started:
        _systems_started = True
        try:
            await start_rcon_system(bot)
        except Exception as e:
            print(f"[BOOT] start_rcon_system error: {e}")

        try:
            await start_printpos_system(bot)
        except Exception as e:
            print(f"[BOOT] start_printpos_system error: {e}")
    else:
        print("[BOOT] Systems already started; skipping.")


@bot.event
async def on_message(message: discord.Message):
    # Ignore self
    if message.author == bot.user:
        return

    # Always allow prefix commands
    await bot.process_commands(message)

    if not isinstance(message.channel, discord.TextChannel):
        return

    # Ticket routing ONLY (keep wiring here, logic in ticket module)
    try:
        from starz_core.tickets.router import maybe_handle_ticket_message
        handled = await maybe_handle_ticket_message(
            bot=bot,
            client_ai=client_ai,
            message=message,
            style_text=style_text,
            rules_text=rules_text,
            zorp_guide_text=zorp_guide_text,
            raffle_text=raffle_text,
            ticket_sessions=ticket_sessions,
            ticket_category_ids=set(TICKET_CATEGORY_IDS),
            ai_control_roles=set(AI_CONTROL_ROLES),
        )
        if handled:
            return
    except ModuleNotFoundError:
        # If you haven't created starz_core/tickets/router.py yet, bot still runs.
        return
    except Exception as e:
        print(f"[TICKETS] Router error: {e}")


# =========================
# MAIN
# =========================
def main():
    bot.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
