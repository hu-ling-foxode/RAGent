import discord
import traceback
from discord.ext import commands
from datetime import datetime
import pickle
from pathlib import Path
import re
import base64

import settings
from models import Message
from rag import index_message, answer_query, qd_collection, chat_repl, qd_client, download_and_create_images, index_images


logger = settings.logging.getLogger("bot")

def process_incoming_message(message):
    """Replace user id with handle for mentions."""
    content = message.content
    for user in message.mentions:
        mention_str = f'<@{user.id}>'
        content = content.replace(mention_str, f'@{user.name}')
    message.content = content
    return message


def remember_message(when, who, msg_content, guild_id, channel):
    logger.info(
        f"Remembering new message \"{msg_content}\" from {who} on channel "
        f"{channel.name} at {datetime.now().strftime('%m-%d-%Y %H:%M:%S')}"
    )
    msg_str = f"[{when.strftime('%m-%d-%Y %H:%M:%S')}] - @{who} on #[{str(channel)[:15]}]: `{msg_content}`"
    global messages
    if not messages.get(guild_id, None):
        messages[guild_id] = []
    messages[guild_id].append(
        Message(is_in_thread=str(channel.type) == 'public_thread',
                posted_at=when,
                author=str(who),
                message_str=msg_str,
                channel_id=channel.id,
                just_msg=msg_content))
    persist_messages()

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
      
def remember_images(when, who, documents_url, guild_id, channel):
    logger.info(
        f"Remembering new images from {who} on channel "
        f"{channel.name} at {datetime.now().strftime('%m-%d-%Y %H:%M:%S')}"
    )
    #msg_str = f"[{when.strftime('%m-%d-%Y %H:%M:%S')}] - @{who} on #[{str(channel)[:15]}]: `{msg_content}`"
    global messages
    if not messages.get(guild_id, None):
        messages[guild_id] = []
    image_base64 = []
    for url in documents_url:
        base64_image = encode_image(url)
        image_base64.append(base64_image)
        postfix = url[url.rfind('.')+1:]
        messages[guild_id].append(
            Message(is_in_thread=str(channel.type) == 'public_thread',
                    is_image=True,
                    posted_at=when,
                    author=str(who),
                    message_str=url,
                    channel_id=channel.id,
                    just_msg=f"data:image/{postfix};base64,{base64_image}"))
    persist_messages()
    return image_base64

persist_dir = "./.persist"

messages_path = Path(persist_dir + "/messages.pkl")
listening_path = Path(persist_dir + "/listening.pkl")

messages_path.parent.mkdir(parents=True, exist_ok=True)


async def chunk_reply(message, input, bot):
    # Determine the channel based on input type
    if isinstance(input, discord.ext.commands.Context):
        channel = input.channel
    elif isinstance(input, discord.Message):
        channel = input.channel
    elif isinstance(input, discord.Interaction):
        channel = input.channel
    else:
        raise ValueError("Unsupported input type.")
    message = message.replace("```", "\n```")
    def split_content(content, max_length=2000):
        parts = []
        last_index = 0
        in_code_block = False
        code_block_id = ""

        while last_index < len(content):
            in_code_block_type = None
            if last_index + max_length >= len(content):
                if in_code_block:
                    parts.append("\n```" + code_block_id + '\n' + content[last_index:next_split])
                else:  
                    parts.append(content[last_index:])
                return parts
            in_code_block_type = None
            find_good_split = False
            next_split = last_index + max_length
            patterns = [
                r'\n###'
                r'\n\*\*',      # Titles
                r'\n\d+\.\s'  # Numbered bullet points
            ]
            # 500-2000: title, point, code
            for pattern in patterns:
                matches = list(re.finditer(pattern, content[last_index + 500: last_index + 2000]))
                if matches:
                    next_split = last_index + 500 + matches[-1].start()
                    find_good_split = True
                    break
            if not find_good_split:
                split_s = ['\n', '. ', ' ']
                for s in split_s:
                    tmp_split = content.rfind(s, last_index + 1500, last_index + 2000)
                    if tmp_split != -1:
                        next_split = tmp_split
                        find_good_split = True
                        break

            code_blocks = list(re.finditer(r'\n```', content[last_index: next_split]))
            if not in_code_block:
                if len(code_blocks) % 2 == 0:
                    pass
                else:
                    if last_index + code_blocks[-1].start() == last_index:
                        in_code_block = True
                        in_code_block_type = 1
                        tmp = content.find('\n', last_index + 4, next_split)
                        code_block_id = content[last_index+4:tmp]
                    else:
                        next_split = last_index + code_blocks[-1].start()

            else:
                if len(code_blocks) % 2 == 0:
                    in_code_block_type = 2
                else:
                    in_code_block_type = 3
                    in_code_block = False

            if in_code_block_type is None:
                parts.append(content[last_index:next_split])
            elif in_code_block_type == 1:
                parts.append(content[last_index:next_split] + "\n```")
            elif in_code_block_type == 2:
                parts.append("\n```" + code_block_id + '\n' + content[last_index:next_split] + "\n```")
            elif in_code_block_type == 3:
                parts.append("\n```" + code_block_id + '\n' + content[last_index:next_split])
                code_block_id = ''
            last_index = next_split
        return parts
    chunk_size = 2000  # Discord's max message size limit
    if len(message) <= chunk_size:
        if isinstance(input, discord.Interaction):
            await input.followup.send(message)
        else:
            async with channel.typing():
                await channel.send(message)
    else:
        parts = split_content(message)
        if isinstance(input, discord.Interaction):
            for part in parts:
                await input.followup.send(part)
        else:
            async with channel.typing():
                for part in parts:
                    await channel.send(part)



def persist_listening():
    global listening

    with open(listening_path, 'wb') as file:
        pickle.dump(listening, file)


def persist_messages():
    global messages

    with open(messages_path, 'wb') as file:
        pickle.dump(messages, file)



if messages_path.is_file():
    with open(messages_path, 'rb') as file:
        messages = pickle.load(file)
else:
    messages: dict[int, list[Message]] = {}
    persist_messages()

if listening_path.is_file():
    with open(listening_path, 'rb') as file:
        listening = pickle.load(file)
else:
    listening: dict[int, bool] = {}
    persist_listening()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    logger.info(f"User: {bot.user} (ID: {bot.user.id})")


#@bot.command(aliases=['li'])
@tree.command(name="listen", description="RAgent will start listening to messages in this channel from now on.")
async def listen(interaction: discord.Interaction):
    "RAgent will start listening to messages in this channel from now on."

    global listening
    listening[interaction.guild.id] = True
    persist_listening()
    logger.info(
        f"Listening to messages on channel {interaction.channel.name} of server: {interaction.guild.id} "
        f"from {datetime.now().strftime('%m-%d-%Y %H:%M:%S')}")
    await interaction.response.send_message('**RAgent SYS**: Listening to your messages now.')


#@bot.command(aliases=['s'])
@tree.command(name="stop", description="RAgent will stop listening to messages in this channel from now on")
async def stop(interaction: discord.Interaction):
    "RAgent will stop listening to messages in this channel from now on."

    global listening
    listening[interaction.guild.id] = False
    persist_listening()
    logger.info(
        f"Stopped Listening to messages on channel "
        f"{interaction.channel.name} from {datetime.now().strftime('%m-%d-%Y')}")
    await interaction.response.send_message('**RAgent SYS**: Stopped listening to messages.')


#@bot.command(aliases=['f'])
@tree.command(name="forget", description="RAgent will forget all messages in this channel from now on")
async def forget(interaction: discord.Interaction):
    "Llama will forget everything it remembered. It will forget all messages, todo, reminders etc."

    # forget_all(ctx)
    from qdrant_client.http import models as rest

    global qd_client

    try:
        global messages
        global listening
        messages.pop(interaction.guild.id)
        listening.pop(interaction.guild.id)
    except KeyError:
        pass
    persist_messages()
    persist_listening()

    qd_client.delete(
        collection_name=qd_collection,
        points_selector=rest.Filter(must=[
            rest.FieldCondition(key="guild_id",
                                match=rest.MatchValue(value=interaction.guild.id))
        ]),
    )
    await interaction.response.send_message('**RAgent SYS**: All messages forgotten & stopped listening to yall')


#@bot.command(aliases=['st'])
@tree.command(name="status", description="RAgent will tell you if it's listening to messages in this channel")
async def status(interaction: discord.Interaction):
    "Status of RAgent, whether it's listening or not"
    global listening
    await interaction.response.send_message(
      "**RAgent SYS**: Listening to yall👂" if listening.get(interaction.guild.id, False) \
      else "**RAgent SYS**: Not Listening 🙉"
    )

#@bot.command(aliases=['r'])
#rag is not summarize, rag is to answer question based on local data and LLM knowledge and logical ability
#as for rag, we should support all channels, specified channels and the channel where the message is sent
#as for rag, we should support different data sources.
@tree.command(name="rag", description="RAgent will answer question based on local data and current channel history and LLM knowledge and logical ability")
async def rag(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    global listening
    
    # this might be wrong, since even if we are not listening, we should still respond to the message
    # this should be rewrite... 
    if not listening.get(interaction.guild.id, False):
        await interaction.response.send_message(
            "I'm not listening to what y'all saying. "
            "\nRun \"/listen\" if you want me to start listening.")
        return
    if len(query) == 0:
        await interaction.response.send_message("**RAgent SYS**: Empty Input?")
        return

    # it is not reasonable to use messages from a server as "replies"
    # here we should use last few messages from the channel as "replies"
    # however, here seems to be a sanity check, ignore
    rag_messages = [
        msg for msg in messages.get(interaction.guild.id, [])
        if not msg.just_msg.startswith("**RAgent SYS**:") # can be deleted
    ]
    if len(rag_messages) == 0:
        await interaction.response.send_message(
            "**RAgent SYS**: Hey, RAgent's knowledge base is empty now. Please say something before using rag function."
        )
        return
    try:
        #async with interaction.typing():
            #response = await answer_query(messages, " ".join(query), ctx, bot)
        response = await answer_query(messages, query, interaction, bot)
            # await ctx.message.reply(response)
        await chunk_reply(response, interaction, bot)
        if listening.get(interaction.guild.id, False):
            #message = interaction.message
            # def remember_message(when, who, msg_content, guild_id, channel):
            # def index_message(when, who, msg_content, guild_id, channel):
            snowflake_id = interaction.id
            timestamp = ((snowflake_id >> 22) + 1420070400000) / 1000
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            remember_message(timestamp, bot.user, response, interaction.guild_id, interaction.channel)
            index_message(timestamp, bot.user, response, interaction.guild_id, interaction.channel)
    except:
        tb = traceback.format_exc()
        print(tb)
        await interaction.response.send_message(
            "**RAgent SYS**: The bot encountered an error, will try to fix it soon."
        )

@bot.command()
async def sync(ctx):
    print("sync command")
    print(ctx.author.id)
    if ctx.author.id == 799479143174897694:
        await bot.tree.sync()
        await ctx.send('**RAgent SYS**: Command tree synced.')
    else:
        await ctx.send('**RAgent SYS**: You must be the owner to use this command!')

@bot.event
async def on_message(message):
    global listening
    message = process_incoming_message(message)
    if message.author == bot.user:
        return
    if message.content.startswith('/'):
        await bot.process_commands(message)
        return
    if listening.get(message.guild.id, False):
        # def remember_message(when, who, msg_content, guild_id, channel):
        # def index_message(when, who, msg_content, guild_id, channel):
        image_urls = [a.url for a in message.attachments if a.content_type.startswith("image")]
        print("image_urls", image_urls)
        if image_urls:
            print("hiiiiiiiiiiiiiiiiiiiiiii")
            documents_url = await download_and_create_images(image_urls)
            # this part should be rewrite into an async version
            print("documents", documents_url)
            images_base64 = remember_images(message.created_at, message.author, documents_url, message.guild.id, message.channel)
            index_images(message.created_at, message.author, images_base64, message.guild.id, message.channel)
        remember_message(message.created_at, message.author, message.content, message.guild.id, message.channel)
        index_message(message.created_at, message.author, message.content, message.guild.id, message.channel)

    if bot.user.mentioned_in(message):
        #query = message.content.replace(f'<@!{bot.user.id}>', '').strip()
        query = message.content

        if not listening.get(message.guild.id, False):
            await message.reply(
                "I'm not listening to what y'all saying 🙈🙉🙊. "
                "\nRun \"/listen\" if you want me to start listening.")
            return

        if not query:
            await message.reply("What?")
            return

        try:
            async with message.channel.typing():
                # response = await answer_query(messages, query, message, bot)
                response = await chat_repl(messages, query, message, bot)
                # await message.reply(response)
                await chunk_reply(response, message, bot)
                if listening.get(message.guild.id, False):
                    # def remember_message(when, who, msg_content, guild_id, channel):
                    # def index_message(when, who, msg_content, guild_id, channel):
                    remember_message(message.created_at, bot.user, response, message.guild.id, message.channel)
                    index_message(message.created_at, bot.user, response, message.guild.id, message.channel)

        except:
            tb = traceback.format_exc()
            print(tb)
            await message.reply(
                "**RAgent SYS**: The bot encountered an error, will try to fix it soon."
            )

    await bot.process_commands(message)
