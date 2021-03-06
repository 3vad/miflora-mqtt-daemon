#!/usr/bin/env python3

import sys
import json
import os.path
from time import sleep, localtime, strftime
from configparser import ConfigParser
from miflora.miflora_poller import MiFloraPoller, MI_BATTERY, MI_CONDUCTIVITY, MI_LIGHT, MI_MOISTURE, MI_TEMPERATURE
import paho.mqtt.client as mqtt

parameters = [MI_BATTERY, MI_CONDUCTIVITY, MI_LIGHT, MI_MOISTURE, MI_TEMPERATURE]

print('Xiaomi Mi Flora Plant Sensor MQTT Client/Daemon')
print('Source: https://github.com/janwh/miflora-mqtt-daemon')
print()

# Eclipse Paho callbacks http://www.eclipse.org/paho/clients/python/docs/#callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print('Connected.\n')
    else:
        print('Connection error with result code {} - {}'.format(str(rc), mqtt.connack_string(rc)), file=sys.stderr)
        #kill main thread
        os._exit(1)

def on_publish(client, userdata, mid):
    print('Data successfully published!')

# Load configuration file
config = ConfigParser(delimiters=('=', ))
config.optionxform = str
config.read(os.path.join(sys.path[0], 'config.ini'))

reporting_mode = config['General'].get('reporting_method', 'mqtt-json')
daemon_enabled = config['Daemon'].getboolean('enabled', True)
sleep_period = config['Daemon'].getint('period', 300)
topic_prefix = config['MQTT'].get('topic_prefix', 'miflora')
miflora_cache_timeout = config['MiFlora'].getint('cache_timeout', 600)

if not reporting_mode in ['mqtt-json', 'json']:
    print('Error. Configuration parameter reporting_mode set to an invalid value.', file=sys.stderr)
    sys.exit(1)
if not config['Sensors']:
    print('Error. Please add at least one sensor to the configuration file "config.ini".', file=sys.stderr)
    print('Scan for available Miflora sensors with "hcitool lescan".', file=sys.stderr)
    sys.exit(1)

# MQTT connection
if reporting_mode == 'mqtt-json':
    print('Connecting to MQTT broker ...')
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_publish = on_publish
    if config['MQTT'].get('username'):
        mqtt_client.username_pw_set(config['MQTT'].get('username'), config['MQTT'].get('password', None))
    try:
        mqtt_client.connect(config['MQTT'].get('hostname', 'localhost'),
                            port=config['MQTT'].getint('port', 1883),
                            keepalive=config['MQTT'].getint('keepalive', 60))
    except:
        print('Error. Please check your MQTT connection settings in the configuration file "config.ini".', file=sys.stderr)
        sys.exit(1)
    else:
        mqtt_client.loop_start()
        sleep(1) # some slack to establish the connection

# Initialize Mi Flora sensors
flores = {}
for flora in config['Sensors'].items():
    print('Adding device from config to Mi Flora device list ...')
    print('Name:         "{}"'.format(flora[0]))
    flores[flora[0]] = MiFloraPoller(mac=flora[1], cache_timeout=miflora_cache_timeout)
    print('Device name:  "{}"'.format(flores[flora[0]].name()))
    print('MAC address:  {}'.format(flora[1]))
    print('Firmware:     {}'.format(flores[flora[0]].firmware_version()))
    print()

# Sensor data retrieval and publication
while True:
    for flora in flores:
        data = {}
        for param in parameters:
            data[param] = flores.get(flora).parameter_value(param)
        timestamp = strftime('%Y-%m-%d %H:%M:%S', localtime())

        if reporting_mode == 'mqtt-json':
            print('[{}] Attempting to publishing to MQTT topic "{}/{}" ...\nData: {}'.format(timestamp, topic_prefix, flora, json.dumps(data)))
            mqtt_client.publish('{}/{}'.format(topic_prefix, flora), json.dumps(data))
            sleep(0.5) # some slack for the publish roundtrip and callback function
            print()
        elif reporting_mode == 'json':
            data['timestamp'] = timestamp
            data['name'] = flora
            data['mac'] = flores.get(flora)._mac
            print(json.dumps(data))
        else:
            raise NameError('Unexpected reporting_mode.')

    if not daemon_enabled:
        break
    else:
        print('Sleeping ({} seconds) ...'.format(sleep_period))
        sleep(sleep_period)
        print()

if reporting_mode == 'mqtt-json':
    mqtt_client.disconnect()

