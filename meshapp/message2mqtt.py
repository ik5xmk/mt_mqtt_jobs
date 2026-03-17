#!/usr/bin/env python3

import time
import random
import argparse
import paho.mqtt.client as mqtt

# ===== Meshtastic protobuf =====
try:
    from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2
    from meshtastic import BROADCAST_NUM # BROADCAST_NUM = 0xFFFFFFFF = 4294967295 (-1 in JSON)
except ImportError:
    from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, BROADCAST_NUM

import json
from google.protobuf.json_format import MessageToDict

# ============================================================
# CONFIGURAZIONE
# ============================================================

MQTT_HOST = "192.168.2.198"
MQTT_USER = "user"
MQTT_PASS = "password"
MQTT_PORT = 1883

REGION = "EU_868"
CHANNEL_INDEX = 2            # deve rimanere 2, è un routing level interno del gateway MQTT
CHANNEL_NAME  = "MediumFast" # nome canale ove trasmettere es. Toscana 
NODE_ID_HEX   = "aaaa1111"   # 8 char HEX (inviare prima un pacchetto info altrimenti compare UNK)
LONG_NAME     = "Nodo virtuale solo software"
SHORT_NAME    = "NVSW"
MAX_MSG_LEN   = mesh_pb2.Constants.DATA_PAYLOAD_LEN # vedi protobufs mesh.proto è una costante di 233

# NodeInfo fields
HW_MODEL          = 255 # private hw
# https://github.com/meshtastic/protobufs/blob/master/meshtastic/config.proto#L21
ROLE              = 1 # CLIENT_MUTE
IS_LICENSED       = False
NON_MESSAGGIABILE = True
VIA_MQTT          = True

# ============================================================
# DEBUG PROTOBUF in JSON
# ============================================================

def debug_print_envelope(payload_bytes):

    env = mqtt_pb2.ServiceEnvelope()
    env.ParseFromString(payload_bytes)

    pkt = env.packet

    output = {
        "service_envelope": {
            "channel_id": env.channel_id,
            "gateway_id": env.gateway_id,
        },
        "mesh_packet": {
            "id": pkt.id,
            "from": getattr(pkt, "from"),
            "to": pkt.to,
            "channel": pkt.channel,
            "hop_limit": pkt.hop_limit,
            "hop_start": pkt.hop_start,
            "want_ack": pkt.want_ack,
        }
    }

    # Decoded data
    if pkt.HasField("decoded"):
        data = pkt.decoded
        output["mesh_packet"]["decoded"] = {
            "portnum": data.portnum,
            "bitfield": data.bitfield,
        }

        # TEXT MESSAGE
        if data.portnum == portnums_pb2.TEXT_MESSAGE_APP:
            output["mesh_packet"]["decoded"]["text"] = data.payload.decode("utf-8", errors="ignore")

        # NODE INFO
        elif data.portnum == portnums_pb2.NODEINFO_APP:
            user = mesh_pb2.User()
            user.ParseFromString(data.payload)
            output["mesh_packet"]["decoded"]["user"] = MessageToDict(user, preserving_proto_field_name=True)

    print("JSON_DEBUG_START")
    print(json.dumps(output, indent=2))
    print("JSON_DEBUG_END")

def debug_print_raw_hex(payload_bytes):
    print("HEX_DEBUG_START")
    print(" ".join(hexstr[i:i+2] for i in range(0, len(hexstr), 2)))
    print("HEX_DEBUG_END")


# ============================================================
# TOPIC MQTT (/e/ API2)
# ============================================================

def build_topic():
    # esempio: msh/US/2/e/LongFast/!abcd1234
    return f"msh/{REGION}/{CHANNEL_INDEX}/e/{CHANNEL_NAME}/!{NODE_ID_HEX}"

def build_json_topic():
    return f"msh/{REGION}/{CHANNEL_INDEX}/json/{CHANNEL_NAME}/!{NODE_ID_HEX}"

# ============================================================
# BUILD JSON TEXT MESSAGE
# ============================================================

def build_json_text(text):

    node_dec = int(NODE_ID_HEX, 16)

    return {
        "channel": 0,
        "from": node_dec,
        "payload": {
            "text": text
        },
        "sender": f"!{NODE_ID_HEX}",
        "to": BROADCAST_NUM,
        "type": "text"
    }


# ============================================================
# BUILD JSON NODEINFO
# ============================================================

def build_json_nodeinfo():

    node_dec = int(NODE_ID_HEX, 16)

    return {
        "channel": 0,
        "from": node_dec,
        "payload": {
            "hardware": HW_MODEL,
            "id": f"!{NODE_ID_HEX}",
            "longname": LONG_NAME,
            "shortname": SHORT_NAME
        },
        "sender": f"!{NODE_ID_HEX}",
        "timestamp": int(time.time()),
        "to": BROADCAST_NUM,
        "type": "nodeinfo"
    }


# ============================================================
# BUILD TEXT MESSAGE (decoded, NO encryption)
# ============================================================

def build_text_packet(text: str):

    node_dec = int(NODE_ID_HEX, 16)
    packet_id = random.randint(1, 0xFFFFFFFF)

    if len(text.encode("utf-8")) > MAX_MSG_LEN:
        text = text.encode("utf-8")[:MAX_MSG_LEN].decode("utf-8", errors="ignore")

    # Data payload
    data = mesh_pb2.Data()
    data.portnum = portnums_pb2.TEXT_MESSAGE_APP
    data.payload = text.encode("utf-8")
    data.bitfield = 1

    # MeshPacket
    pkt = mesh_pb2.MeshPacket()
    pkt.id = packet_id
    setattr(pkt, "from", node_dec)
    pkt.to = BROADCAST_NUM
    pkt.want_ack = False
    pkt.hop_limit = 3
    pkt.hop_start = 3
    pkt.decoded.CopyFrom(data)
    pkt.channel = CHANNEL_INDEX

    # ServiceEnvelope
    env = mqtt_pb2.ServiceEnvelope()
    env.packet.CopyFrom(pkt)
    env.channel_id = CHANNEL_NAME
    env.gateway_id = f"!{NODE_ID_HEX}"

    return env.SerializeToString()


# ============================================================
# BUILD NODE INFO (decoded)
# ============================================================

def build_nodeinfo_packet():

    """

Questo è il formato JSON che Meshtastic produce quando:

Riceve il pacchetto
Lo interpreta
Lo converte in oggetto interno
Lo pubblica su topic /json/

{
  "id": 452664778,
  "channel": 0,
  "from": 2130636288,
  "payload": {
    "hardware": 10,
    "id": "!7efeee00",
    "longname": "base0",
    "shortname": "BA0"
  },
  "sender": "!7efeee00",
  "timestamp": 1646832724,
  "to": -1,
  "type": "nodeinfo"
}

Manca timestamp, type, sender nella mia trasmissione perché nel protobuf:
- timestamp: NON lo aggiunge il nodo ricevente
- sender: NON esiste nel MeshPacket ma è calcolato dall'app
- type: nodeinfo NON è un campo protobuf ma è una semplificazione JSON

    """

    node_dec = int(NODE_ID_HEX, 16)
    packet_id = random.randint(1, 0xFFFFFFFF)

    # User structure (viene inserito nel payload data)
    user = mesh_pb2.User()
    user.id = f"!{NODE_ID_HEX}"
    user.long_name = LONG_NAME
    user.short_name = SHORT_NAME
    user.hw_model = HW_MODEL
    user.is_licensed = IS_LICENSED
    user.is_unmessagable = NON_MESSAGGIABILE
    user.role = ROLE

    # Data wrapper (viene inserito nel pacchetto) - pkt
    data = mesh_pb2.Data()
    data.portnum = portnums_pb2.NODEINFO_APP
    data.payload = user.SerializeToString()
    data.bitfield = 1

    # MeshPacket (viene imbustato nel service envelope)
    pkt = mesh_pb2.MeshPacket() # vedi protobuf mesh.proto
    pkt.id = packet_id
    setattr(pkt, "from", node_dec)
    pkt.to = BROADCAST_NUM
    pkt.want_ack = False
    pkt.hop_limit = 3
    pkt.hop_start = 3
    pkt.decoded.CopyFrom(data)
    pkt.channel = CHANNEL_INDEX
    pkt.via_mqtt = VIA_MQTT

    # ServiceEnvelope (ultimo stadio di preparazione)
    env = mqtt_pb2.ServiceEnvelope()
    env.packet.CopyFrom(pkt)
    env.channel_id = CHANNEL_NAME
    env.gateway_id = f"!{NODE_ID_HEX}"

    return env.SerializeToString()


# ============================================================
# MQTT CALLBACK
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connesso MQTT")
        client.connected_flag = True
    else:
        print(f"Errore connessione MQTT: {reason_code}")


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(description="Meshtastic MQTT sender by IK5XMK")
    parser.add_argument("message", nargs="?", help="Testo da inviare")
    parser.add_argument("-i", "--info", action="store_true", help="Invia Node Info")
    args = parser.parse_args()

    if not args.info and not args.message:
        parser.error("Specificare un messaggio oppure usare -i")

    topic = build_topic()
    json_topic = build_json_topic()

    if args.info:
        print("Invio Node Info")
        payload = build_nodeinfo_packet()
        json_payload = build_json_nodeinfo()
    else:
        print("Invio Text Message")
        payload = build_text_packet(args.message)
        json_payload = build_json_text(args.message)

    # DEBUG JSON OUTPUT
    debug_print_envelope(payload)

    #debug_print_raw_hex(payload)


    mqtt.Client.connected_flag = False
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    # print(f"Connessione a {MQTT_HOST}...")
    print(f"Connessione a server MQTT...")

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    timeout = 5
    start = time.time()
    while not client.connected_flag and time.time() - start < timeout:
        time.sleep(0.1)

    if not client.connected_flag:
        print("Timeout connessione MQTT")
        return

    print(f"Invio su topic protobuf: {topic}")
    client.publish(topic, payload, qos=0)

    print(f"Invio su topic json: {json_topic}")
    client.publish(json_topic, json.dumps(json_payload), qos=0)

    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()
    print("Messaggio inviato")


if __name__ == "__main__":
    main()
