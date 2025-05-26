# RemoteSteering

RemoteSteering is a system designed to operate on OpenWrt routers. It manages the roaming of Wi-Fi clients, particularly for virtual reality headsets, to optimize access point changes and minimize service interruptions.

## Installation

### Prerequisites
- OpenWrt routers
- Access to the LuCI interface (optional for the Dashboard)

### Installation Steps

#### Install the Service on OpenWrt Routers:

Since there is no opkg package available, you need to install the service manually:

Copy the necessary files to your OpenWrt router.

``` bash
scp remote-steering/Service/wifi-osc-daemon root@<router-ip-address>:/usr/bin/
scp remote-steering/Service/wifi-osc-daemon.py root@<router-ip-address>:/root/
scp remote-steering/Service/wifi_osc_daemon.conf root@<router-ip-address>:/root/
```

Log in to your router and manually install the files.

``` bash
ssh root@<router-ip-address>
chmod +x /usr/bin/wifi-osc-daemon
```

#### Install the Dashboard (Optional):

Copy the Dashboard files to your OpenWrt router.

```bash
scp remote-steering/Dashboard/osc_websocket_relay.py root@<router-ip-address>:/path/to/destination/
scp -r remote-steering/Dashboard/usr/lib/lua/luci root@<router-ip-address>:/usr/lib/lua/
```
Log in to your router and manually install the files.

``` bash
ssh root@<router-ip-address>
chmod +x /path/to/destination/osc_websocket_relay.py
```
## Usage
### Service

The RemoteSteering service runs in the background on OpenWrt routers. It queries connected Wi-Fi clients and communicates with external software to manage roaming.
Dashboard

The Dashboard is accessible via the LuCI interface and allows you to control and monitor the RemoteSteering system.

    Access the Dashboard:
        Log in to your router's LuCI interface.
        Navigate to the RemoteSteering Dashboard.

    Control Roaming:
        Use the Dashboard to monitor connected Wi-Fi clients.
        Configure roaming settings to optimize access point changes.

### Configuration

The configuration file is `/root/wifi_osc_daemon.conf` This file stores the configuration parameters required for the OSC daemon to function.
Configuration File: wifi_osc_daemon.conf

The configuration file is in INI format, meaning it is divided into sections, each containing key-value pairs. Here is an example of what this file might look like:

``` conf
[osc]
ip = 127.0.0.1
port = 9000
listen_port = 9001
```
Sections and Keys

- Section [osc] :

	- ip :
		- Type : String
		- Description : The IP address to which the OSC client will send messages. By default, it is 127.0.0.1, meaning messages will be sent to the local host.
		- Example : ip = 192.168.1.100

	- port :
		- Type : Integer
		- Description : The port on which the OSC client will send messages. By default, it is 9000.
		- Example : port = 9000

	- listen_port :
		- Type : Integer
		- Description : The port on which the OSC server will listen for incoming messages. By default, it is 9001.
		- Example : listen_port = 9001

### OSC Protocol
#### OSC Messages

	/wifi-data/<hostname>
Description : Periodic message containing Wi-Fi data.

Format : JSON containing details of Wi-Fi interfaces, SSIDs, connected clients, etc.

    /nudge
Description : Message to trigger a Wi-Fi client transition.

Format : <client_mac> <neighbor_param>

    /nudge-response
Description : Response message indicating the result of the transition request.

Format : Text indicating the result of the request.

#### Example Message /wifi-data/<hostname>

``` JSON
[
  {
    "interface": "wlan0",
    "ssid": "MySSID",
    "mode": "ap",
    "firewall_network": ["lan"],
    "bssid": "70\:f0:96:21:9b\:c3,0x0000,81,11,6",
    "connected_clients": [
      {
        "mac": "00:11:22:33:44:55",
        "signal_strength": "-65",
        "ip_address": "192.168.1.100"
      }
    ]
  }
]
```

#### Startup Script

The startup script is located in the /etc/init.d/ directory and is used to control the wifi-osc-daemon.py service. It follows the standard structure of OpenWrt startup scripts.
Script Structure

``` bash
#!/bin/sh /etc/rc.common
START=99
STOP=10
DAEMON="/usr/bin/python /root/wifi-osc-daemon.py"  # Change path if needed

start() {
    echo "Starting WiFi OSC Daemon..."
    \$DAEMON &
}

stop() {
    echo "Stopping WiFi OSC Daemon..."
    \$DAEMON stop
}

restart() {
    stop
    sleep 1
    start
}
```

#### Usage

Start the Service :

	/etc/init.d/wifi-osc-daemon start

Stop the Service :

	/etc/init.d/wifi-osc-daemon stop

Restart the Service :

	/etc/init.d/wifi-osc-daemon restart

Enable the Service at Startup :

	/etc/init.d/wifi-osc-daemon enable

Disable the Service at Startup :

	/etc/init.d/wifi-osc-daemon disable