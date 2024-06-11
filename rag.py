from llama_index.core import StorageContext
from llama_index.core.indices import MultiModalVectorStoreIndex
from llama_index.core import Settings
from llama_index.core.postprocessor import FixedRecencyPostprocessor

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.schema import TextNode, QueryBundle, ImageNode
from llama_index.core.vector_stores.types import (
    MetadataFilter,
    MetadataFilters,
    FilterOperator,
)
from llama_index.core import set_global_handler
from llama_index.core.base.llms.types import ChatMessage, MessageRole
import qdrant_client
import os
import aiohttp
import asyncio
from PIL import Image
from io import BytesIO


import settings
from prompts import prompt

set_global_handler("simple")

# initialize qdrant client
qd_client = qdrant_client.QdrantClient(
  url=settings.QDRANT_URL,
  api_key=settings.QDRANT_API_KEY
)

qd_collection = 'discord_llamabot'
use_openai = bool(os.environ.get("USE_OPENAI", False))
use_cohere = bool(os.environ.get("USE_COHERE", False))

if use_openai:
  from llama_index.llms.openai import OpenAI
  from llama_index.embeddings.openai import OpenAIEmbedding
  print("Using GPT-4")
  llm=OpenAI(
    #model="gpt-4-0125-preview",
    model="gpt-4o"
  )
  embed_model = OpenAIEmbedding(model="text-embedding-3-small")
elif use_cohere:
  from llama_index.llms import Cohere
  print("Using Cohere")
  llm=Cohere(api_key=os.environ.get('COHERE_KEY'))
else:
  from llama_index.llms.gemini import Gemini
  print("Using Gemini Pro")
  llm=Gemini()

vector_store = QdrantVectorStore(client=qd_client,
                                collection_name=qd_collection)
image_store = QdrantVectorStore(
    client=qd_client, collection_name="image_collection"
)
storage_context = StorageContext.from_defaults(vector_store=vector_store, image_store=image_store)

Settings.llm = llm
Settings.embed_model = embed_model


# index = VectorStoreIndex([],
#                storage_context=storage_context,
#                          embed_model=embed_model)
index = MultiModalVectorStoreIndex([], storage_context=storage_context, embed_model=embed_model)

def index_message(when, who, msg_content, guild_id, channel):
  msg_str = f"[{when.strftime('%m-%d-%Y %H:%M:%S')}] - @{who} on #[{str(channel)[:15]}]: `{msg_content}`"
  
  node = TextNode(
    text=msg_str,
    metadata={
      'author': str(who),
      'posted_at': str(when),
      'channel_id': channel.id,
      'guild_id': guild_id
    },
    excluded_llm_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
    excluded_embed_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
  )

  index.insert_nodes([node])

def index_images(when, who, image_base64, guild_id, channel):
  nodes = []
  for image in image_base64:
    node = ImageNode(
      image=image,
      metadata={
        'author': str(who),
        'posted_at': str(when),
        'channel_id': channel.id,
        'guild_id': guild_id
      },
      excluded_llm_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
      excluded_embed_metadata_keys=['author', 'posted_at', 'channel_id', 'guild_id'],
    )
    nodes.append(node)
  index.insert_nodes(nodes)

async def chat_repl(messages, query, message, bot):
  channel_id = message.channel.id
  chat_history = [ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant. Your name is RAgent.")]
  tmp = []
  for msg in messages.get(message.guild.id, []):
    if msg.channel_id == channel_id:
      tmp.append(msg)
      if msg.author != str(bot.user):
        if msg.is_image:
          chat_history.append(ChatMessage(role=MessageRole.USER, content=[{"type":"image_url", "image_url":{"url":msg.just_msg}}]))
        else:
          chat_history.append(ChatMessage(role=MessageRole.USER, content=msg.just_msg))
      else:
        if msg.is_image:
          chat_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=[{"type":"image_url", "image_url":{"url":msg.just_msg}}]))
        else:
          chat_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=msg.just_msg))
  # print(chat_history)
  print('Mooooo')
  print(message.attachments)
  # print("chat history")
  # print(chat_history)
  # print("messages")
  # print(tmp)
  r = llm.chat(chat_history)
  # print(r)
  return r.message.content

async def answer_query(messages, query, interaction, bot):

  # 1. specify channel in the query
  # 2. get channel id by channel name
  # 3. filter by these channel id
  # 4. avoid triggering this step if # is in the query somehow
  # 5. the position of # is not determined
  # 6. first step: get the channel id name dict 
  channel_id = interaction.channel.id
  thread_messages = [
    msg.just_msg for msg in messages.get(interaction.guild.id, []) if msg.channel_id==channel_id
  ][-1*settings.LAST_N_MESSAGES:-1]
  # thread_messages = [
  #   msg.message_str for msg in messages.get(interaction.guild.id, [])
  # ]

  # replies seems wrong, and what is context_str?
  partially_formatted_prompt = prompt.partial_format(
    replies="\n".join(thread_messages),
    user_asking=str(interaction.user.name),
    bot_name=str(bot.user)
  )

  # we might filter further to get specified channels messages
  filters = MetadataFilters(
    filters=[
      MetadataFilter(
        key="guild_id", operator=FilterOperator.EQ, value=interaction.guild.id
      )
    ]
  )

  # why are we using data_key here, and what is FixedRecencyPostprocessor?
  postprocessor = FixedRecencyPostprocessor(
      top_k=8, 
      date_key="posted_at", # the key in the metadata to find the date
  )

  # what is index.as_query_engine?
  query_engine = index.as_query_engine(
    filters=filters,
    similarity_top_k=8,
    node_postprocessors=[postprocessor])

  # what is update_prompts?
  # this code is ... confusing.
  query_engine.update_prompts(
      {"response_synthesizer:text_qa_template": partially_formatted_prompt}
  )

  replies_query = [
    msg.just_msg for msg in messages.get(interaction.guild.id, []) if msg.channel_id==channel_id
  ][-1*settings.LAST_N_MESSAGES:-1]
  replies_query.append(query)

  # print(replies_query)
  # what is QueryBundle, what is custome_embedding_strs?
  # it seems in here query_str is formatted, context_str is formatted by retreiving using custom_embedding_strs
  # check this part!
  # print(query_engine.get_prompts())
  return str(query_engine.query(QueryBundle(
    query_str=query,
    custom_embedding_strs=replies_query
  )))

# Directory to save images
IMAGE_DIR = './images'

# Ensure the directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

async def download_and_create_images(image_urls):
    async def download_image(session, url):
        try:
            async with session.get(url) as response:
                response.raise_for_status()

                # Get image from response
                image_data = await response.read()
                image = Image.open(BytesIO(image_data))

                # Create a unique filename
                filename = os.path.join(IMAGE_DIR, os.path.basename(url))
                print("filename", filename)
                file_type = filename[filename.rfind('.'):filename.rfind('?')]
                # if not filename.lower().endswith('.jpg') and not filename.lower().endswith('.png'):
                #     filename += '.jpg'  # Assume JPEG format if no extension

                # Save the image locally
                filename += file_type
                print("filename", filename)
                image.save(filename)
                return filename
        except aiohttp.ClientError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as err:
            print(f"An error occurred: {err}")

        return None

    # def create_image_document(image_path):
    #     # Create a document with the image path and any required metadata
    #     return Document(
    #         content="Image",
    #         metadata={"image_path": image_path}
    #     )

    async with aiohttp.ClientSession() as session:
        # Create a list of download tasks
        tasks = [download_image(session, url) for url in image_urls]

        # Run all tasks concurrently
        image_paths = await asyncio.gather(*tasks)

        # Create documents for each successfully downloaded image
        # documents = [SimpleDirectoryReader(path).load_data() for path in image_paths if path]

    return image_paths
  