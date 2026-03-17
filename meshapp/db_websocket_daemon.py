import asyncio
import json
import datetime
import sqlite3
import websockets
import websockets.exceptions


# =========================================================
# CONFIGURAZIONE DATABASE
# =========================================================

# vedi dove viene salvato il db popolato da mqtt2sqlite_msg
DB_FILE = "/home/david/meshtastic_messages.db"

POLL_INTERVAL = 10
CHANNEL_FILTER = 0  # 0 = Primary channel, lavoro su questo

# =========================================================
# CONFIGURAZIONE WEBSOCKET
# =========================================================

WS_PORT = 8765


# =========================================================
# BUFFER MESSAGGI
# =========================================================

MESSAGE_BUFFER = 10  # nn messaggi da consegnare alla app


# =========================================================
# STRUTTURE GLOBALI
# =========================================================

clients = set()
message_buffer = []
last_id = 0
loop = None


# =========================================================
# WEBSOCKET HANDLER
# =========================================================
async def ws_handler(websocket):

    print("Client WebSocket connesso", flush=True)

    clients.add(websocket)

    for msg in message_buffer:
        try:
            await websocket.send(json.dumps(msg))
        except:
            pass

    try:
        async for _ in websocket:
            pass

    except websockets.exceptions.ConnectionClosed:
        pass

    finally:
        if websocket in clients:
            clients.remove(websocket)

        print("Client WebSocket disconnesso", flush=True)


# =========================================================
# BROADCAST
# =========================================================
async def broadcast(data):

    print("Broadcast:", data, flush=True)

    message_buffer.append(data)

    if len(message_buffer) > MESSAGE_BUFFER:
        message_buffer.pop(0)

    if not clients:
        return

    dead = set()

    for c in clients:
        try:
            await c.send(json.dumps(data))
        except:
            dead.add(c)

    for d in dead:
        clients.remove(d)


# =========================================================
# INIZIALIZZAZIONE BUFFER MESSAGGI ALL'AVVIO
# =========================================================
def init_last_id():

    with sqlite3.connect(DB_FILE, timeout=5) as conn:
        c = conn.cursor()

        c.execute(
            """
            SELECT id
            FROM messages
            WHERE channel = ?
            ORDER BY id DESC
            LIMIT 1 OFFSET ?
            """,
            (CHANNEL_FILTER, MESSAGE_BUFFER)
        )

        row = c.fetchone()

    if row:
        return row[0]

    return 0


# =========================================================
# LETTURA NUOVI MESSAGGI DAL DB
# =========================================================
def read_new_messages():

    global last_id

    with sqlite3.connect(DB_FILE, timeout=5) as conn:
        c = conn.cursor()

        c.execute(
            """
            SELECT
                m.id,
                m.text,
                m.timestamp,
                n.longname,
                n.node_id,
                m.from_id
            FROM messages m
            LEFT JOIN nodes n
            ON m.from_id = n.from_id
            WHERE m.id > ?
            AND m.channel = ?
            ORDER BY m.id ASC
            """,
            (last_id, CHANNEL_FILTER)
        )

        rows = c.fetchall()

    return rows


# =========================================================
# TASK DI MONITORAGGIO DATABASE
# =========================================================
async def db_watcher():

    global last_id
    global loop

    while True:
        try:
            rows = read_new_messages()

            for r in rows:

                msg_id, text, ts, longname, node_hex, node_dec = r

                last_id = msg_id

                if not text:
                    continue

                text = text.replace("\x00", "").strip()

                if longname:
                    node_name = longname
                elif node_hex:
                    node_name = node_hex
                else:
                    node_name = f"!{node_dec:08x}"

                t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")

                data = {
                    "time": t,
                    "node": node_name,
                    "text": text
                }

                # print(f"[{t}] {node_name} : {text}", flush=True)

                await broadcast(data)

        except sqlite3.OperationalError as e:
            print(f"Errore SQLite: {e}", flush=True)

        except Exception as e:
            print(f"Errore db_watcher: {e}", flush=True)

        await asyncio.sleep(POLL_INTERVAL)


# =========================================================
# MAIN
# =========================================================
async def main():

    global loop
    global last_id

    last_id = init_last_id()

    loop = asyncio.get_running_loop()

    print("")
    print("MESHTASTIC DATABASE LISTENER")
    print("---------------------------")
    print("Database:", DB_FILE)
    print("WebSocket porta:", WS_PORT)
    print("Buffer messaggi:", MESSAGE_BUFFER)
    print("")

    server = await websockets.serve(
        ws_handler,
        "0.0.0.0",
        WS_PORT,
        ping_interval=20,
        ping_timeout=20
    )

    asyncio.create_task(db_watcher())

    await server.wait_closed()


asyncio.run(main())

