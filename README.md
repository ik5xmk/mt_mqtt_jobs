The mqtt2sqlite_msg program reads meshtastic messages arriving on an MQTT server, <strong>in json format and with a specific topic</strong>, and stores them in a sqlite3 database. 
The MQTT server must be running (see various guides online for installing it on your distro), and the meshtastic LORA cards must be configured to send data to the MQTT server on port 1883. Make sure the MQTT server allows access to this port and create a login user and password to enter in the LORA cards' configuration.<br><br>
![](https://github.com/ik5xmk/mt_mqtt_jobs/blob/main/mqtt_meshtastic_configuration.jpg)<br>
The mqtt2sqlite_msg program acts as a client and intercepts messages in transit. <strong>It must always be active in the background.</strong><br><br>
![](https://github.com/ik5xmk/mt_mqtt_jobs/blob/main/mqtt_sample_frames_in_json.jpg)<br>
<strong>The db2html_msg program can be run as a cron job</strong>. Its function is to extract a certain number of messages from the database and display them in a specially created HTML page.
In the configuration code, you must specify the database path and where the page should be created (usually a path within the existing web server).
You can also specify which channels to display, thus offering the possibility of having different pages for each meshtastic channel (the messages in the database are from all the channels configured on the lora cards). The code and HTML page are very simple, making it easy to customize.
These Python programs require libraries that must be installed manually.<br><br>
![](https://github.com/ik5xmk/mt_mqtt_jobs/blob/main/html_messages_dashboard.jpg)<br>
