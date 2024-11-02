import hikari
import lightbulb
import random
import asyncio

import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import gspread.exceptions
import logging


creds_json = json.loads(os.getenv("GOOGLE_SHEETS_CREDS"))
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scopes)
client = gspread.authorize(creds)

# Open the Google Sheet
sheet = client.open("Computer Science Club Member Form Responses").sheet1  # Change to your sheet name

# Fetch all records
data = sheet.get_all_records()

# Example: Assign roles and nicknames
for entry in data:
    username = entry["What's your Discord Username? "]  # Adjust based on your column names
    nickname = entry['How do you want to be addressed on discord?']   # Adjust based on your column names
    # Your code to assign roles and set nicknames goes here

bot = lightbulb.BotApp(
    token=os.getenv("DISCORD_BOT_TOKEN"),
    intents=hikari.Intents.ALL
)

# Role mappings
ROLE_EMOJI_MAPPING = {
    "🐍": 1286066893282607195,
    "🌊": 1286095057690169374,
    "☕": 1286096191905333320,
    "🌐": 1286097485734871071,
    "👾": 1286099013568958535,
    "🎨": 1286098134036119663,
}

PRONOUN_ROLE_EMOJI_MAPPING = {
    "🟥": 1287300665353437246,
    "🟦": 1287300470058258473,
    "🟪": 1287300748014522460,
    "🟨": 1287323346354045060,
}

# Guild ID
GUILD_ID = 1285358247016005706

# Role IDs
MEMBER_ROLE_ID = 1286546888832843858
VISITOR_ROLE_ID = 1287195640492986370
LANGUAGES_ID = 1287194613781630997
PRONOUNS_ID = 1287305586165415959

# Channel IDs
WELCOME_CHANNEL_ID = 1285358247489966082
CREATE_VOICE_CHANNEL_ID = 1287321828141826098
CREATE_CATEGORY_CHANNEL_ID = 1285358247489966085
ADMIN_CHANNEL_ID = 1285486890736418830

# Role message IDs dictionary
role_message_ids = {
    "pronoun_roles": 1287528260179202058,
    "language_roles": 1287528385140232256,
}

# A dictionary to keep track of dynamically created channels
created_channels = {}
voice_channel_members = {}

@bot.listen
async def on_ready():
    await bot.change_presence(activity=hikari.Activity(type=hikari.ActivityType.PLAYING, name="with the Computer Science Club!"))
    print(f"Logged in as {bot.me.username}")

@bot.command
@lightbulb.command('assign_roles', 'Assign roles and nicknames based on Google Sheet responses')
@lightbulb.implements(lightbulb.SlashCommand)
async def update_members(ctx: lightbulb.Context) -> None:
    print("Checking for new members")
    max_retries = 5  # Maximum number of retry attempts
    for attempt in range(max_retries):
        try:
            data = sheet.get_all_records()  # Fetch Google Sheet records
            break  # Exit loop if successful
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 500:
                wait_time = 2 ** attempt  # Exponential backoff
                logging.error(f"APIError encountered: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise
    else:
        # Max retries reached, log the error and return
        await print("Failed to retrieve data from Google Sheets after several attempts.")
        return

    guild = await bot.rest.fetch_guild(GUILD_ID)

    for entry in data:
        username = entry.get("What's your Discord Username? ", "").strip()
        nickname = entry.get('How do you want to be addressed on discord?', "").strip()

        if not username:
            logging.warning("Entry missing Discord username, skipping...")
            continue  # Skip if the username is missing

        # Find the member by username
        members = await bot.rest.fetch_members(GUILD_ID)
        for member in members:
            if member.username == username:
                # Check if member already has the Member role
                if MEMBER_ROLE_ID not in member.role_ids:
                    await member.add_role(MEMBER_ROLE_ID)
                    await member.remove_role(VISITOR_ROLE_ID)
                    print(f"Assigned Member role to {username}.")
                    if nickname:
                        await member.edit(nickname=nickname)
                        print(f"Updated nickname for {username}.")
                break
        else:
            await print(f"Member {username} not found.")

class MockContext:
    def __init__(self, bot, channel, guild):
        self.bot = bot
        self.channel = channel
        self.guild = guild

    async def respond(self, message):
        await self.bot.rest.create_message(self.channel.id, message)

async def periodic_update():
    guild = await bot.rest.fetch_guild(GUILD_ID)
    channel = await bot.rest.fetch_channel(ADMIN_CHANNEL_ID)
    context = MockContext(bot, channel, guild)

    while True:
        try:
            await update_members(context)
        except gspread.exceptions.APIError as e:
            logging.error(f"Error during Google Sheets update: {e}")
            await print("There was an issue accessing Google Sheets. Please try again later.")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
        await asyncio.sleep(60)  # Check every minute

@bot.listen(hikari.StartedEvent)
async def on_startup(event: hikari.StartedEvent) -> None:
    asyncio.create_task(periodic_update())

@bot.listen(hikari.VoiceStateUpdateEvent)
async def on_voice_state_update(event: hikari.VoiceStateUpdateEvent) -> None:
    guild_id = event.guild_id
    member = event.state.member

    # If the user joins the main voice channel
    if event.state.channel_id == CREATE_VOICE_CHANNEL_ID:
        # Check if the user already has a study room
        if member.id in created_channels:
            old_channel_id = created_channels[member.id]
            await bot.rest.delete_channel(old_channel_id)  # Delete the old study room

        # Create a new custom voice channel
        new_channel = await bot.rest.create_guild_voice_channel(
            guild=guild_id,
            name=f"👥︱{member.nickname or member.username}'s Study Room",
            category=CREATE_CATEGORY_CHANNEL_ID,
        )

        # Move the user to the new custom voice channel
        await bot.rest.edit_member(
            guild=guild_id,
            user=member.id,
            voice_channel=new_channel.id
        )

        # Store the newly created channel and the member
        created_channels[member.id] = new_channel.id
        voice_channel_members[new_channel.id] = {member.id}

    # If the user leaves a voice channel
    elif event.old_state and event.old_state.channel_id in created_channels.values():
        channel_id = event.old_state.channel_id

        # Update the members in the channel
        if channel_id in voice_channel_members:
            voice_channel_members[channel_id].discard(event.old_state.member.id)

        # If the channel becomes empty, delete it
        if not voice_channel_members[channel_id]:  # Check if no members are left
            await bot.rest.delete_channel(channel_id)
            del created_channels[member.id]  # Remove the channel mapping
            del voice_channel_members[channel_id]  # Remove member tracking

    # If the user joins a created channel, add them to the member list
    if event.state.channel_id in voice_channel_members:
        voice_channel_members[event.state.channel_id].add(event.state.member.id)

@bot.command
@lightbulb.command('setup_pronoun_roles', 'Sets up the pronoun roles prompt')
@lightbulb.implements(lightbulb.SlashCommand)
async def setup_pronoun_roles(ctx: lightbulb.Context) -> None:
    global role_message_ids
    channel = ctx.get_channel()

    embed = hikari.Embed(
        title="REACT FOR YOUR PRONOUNS!!!",
        description="React with the corresponding emoji to get your pronoun role!\n\n" +
                    "🟥 ︱ She/Her\n" +
                    "🟦 ︱ He/Him\n" +
                    "🟪 ︱ They/Them\n" +
                    "🟨 ︱ Ask",
        color=0xcc63ff
    )
    
    message = await channel.send(embed=embed)
    role_message_ids["pronoun_roles"] = message.id

    for emoji in PRONOUN_ROLE_EMOJI_MAPPING.keys():
        await message.add_reaction(emoji)

@bot.command
@lightbulb.command('setup_language_roles', 'Sets up the language roles prompt')
@lightbulb.implements(lightbulb.SlashCommand)
async def setup_language_roles(ctx: lightbulb.Context) -> None:
    global role_message_ids
    channel = ctx.get_channel()

    embed = hikari.Embed(
        title="REACT FOR CODING LANGUAGE ROLES!!!",
        description="React to the language emojis that you are capable in.\n(Will get pinged for help in chosen languages)\n\n" +
                    "🐍 - Python\n" +
                    "🌊 - C++\n" +
                    "☕ - Java\n" +
                    "🌐 - JavaScript\n" +
                    "👾 - C#\n" +
                    "🎨 - HTML/CSS",
        color=0x077fff
    )
    message = await channel.send(embed=embed)
    role_message_ids["language_roles"] = message.id

    for emoji in ROLE_EMOJI_MAPPING.keys():
        await message.add_reaction(emoji)

@bot.listen(hikari.ReactionAddEvent)
async def on_reaction_add(event: hikari.ReactionAddEvent) -> None:
    if event.user_id == bot.get_me().id:
        return
    
    guild = await bot.rest.fetch_guild(event.guild_id)
    
    # Check for pronoun roles
    if event.message_id == role_message_ids["pronoun_roles"]:
        role_id = PRONOUN_ROLE_EMOJI_MAPPING.get(event.emoji_name)
        if role_id:
            role = guild.get_role(role_id)
            member = await bot.rest.fetch_member(event.guild_id, event.user_id)
            if role and member:
                await member.add_role(role)
                print(f"Assigned role {role.name} to {member.display_name}")

    # Check for language roles
    elif event.message_id == role_message_ids["language_roles"]:
        role_id = ROLE_EMOJI_MAPPING.get(event.emoji_name)
        if role_id:
            role = guild.get_role(role_id)
            member = await bot.rest.fetch_member(event.guild_id, event.user_id)
            if role and member:
                await member.add_role(role)
                print(f"Assigned role {role.name} to {member.display_name}")

@bot.listen(hikari.ReactionDeleteEvent)
async def on_reaction_remove(event: hikari.ReactionDeleteEvent) -> None:
    guild = await bot.rest.fetch_guild(event.guild_id)
    
    # Check for pronoun roles
    if event.message_id == role_message_ids["pronoun_roles"]:
        role_id = PRONOUN_ROLE_EMOJI_MAPPING.get(event.emoji_name)
        if role_id:
            role = guild.get_role(role_id)
            member = await bot.rest.fetch_member(event.guild_id, event.user_id)
            if role and member:
                await member.remove_role(role)
                print(f"Removed role {role.name} from {member.display_name}")

    # Check for language roles
    elif event.message_id == role_message_ids["language_roles"]:
        role_id = ROLE_EMOJI_MAPPING.get(event.emoji_name)
        if role_id:
            role = guild.get_role(role_id)
            member = await bot.rest.fetch_member(event.guild_id, event.user_id)
            if role and member:
                await member.remove_role(role)
                print(f"Removed role {role.name} from {member.display_name}")

@bot.command
@lightbulb.command('diceroll', 'Roll the Dice!')
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    rollNumber = random.randint(1, 6)
    await ctx.respond(f"You rolled a {rollNumber}!!!")

@bot.command
@lightbulb.command('coinflip', 'Flip the Coin!')
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    flipNumber = random.randint(1, 2)
    if (flipNumber == 1):
        await ctx.respond("You got Tails!!!")

    if (flipNumber == 2):
        await ctx.respond("You got Heads!!!")

@bot.command
@lightbulb.option('max', 'The maximum number for the random range', type=int)
@lightbulb.command('randomnumber', 'Picks a random number between 0 and any number you enter!')
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    randNumber = random.randint(0, ctx.options.max)
    await ctx.respond(f"You rolled a {randNumber}!!!")

@bot.command
@lightbulb.command('computerscience', 'I love Computer Science!')
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    await ctx.respond('I also love Computer Science!')

@bot.listen(hikari.MemberCreateEvent)
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    channel = await bot.rest.fetch_channel(WELCOME_CHANNEL_ID)
    display_name = event.member.display_name or event.member.username
    
    embed = hikari.Embed(
        title="Welcome to the Server!",
        description=f"Hello {display_name} ({event.member.mention}), Welcome to the server! 🎉🎉🎉\n" \
                      "We're glad to have you here! Feel free to check out the rules and introduce yourself!",
        color=0x077fff
    )

    embed.set_thumbnail(event.member.avatar_url or "https://i.imgur.com/iXb26SA.png")
    embed.set_footer(text="Enjoy your stay!")
    
    await channel.send(embed=embed)

    try:
        await event.member.add_role(VISITOR_ROLE_ID)
        await event.member.add_role(LANGUAGES_ID)
        await event.member.add_role(PRONOUNS_ID)
        print(f"Assigned first roles to {event.member.username}")
    except Exception as e:
        print(f"Failed to assign first roles: {e}")

bot.run()