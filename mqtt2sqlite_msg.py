#!/usr/bin/env python3
import json
import sqlite3
import time
import paho.mqtt.client as mqtt

# === CONFIGURAZIONE MQTT ===
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = "ILTUOUSER"
MQTT_PASSWORD = "LATUAPASSWORD"
ROOT_TOPIC = "msh/EU_868/#"
CLIENT_ID = "meshtastic_logger"

# === CONFIGURAZIONE DATABASE ===
DB_FILE = "meshtastic_messages.db"
MAX_MESSAGES = 1000        # Numero massimo di messaggi da conservare
MAX_DAYS = 30              # Giorni massimi di conservazione messaggi

# === FILTRO DUPLICATI ===
DUPLICATE_WINDOW = 10      # Secondi entro cui considerare due messaggi duplicati
FILTER_BY_SENDER = True    # True = esclude duplicati anche per stesso sender
FILTER_BY_NODE = True      # True = esclude duplicati anche per stesso nodo


# --- Inizializzazione del database ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Tabella nodi (univoca per from_id)
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            from_id INTEGER PRIMARY KEY,
            longname TEXT,
            shortname TEXT,
            hardware INTEGER,
            role INTEGER,
            node_id TEXT,
            last_seen INTEGER
        )
    """)

    # Tabella messaggi (completa con tutti i campi rilevanti)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id INTEGER,
            channel INTEGER,
            text TEXT,
            timestamp INTEGER,
            hop_start INTEGER,
            hops_away INTEGER,
            msg_id INTEGER,
            sender TEXT,
            to_id INTEGER,
            rssi REAL,
            snr REAL,
            FOREIGN KEY(from_id) REFERENCES nodes(from_id)
        )
    """)

    conn.commit()
    conn.close()


# --- Pulizia automatica del database ---
def cleanup_old_messages(c):
    cutoff_time = int(time.time()) - (MAX_DAYS * 24 * 3600)
    c.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff_time,))

    c.execute("SELECT COUNT(*) FROM messages")
    count = c.fetchone()[0]
    if count > MAX_MESSAGES:
        to_delete = count - MAX_MESSAGES
        print(f"[INFO] ⚠️  Rimuovo {to_delete} messaggi più vecchi per mantenere il limite di {MAX_MESSAGES}.")
        c.execute("""
            DELETE FROM messages WHERE id IN (
                SELECT id FROM messages ORDER BY timestamp ASC LIMIT ?
            )
        """, (to_delete,))


# --- Controllo duplicati ---
def is_duplicate(c, from_id, sender, text, timestamp):
    """
    Restituisce True se il messaggio è un duplicato recente.
    Il controllo è fatto su 'text', 'from_id' e/o 'sender' entro DUPLICATE_WINDOW secondi.
    """
    since_time = timestamp - DUPLICATE_WINDOW

    if FILTER_BY_SENDER and FILTER_BY_NODE:
        c.execute("""
            SELECT COUNT(*) FROM messages
            WHERE text=? AND timestamp>=? AND (from_id=? OR sender=?)
        """, (text, since_time, from_id, sender))
    elif FILTER_BY_SENDER:
        c.execute("""
            SELECT COUNT(*) FROM messages
            WHERE text=? AND timestamp>=? AND sender=?
        """, (text, since_time, sender))
    elif FILTER_BY_NODE:
        c.execute("""
            SELECT COUNT(*) FROM messages
            WHERE text=? AND timestamp>=? AND from_id=?
        """, (text, since_time, from_id))
    else:
        return False

    return c.fetchone()[0] > 0


# --- Salvataggio informazioni nodo ---
def save_nodeinfo(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    from_id = data.get("from")
    payload = data.get("payload", {})
    longname = payload.get("longname")
    shortname = payload.get("shortname")
    hardware = payload.get("hardware")
    role = payload.get("role")
    node_id = payload.get("id")
    last_seen = int(time.time())

    c.execute("""
        INSERT INTO nodes (from_id, longname, shortname, hardware, role, node_id, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_id) DO UPDATE SET
            longname=excluded.longname,
            shortname=excluded.shortname,
            hardware=excluded.hardware,
            role=excluded.role,
            node_id=excluded.node_id,
            last_seen=excluded.last_seen
    """, (from_id, longname, shortname, hardware, role, node_id, last_seen))

    conn.commit()
    conn.close()


# --- Salvataggio messaggi ---
def save_message(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    from_id = data.get("from")
    channel = data.get("channel")
    payload = data.get("payload", {})
    text = payload.get("text", "")
    timestamp = data.get("timestamp", int(time.time()))
    hop_start = data.get("hop_start")
    hops_away = data.get("hops_away")
    msg_id = data.get("id")
    sender = data.get("sender")
    to_id = data.get("to")
    rssi = data.get("rssi")
    snr = data.get("snr")

    # Controllo duplicati
    if is_duplicate(c, from_id, sender, text, timestamp):
        print(f"[DUPLICATO] Messaggio ignorato da {from_id} / {sender}: \"{text}\"")
        conn.close()
        return

    c.execute("""
        INSERT INTO messages (
            from_id, channel, text, timestamp,
            hop_start, hops_away, msg_id, sender, to_id, rssi, snr
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (from_id, channel, text, timestamp, hop_start, hops_away, msg_id, sender, to_id, rssi, snr))

    cleanup_old_messages(c)

    conn.commit()
    conn.close()


# --- Gestione connessione MQTT ---
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[OK] Connesso a {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(ROOT_TOPIC)
        print(f"[INFO] Sottoscritto al topic: {ROOT_TOPIC}")
    else:
        print(f"[ERRORE] Connessione MQTT fallita (codice {reason_code})")


# --- Gestione messaggi MQTT ---
def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8", errors="replace")
        data = json.loads(payload_str)
        tipo = data.get("type")

        if tipo == "nodeinfo":
            save_nodeinfo(data)
            print(f"[NODEINFO] Canale {data.get('channel')} | FROM {data.get('from')} → Nodo aggiornato.")
        elif tipo == "text":
            save_message(data)
            testo = data.get("payload", {}).get("text", "")
            print(f"[TEXT] Canale {data.get('channel')} | FROM {data.get('from')} → \"{testo}\"")
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[ERRORE] {e}")


# --- Main ---
def main():
    print("[INIT] Avvio ricezione Meshtastic → MQTT → SQLite")
    print(f"[CONF] Limite messaggi: {MAX_MESSAGES}, conservazione: {MAX_DAYS} giorni")
    print(f"[CONF] Finestra duplicati: {DUPLICATE_WINDOW}s (sender={FILTER_BY_SENDER}, node={FILTER_BY_NODE})")
    init_db()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print("[START] In ascolto su broker MQTT...\n")
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Terminato dall’utente.")
    except Exception as e:
        print(f"[ERRORE] Loop MQTT interrotto: {e}")


if __name__ == "__main__":
    main()
