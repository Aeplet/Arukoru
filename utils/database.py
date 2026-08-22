import aiosqlite

from constants import DATABASE_FILE_NAME

async def init_database():
    async with aiosqlite.connect(DATABASE_FILE_NAME) as db:
        # warn table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                issuer_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # guild invite whitelist table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelisted_guilds (
                guild_whitelist_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                adder_id INTEGER NOT NULL,
                guild_whitelisted_in INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # user restrictions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_restrictions (
                restriction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                issuer_id INTEGER NOT NULL,
                reason TEXT,
                user_id INTEGER NOT NULL,
                restriction_type INTEGER NOT NULL,
                guild_id INTEGER NOT NULL
            )""")
        # server logs channels table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_log_channels (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                log_channel_type INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # honeypot channels table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS honeypot_channels (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                guild_id INTEGER NOT NULL,
                honeypot_channel_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # appeal instructions per server
        await db.execute("""
            CREATE TABLE IF NOT EXISTS appeal_instructions (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                guild_id INTEGER NOT NULL,
                appeal_instructions_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # allowed guilds (guilds the bot can be used in)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS allowed_guilds (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                guild_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        await db.commit()
        print("Successfully initialized database!")

async def execute(query: str, parameters: tuple = ()):
    async with aiosqlite.connect(DATABASE_FILE_NAME) as db:
        async with db.execute(query, parameters) as cursor:
            await db.commit()
            return cursor.lastrowid

async def fetch_all(query: str, parameters: tuple = ()):
    async with aiosqlite.connect(DATABASE_FILE_NAME) as db:
        async with db.execute(query, parameters) as cursor:
            return await cursor.fetchall()

async def fetch_one(query: str, parameters: tuple = ()):
    async with aiosqlite.connect(DATABASE_FILE_NAME) as db:
        async with db.execute(query, parameters) as cursor:
            return await cursor.fetchone()