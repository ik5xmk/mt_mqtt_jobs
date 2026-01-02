The mqtt2sqlite_msg program reads meshtastic messages arriving on an MQTT server, in json format and with a specific topic, and stores them in a sqlite3 database.<br>
The MQTT server must be running (see various guides online for installing it on your distro), and the meshtastic LORA cards must be configured to send data to the MQTT server on port 1883.<br>
Make sure the MQTT server allows access to this port and create a login user and password to enter in the LORA cards' configuration.<br>
The mqtt2sqlite_msg program acts as a client and intercepts messages in transit. It must always be active in the background.<br><br>
