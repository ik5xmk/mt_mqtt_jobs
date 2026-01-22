#!/usr/bin/env python3
import sqlite3
import folium
import os
from datetime import datetime
from geopy.distance import geodesic

# === CONFIGURAZIONE ===
DB_FILE = "/home/david/meshtastic_nodes2.db"
MAP_FILE = "/var/www/html/fullmap.html"

CENTER_LAT = 43.7696
CENTER_LON = 11.2558
ZOOM_START = 10
RADIUS = 100  # km
LAST_SEEN = 12  # ore massime accettate

# === FUNZIONI DB ===
def get_nodes_with_positions():
    """Restituisce nodi con posizione, nodeinfo e telemetria se presenti."""
    if not os.path.exists(DB_FILE):
        print(f"[ERRORE] Database '{DB_FILE}' non trovato.")
        return []

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            n.from_id,
            n.longname,
            n.shortname,
            p.latitude,
            p.longitude,
            p.altitude,
            p.timestamp
        FROM nodes n
        LEFT JOIN positions p ON n.from_id = p.from_id
        ORDER BY n.last_seen DESC
    """)
    nodes = cur.fetchall()

    # Recupera telemetrie in dizionari
    cur.execute("SELECT * FROM telemetry1")
    telem1 = {r[0]: r[1:] for r in cur.fetchall()}  # key = from_id

    cur.execute("SELECT * FROM telemetry2")
    telem2 = {r[0]: r[1:] for r in cur.fetchall()}

    conn.close()
    return nodes, telem1, telem2

# === GESTIONE VALORI IAQ ===
def iaq_icon_label(iaq):
    """Ritorna tuple (icon, label) in base al valore IAQ."""
    try:
        iaq = float(iaq)
    except (TypeError, ValueError):
        return "❓", "IAQ: n.d."

    if iaq <= 50:
        return "🟢", f"IAQ: {iaq:.0f} (Buona)"
    elif iaq <= 100:
        return "🟡", f"IAQ: {iaq:.0f} (Moderata)"
    elif iaq <= 150:
        return "🟠", f"IAQ: {iaq:.0f} (Scarsa)"
    else:
        return "🔴", f"IAQ: {iaq:.0f} (Attenzionare)"

# === CALCOLA QNH ===
def calcola_qnh(pressione_hpa, alt_m, temp_C):
    """
    Calcola la pressione relativa al livello del mare (QNH)
    partendo da pressione assoluta, altitudine e temperatura ambiente.

    Formula termocorretta:
        QNH = P * (1 - (0.0065 * h) / (T + 273.15 + (0.0065 * h / 2))) ** -5.255

    :param pressione_hpa: pressione assoluta in hPa
    :param alt_m: altitudine in metri
    :param temp_C: temperatura in °C
    :return: QNH in hPa (arrotondato a 1 decimale)
    """
    if pressione_hpa <= 0:
        return None  # valore non valido

    temp_K = temp_C + 273.15
    qnh = pressione_hpa * (1 - (0.0065 * alt_m) / (temp_K + (0.0065 * alt_m / 2))) ** -5.255
    return round(qnh, 1)

# === GENERAZIONE MAPPA ===
def generate_map(nodes, telem1, telem2):
    m = folium.Map(location=[CENTER_LAT, CENTER_LON], zoom_start=ZOOM_START)
    center_point = (CENTER_LAT, CENTER_LON)

    folium.Circle(
        location=center_point,
        radius=RADIUS * 1000,
        color="green",
        fill=True,
        fill_opacity=0.1,
        popup=f"Raggio di {RADIUS} km"
    ).add_to(m)

    count_total = 0
    count_green = 0  # con telemetria
    count_blue = 0   # con nome ma senza telemetria
    count_yellow = 0 # senza nome

    now = datetime.now().timestamp()

    for from_id, longname, shortname, lat, lon, alt, ts in nodes:
        if lat is None or lon is None:
            continue  # senza posizione non va in mappa

        # Età posizione
        if ts is None or (now - ts) > LAST_SEEN * 3600:
            continue # dati vecchi non vanno in mappa

        distance_km = geodesic(center_point, (lat, lon)).km
        if distance_km > RADIUS:
            continue # sono nodi lontani quindi non vanno in mappa

        popup_lines = []
        title = longname or shortname or str(from_id)
        popup_lines.append(f"<b>{title}</b>")

        if alt is not None:
            popup_lines.append(f"Altitudine: {alt} m")

        popup_lines.append(f"Aggiornato: {datetime.fromtimestamp(ts).strftime('%H:%M:%S %d-%m-%Y')}")

        # Telemetria disponibile?
        t1 = telem1.get(from_id)
        t2 = telem2.get(from_id)

        if t1 or t2:
            popup_lines.append("<hr><b>Telemetria:</b>")
            if t1:
                (temperature, rh, pressure, lux, white, gas, iaq, radiation,
                 wind_speed, gust, lull, direction, voltage, current, ts1) = t1
                if (temperature is not None) and (temperature != 0): popup_lines.append(f"🌡️ Temp: {temperature:.2f} °C")
                if (rh is not None) and (rh != 0): popup_lines.append(f"💧 Umidità: {rh:.2f} %")
                if (pressure is not None) and (pressure != 0): popup_lines.append(f"⛰️ Pressione: {pressure:.2f} hPa")

                # calcolo QNH
                if (alt is not None) and (pressure is not None) and (temperature is not None):
                    qnh = calcola_qnh(pressure, alt, temperature)
                    popup_lines.append(f"📈 QNH: {qnh} hPa")

                if (lux is not None) and (lux != 0): popup_lines.append(f"💡 Lux: {lux}")
                icon, label = iaq_icon_label(iaq)
                popup_line = f"{icon} {label}"
                if (iaq is not None) and (iaq != 0): popup_lines.append(popup_line) # (f"IAQ: {iaq}")
                if (wind_speed is not None) and (wind_speed != 0): popup_lines.append(f"💨 Vento: {wind_speed} m/s ({direction}°)")
                if (voltage is not None) and (voltage != 0): popup_lines.append(f"🔋 Tensione(t1): {voltage:.2f} V")

            if t2:
                (voltage2, batt, tx, util, uptime, rssi, snr, ts2) = t2
                if (voltage2 is not None) and (voltage2 > 0): popup_lines.append(f"🔋 Tensione(t2): {voltage2:.2f} V")
                if (batt is not None) and (batt <= 100): popup_lines.append(f"🔋 Batteria: {batt} %")
                # if rssi is not None: popup_lines.append(f"📶 RSSI: {rssi} dBm")
                # if snr is not None: popup_lines.append(f"SNR: {snr} dB")

            color = "green"
            count_green += 1
        else:
            if longname or shortname:
                color = "blue"
                count_blue += 1
            else:
                color = "yellow"
                count_yellow += 1

        popup_html = "<br>".join(popup_lines)
        iframe = folium.IFrame(popup_html)
        popup_box = folium.Popup(iframe, max_width=370, min_width=370)

        folium.Marker(
            location=[lat, lon],
            popup=popup_box,
            tooltip=title,
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(m)

        count_total += 1

    os.makedirs(os.path.dirname(MAP_FILE), exist_ok=True)
    m.save(MAP_FILE)

    print(f"\n[OK] Mappa generata: {MAP_FILE}")
    print(f"   Totale nodi visualizzati: {count_total}")
    print(f"   🔵 Con posizione + nome: {count_blue}")
    print(f"   🟢 Con posizione + telemetria: {count_green}")
    print(f"   🟡 Con posizione ma senza nome: {count_yellow}\n")

# === MAIN ===
if __name__ == "__main__":
    nodes, telem1, telem2 = get_nodes_with_positions()
    if nodes:
        generate_map(nodes, telem1, telem2)
    else:
        print("[INFO] Nessun nodo trovato nel database.")
