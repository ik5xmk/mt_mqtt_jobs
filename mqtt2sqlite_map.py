#!/usr/bin/env python3
import json
import sqlite3
import time
import paho.mqtt.client as mqtt

# --- Configurazione MQTT ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = "ILTUOUSER"
MQTT_PASSWORD = "LATUAPASSWORD"
ROOT_TOPIC = "msh/EU_868/#"
CLIENT_ID = "99998888"

# --- Configurazione Database ---
DB_FILE = "meshtastic_nodes2.db"
MAX_NODES = 1000
MAX_NODE_AGE_HOURS = 48

# --- Funzioni Database ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Tabella informazioni nodo
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            from_id INTEGER PRIMARY KEY,
            node_id TEXT,
            longname TEXT,
            shortname TEXT,
            hardware INTEGER,
            role INTEGER,
            last_seen INTEGER
        )
    """)

    # Tabella posizioni
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            from_id INTEGER PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            precision_bits INTEGER,
            timestamp INTEGER,
            rssi REAL,
            snr REAL,
            FOREIGN KEY(from_id) REFERENCES nodes(from_id)
        )
    """)

    # Tabella Telemetria1
    c.execute("""
        CREATE TABLE IF NOT EXISTS telemetry1 (
            from_id INTEGER PRIMARY KEY,
            temperature REAL,
            relative_humidity REAL,
            barometric_pressure REAL,
            lux REAL,
            white_lux REAL,
            gas_resistance REAL,
            iaq REAL,
            radiation REAL,
            wind_speed REAL,
            wind_gust REAL,
            wind_lull REAL,
            wind_direction REAL,
            voltage REAL,
            current REAL,
            timestamp INTEGER,
            FOREIGN KEY(from_id) REFERENCES nodes(from_id)
        )
    """)

    # Tabella Telemetria2
    c.execute("""
        CREATE TABLE IF NOT EXISTS telemetry2 (
            from_id INTEGER PRIMARY KEY,
            voltage REAL,
            battery_level REAL,
            air_util_tx REAL,
            channel_utilization REAL,
            uptime_seconds INTEGER,
            rssi REAL,
            snr REAL,
            timestamp INTEGER,
            FOREIGN KEY(from_id) REFERENCES nodes(from_id)
        )
    """)

    conn.commit()
    conn.close()


def cleanup_old_nodes(c):
    c.execute("SELECT COUNT(*) FROM nodes")
    count = c.fetchone()[0]
    if count > MAX_NODES:
        to_delete = count - MAX_NODES
        print(f"[INFO] ⚠️  Limite {MAX_NODES} superato, rimuovo {to_delete} nodi più vecchi...")
        c.execute("DELETE FROM nodes WHERE from_id IN (SELECT from_id FROM nodes ORDER BY last_seen ASC LIMIT ?)", (to_delete,))
        c.execute("DELETE FROM positions WHERE from_id NOT IN (SELECT from_id FROM nodes)")
        c.execute("DELETE FROM telemetry1 WHERE from_id NOT IN (SELECT from_id FROM nodes)")
        c.execute("DELETE FROM telemetry2 WHERE from_id NOT IN (SELECT from_id FROM nodes)")


def cleanup_expired_records(c):
    cutoff_time = int(time.time()) - (MAX_NODE_AGE_HOURS * 3600)
    c.execute("SELECT COUNT(*) FROM nodes WHERE last_seen < ?", (cutoff_time,))
    old_nodes = c.fetchone()[0]
    if old_nodes > 0:
        print(f"[INFO] 🕒 Rimozione di {old_nodes} nodi più vecchi di {MAX_NODE_AGE_HOURS} ore...")

    for table in ("positions", "telemetry1", "telemetry2"):
        c.execute(f"DELETE FROM {table} WHERE from_id IN (SELECT from_id FROM nodes WHERE last_seen < ?)", (cutoff_time,))
    c.execute("DELETE FROM nodes WHERE last_seen < ?", (cutoff_time,))


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
        INSERT INTO nodes (from_id, node_id, longname, shortname, hardware, role, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_id) DO UPDATE SET
            node_id=excluded.node_id,
            longname=excluded.longname,
            shortname=excluded.shortname,
            hardware=excluded.hardware,
            role=excluded.role,
            last_seen=excluded.last_seen
    """, (from_id, node_id, longname, shortname, hardware, role, last_seen))

    cleanup_old_nodes(c)
    cleanup_expired_records(c)
    conn.commit()
    conn.close()


def save_position(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    from_id = data.get("from")
    payload = data.get("payload", {})

    lat = payload.get("latitude_i", 0) / 1e7
    lon = payload.get("longitude_i", 0) / 1e7
    alt = payload.get("altitude")
    precision = payload.get("precision_bits")
    ts = payload.get("time", int(time.time()))
    rssi = data.get("rssi")
    snr = data.get("snr")

    c.execute("""
        INSERT INTO positions (from_id, latitude, longitude, altitude, precision_bits, timestamp, rssi, snr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_id) DO UPDATE SET
            latitude=excluded.latitude,
            longitude=excluded.longitude,
            altitude=excluded.altitude,
            precision_bits=excluded.precision_bits,
            timestamp=excluded.timestamp,
            rssi=excluded.rssi,
            snr=excluded.snr
    """, (from_id, lat, lon, alt, precision, ts, rssi, snr))

    cleanup_old_nodes(c)
    cleanup_expired_records(c)
    conn.commit()
    conn.close()


def save_telemetry1(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    from_id = data.get("from")
    p = data.get("payload", {})
    ts = data.get("timestamp", int(time.time()))

    c.execute("""
        INSERT INTO telemetry1 (from_id, temperature, relative_humidity, barometric_pressure, lux, white_lux, gas_resistance, iaq, radiation,
                                wind_speed, wind_gust, wind_lull, wind_direction, voltage, current, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_id) DO UPDATE SET
            temperature=excluded.temperature,
            relative_humidity=excluded.relative_humidity,
            barometric_pressure=excluded.barometric_pressure,
            lux=excluded.lux,
            white_lux=excluded.white_lux,
            gas_resistance=excluded.gas_resistance,
            iaq=excluded.iaq,
            radiation=excluded.radiation,
            wind_speed=excluded.wind_speed,
            wind_gust=excluded.wind_gust,
            wind_lull=excluded.wind_lull,
            wind_direction=excluded.wind_direction,
            voltage=excluded.voltage,
            current=excluded.current,
            timestamp=excluded.timestamp
    """, (from_id, p.get("temperature"), p.get("relative_humidity"), p.get("barometric_pressure"), p.get("lux"),
          p.get("white_lux"), p.get("gas_resistance"), p.get("iaq"), p.get("radiation"), p.get("wind_speed"),
          p.get("wind_gust"), p.get("wind_lull"), p.get("wind_direction"), p.get("voltage"), p.get("current"), ts))

    cleanup_old_nodes(c)
    cleanup_expired_records(c)
    conn.commit()
    conn.close()


def save_telemetry2(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    from_id = data.get("from")
    p = data.get("payload", {})
    ts = data.get("timestamp", int(time.time()))
    rssi = data.get("rssi")
    snr = data.get("snr")

    c.execute("""
        INSERT INTO telemetry2 (from_id, voltage, battery_level, air_util_tx, channel_utilization, uptime_seconds, rssi, snr, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(from_id) DO UPDATE SET
            voltage=excluded.voltage,
            battery_level=excluded.battery_level,
            air_util_tx=excluded.air_util_tx,
            channel_utilization=excluded.channel_utilization,
            uptime_seconds=excluded.uptime_seconds,
            rssi=excluded.rssi,
            snr=excluded.snr,
            timestamp=excluded.timestamp
    """, (from_id, p.get("voltage"), p.get("battery_level"), p.get("air_util_tx"), p.get("channel_utilization"),
          p.get("uptime_seconds"), rssi, snr, ts))

    cleanup_old_nodes(c)
    cleanup_expired_records(c)
    conn.commit()
    conn.close()


# --- Funzioni MQTT ---
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[OK] Connesso a MQTT {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(ROOT_TOPIC)
        print(f"[INFO] In ascolto su topic: {ROOT_TOPIC}")
    else:
        print(f"[ERRORE] Connessione MQTT fallita, codice {reason_code}")


def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8", errors="replace")
        data = json.loads(payload_str)
        tipo = data.get("type")

        if tipo == "position":
            save_position(data)
            print(f"[POS]  Nodo {data['from']} → posizione aggiornata.")
        elif tipo == "nodeinfo":
            save_nodeinfo(data)
            print(f"[INFO] Nodo {data['from']} → informazioni aggiornate.")
        elif tipo == "telemetry":
            payload = data.get("payload", {})
            if "barometric_pressure" in payload:
                save_telemetry1(data)
                print(f"[TEL1] Nodo {data['from']} → telemetria1 aggiornata.")
            elif "battery_level" in payload:
                save_telemetry2(data)
                print(f"[TEL2] Nodo {data['from']} → telemetria2 aggiornata.")

    except Exception:
        pass


def main():
    print("[INIT] Avvio ricezione dati Meshtastic → MQTT → SQLite")
    init_db()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print("[START] In ascolto su broker MQTT...\n")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Terminato dall'utente.")
    except Exception as e:
        print(f"[ERRORE] Loop MQTT interrotto: {e}")


if __name__ == "__main__":
    main()
