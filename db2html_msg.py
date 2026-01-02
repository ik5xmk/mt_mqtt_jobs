#!/usr/bin/env python3
import sqlite3
from datetime import datetime
import os

# === CONFIGURAZIONE ===
DB_PATH = "/home/david/meshtastic_messages.db"
OUTPUT_HTML = "/var/www/html/messages.html"
REFRESH_SECONDS = 30         # intervallo aggiornamento automatico in secondi
MAX_MESSAGES = 50            # numero massimo di messaggi da mostrare (default 50)
CHANNEL_FILTER = None        # es: 0 per canale specifico, None per tutti

# Mappa etichette canali
CHANNEL_LABELS = {
    0: "Primary",
    1: "Toscana",
    2: "Interno"
}

# === HTML HEADER (Bootstrap 5 + Auto Refresh) ===
HTML_HEADER = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="{REFRESH_SECONDS}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Messaggi Meshtastic</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{
            background-color: #f8f9fa;
            padding: 30px;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 30px;
        }}
        table {{
            table-layout: auto;
            width: 100%;
        }}
        th, td {{
            text-align: center;
            vertical-align: middle;
            word-wrap: break-word;
            max-width: 400px;
        }}
        tbody tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        .container {{
            max-width: 95%;
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>📡 Messaggi Ricevuti - Meshtastic</h1>
    <p class="text-center text-muted">
        Filtro visualizzazione: {MAX_MESSAGES} messaggi più recenti
        {f"dal canale {CHANNEL_FILTER}" if CHANNEL_FILTER is not None else "(tutti i canali)"}
    </p>
    <div class="table-responsive">
        <table class="table table-striped table-bordered table-hover align-middle">
            <thead class="table-dark">
                <tr>
                    <th>Canale</th>
                    <th>Da</th>
                    <th>in MQTT</th>
                    <th>Salti tot/usati</th>
                    <th>Messaggio</th>
                    <th>Orario</th>
                </tr>
            </thead>
            <tbody>
"""

HTML_FOOTER = """            </tbody>
        </table>
    </div>
    <p class="text-center text-muted mt-3">
        by David IK5XMK<br>
        Dati provenienti dal server MQTT/GRF e salvati nel database
    </p>
</div>
</body>
</html>
"""

def generate_html():
    """Genera la pagina HTML con i messaggi dal database Meshtastic."""
    if not os.path.exists(DB_PATH):
        print(f"[ERRORE] Database non trovato: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Costruisce la query dinamicamente in base al filtro canale
    base_query = """
        SELECT
            m.channel,
            n.longname,
            m.from_id,
            m.text,
            m.timestamp,
            m.sender,
            m.hop_start,
            m.hops_away
        FROM messages AS m
        LEFT JOIN nodes AS n ON m.from_id = n.from_id
    """
    params = []

    if CHANNEL_FILTER is not None:
        base_query += " WHERE m.channel = ?"
        params.append(CHANNEL_FILTER)

    base_query += " ORDER BY m.timestamp DESC LIMIT ?"
    params.append(MAX_MESSAGES)

    try:
        cur.execute(base_query, params)
    except sqlite3.OperationalError as e:
        print(f"[ERRORE SQL] {e}")
        conn.close()
        return

    rows = cur.fetchall()
    conn.close()

    html_rows = ""
    for channel, longname, from_id, text, timestamp, sender, hop_start, hops_away in rows:
        # Etichetta canale (fallback al numero se non presente in mappa)
        channel_label = CHANNEL_LABELS.get(channel, str(channel))

        nodo = longname if longname else f"Nodo: {from_id}"
        dt = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S - %d/%m/%Y") if timestamp else "N/D"
        hops = f"{hop_start}/{hops_away}" if hop_start is not None and hops_away is not None else "-"
        sender_display = sender if sender else "-"

        html_rows += f"""
            <tr>
                <td>{channel_label}</td>
                <td>{nodo}</td>
                <td>{sender_display}</td>
                <td>{hops}</td>
                <td>{text}</td>
                <td>{dt}</td>
            </tr>
        """

    # Scrive il file HTML
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(HTML_HEADER + html_rows + HTML_FOOTER)

    print(f"[OK] Pagina generata: {OUTPUT_HTML} ({len(rows)} messaggi mostrati)")

if __name__ == "__main__":
    generate_html()
