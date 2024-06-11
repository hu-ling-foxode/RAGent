# RAGent
RAgent is a Discord bot designed to help users learn, summarize, and mine data within a Discord server using multimodal LLM and RAG systems. This project is an evolution of the llamabot project, with significant improvements and new features.

## LlamaBot

An open-source Discord bot, created using LlamaIndex, that -
- Listens to your server conversations
- Continuously learns from them
- Answers your questions from the entire server.

It’s recommended to host this bot yourself for your server, but if you wanna try out first, you can join this discord server and use RAGent through this link: https://discord.gg/sSkfGQHWk2

Tech stack used for this bot:
1. **LlamaIndex** as the RAG framework
2. **Openai** Pro as the LLm and Embedding model
3. **Qdrant cloud** as the vectorstore
4. **discord.py** to setup the bot logic
5. Finally deploy it to **Replit**

Checkout [llamabot blog post](https://clusteredbytes.pages.dev/posts/2024/create-a-discord-chatbot-using-llamaindex-for-your-server/) where rsrohan99 walk you through the entire process of building a full-fledged discord bot like this using LlamaIndex.

### Features

- `@RAGent` - Ask RAGent questions like a user
- `/listen` - Starts listening to messages across the server and remembers those.
- `/stop` - Stops listening to messages
- `/forget` - Forgets all messages from the server
- `/status` - Shows whether bot is listening to messages or not
- `/sync` - Sync new slash commands to all servers
- `/rag` - Get answer from messages across the server


### Installation
Make sure you go through rsrohan99's blog to get the discord api token and qdrant key and url done.

Go to replit and start a free discord bot project by importing from github.

On the replit shell set folloing up:
```bash
export DISCORD_API_TOKEN='your token'
export OPENAI_API_KEY='your key'
export USE_OPENAI=1
export QDRANT_KEY='your key'
export QDRANT_URL='your url'
python main.py

```

You can chat with your own RAGent in your own server now.

