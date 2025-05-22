#!/usr/bin/env python3
import json
import subprocess
import re
import time
import socket
import os
import sys
import signal
import configparser
from threading import Thread
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

# Configuration file and PID file paths
CONFIG_FILE = "/root/wifi_osc_daemon.conf"
PID_FILE = "/var/run/wifi_osc_daemon.pid"

# Load configuration (OSC IP, OSC port, OSC listen port)
def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        osc_ip = config.get("osc", "ip", fallback="127.0.0.1")
        osc_port = config.getint("osc", "port", fallback=9000)
        listen_port = config.getint("osc", "listen_port", fallback=9001)
    else:
        osc_ip, osc_port, listen_port = "127.0.0.1", 9000, 9001
    return osc_ip, osc_port, listen_port

OSC_IP, OSC_PORT, LISTEN_PORT = load_config()
osc_client = SimpleUDPClient(OSC_IP, OSC_PORT)
osc_client._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# OSC address: /wifi-data/<hostname>
HOSTNAME = socket.gethostname()
OSC_ADDRESS = f"/wifi-data/{HOSTNAME}"

# Global flag to indicate daemon mode
is_daemon = False

# Signal handler to stop the daemon gracefully
def stop_daemon(signal_received=None, frame=None):
    print("\nStopping Wi-Fi OSC daemon...")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    sys.exit(0)

# Daemonize the process (detach from terminal, redirect stdio, write PID file)
def daemonize():
    if os.fork() > 0:
        sys.exit(0)  # First parent exits
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)  # Second parent exits

    sys.stdin = open("/dev/null", "r")
    sys.stdout = open("/dev/null", "a")
    sys.stderr = open("/dev/null", "a")

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

# ------------------------------------------------------------------
# Helper functions to get BSSID and Channel from 'iw dev <ifname> info'
# ------------------------------------------------------------------
def get_bssid_for_interface(ifname):
    try:
        result = subprocess.run(['iw', 'dev', ifname, 'info'],
                                capture_output=True, text=True, check=True)
        # Use a regex that accepts an optional colon after "addr"
        m = re.search(r"addr:?[\s]+([0-9a-f:]{17})", result.stdout, re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""

def get_channel_for_interface(ifname):
    try:
        result = subprocess.run(['iw', 'dev', ifname, 'info'],
                                capture_output=True, text=True, check=True)
        m = re.search(r"channel\s+(\d+)", result.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""

# ------------------------------------------------------------------
# Functions to include connected clients and BSSID (as neighbor string) in the Wi‑Fi data
# ------------------------------------------------------------------
def get_clients_for_interface(ifname):
    """
    Get a list of connected clients for the given interface.
    Each client is a dict with 'mac', 'signal_strength' (in dBm) and 'ip_address'.
    """
    clients = []
    try:
        result = subprocess.run(['iw', 'dev', ifname, 'station', 'dump'],
                                  capture_output=True, text=True, check=True)
        blocks = result.stdout.strip().split("Station ")
        for block in blocks[1:]:
            lines = block.splitlines()
            mac = lines[0].split()[0].strip()
            m_signal = re.search(r"signal:\s+(-?\d+)\s+dBm", block)
            signal = m_signal.group(1) if m_signal else None
            ip = None
            try:
                dhcp = subprocess.run(['cat', '/tmp/dhcp.leases'],
                                        capture_output=True, text=True, check=True)
                m_ip = re.search(rf"{mac}.*?(\d+\.\d+\.\d+\.\d+)", dhcp.stdout, re.IGNORECASE)
                ip = m_ip.group(1) if m_ip else None
            except subprocess.CalledProcessError:
                pass
            clients.append({"mac": mac, "signal_strength": signal, "ip_address": ip})
    except subprocess.CalledProcessError:
        pass
    return clients

def get_wifi_interfaces():
    """
    Get details of Wi‑Fi interfaces using ubus.
    For each interface, include:
      - interface name
      - ssid
      - mode
      - firewall_network
      - bssid (formatted as "70:f0:96:21:9b:c3,0x0000,81,11,6")
      - connected_clients (list with mac, signal_strength, and ip_address)
    """
    interfaces = []
    try:
        result = subprocess.run(['ubus', 'call', 'network.wireless', 'status'],
                                capture_output=True, text=True, check=True, timeout=3)
        wifi_data = json.loads(result.stdout)
        for radio, details in wifi_data.items():
            if 'interfaces' in details:
                for iface in details['interfaces']:
                    ifname = iface.get('ifname', 'Unknown')
                    ssid = iface['config'].get('ssid', 'Hidden SSID')
                    mode = iface['config'].get('mode', 'Unknown Mode')
                    network = iface['config'].get('network', ['Unknown Network'])
                    bssid = iface['config'].get('bssid', '')
                    if not bssid:
                        bssid = get_bssid_for_interface(ifname)
                    channel = iface['config'].get('channel', '')
                    if not channel and ifname:
                        channel = get_channel_for_interface(ifname)
                    if bssid and channel:
                        op_class = "115" if int(channel) >= 36 else "81"
                        phy_type = "7" if int(channel) > 14 else "6"
                        bssid_neighbor = f"{bssid},0x0000,{op_class},{channel},{phy_type}"
                    else:
                        bssid_neighbor = ""
                    clients = get_clients_for_interface(ifname)
                    interfaces.append({
                        "interface": ifname,
                        "ssid": ssid,
                        "mode": mode,
                        "firewall_network": network,
                        "bssid": bssid_neighbor,
                        "connected_clients": clients
                    })
    except Exception as e:
        print("Error reading wifi interfaces:", e)
    return interfaces

# ------------------------------------------------------------------
# The neighbor string for BSS transition requests is now provided as the second argument.
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Functions for client steering and OSC message handling
# ------------------------------------------------------------------
def get_all_connected_client_macs():
    macs = set()
    try:
        result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, check=True, timeout=2)
        interfaces = re.findall(r"Interface (\S+)", result.stdout)
        for iface in interfaces:
            station_dump = subprocess.run(['iw', 'dev', iface, 'station', 'dump'],
                                          capture_output=True, text=True, check=True)
            mac_matches = re.findall(r"Station ([0-9A-Fa-f:]{17})", station_dump.stdout)
            macs.update(mac_matches)
    except Exception as e:
        print("Error: Failed to get connected clients:", e)
    return macs

def get_client_interface(mac):
    try:
        result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, check=True, timeout=2)
        interfaces = re.findall(r"Interface (\S+)", result.stdout)
        for iface in interfaces:
            station_dump = subprocess.run(['iw', 'dev', iface, 'station', 'dump'],
                                          capture_output=True, text=True, check=True)
            if mac.lower() in station_dump.stdout.lower():
                return iface
    except Exception as e:
        print(f"Error: Could not find interface for client {mac}: {e}")
    return None


def is_same_bssid(interface, neighbor_param):
    """Returns True if the local AP's BSSID matches the BSSID from the neighbor parameter."""
    
    # Extract the BSSID (first part of neighbor_param)
    neighbor_bssid = neighbor_param.split(',')[0].strip().lower()
    
    # Get the local AP's BSSID
    local_bssid = get_local_ap_bssid(interface)
    
    if not local_bssid:
        print(f"Error: Could not determine BSSID for interface {interface}")
        return False

    return local_bssid.lower() == neighbor_bssid

def get_local_ap_bssid(interface):
    """Returns the BSSID (MAC Address) of the local AP (Access Point) for a given interface."""
    try:
        cmd = ["cat", f"/sys/class/net/{interface}/address"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip() if result.stdout else None
    except subprocess.CalledProcessError:
        print(f"Error: Could not retrieve BSSID for {interface}")
        return None

def handle_nudge(address, *args):
    # Expecting two arguments: client MAC and neighbor parameter (without the "neighbor=" prefix)
    if len(args) != 2:
        return
    mac1, neighbor_param = args
    connected_clients = get_all_connected_client_macs()
    if mac1.lower() in connected_clients:
        current_interface = get_client_interface(mac1)
        if current_interface:
            if is_same_bssid(current_interface, neighbor_param):
                osc_client.send_message("/nudge-response", f"{mac1} is allready here")
            else:
                # Prepend 'neighbor=' to the provided neighbor parameter
                neighbor_arg = f"neighbor={neighbor_param}"
                cmd1 = ["hostapd_cli", "-i", current_interface, "bss_tm_req", mac1, "disassoc_imminent=1", "disassoc_timer=5", "prefer=1", "btm_mode=2", neighbor_arg]
                result = subprocess.run(cmd1, capture_output=True, text=True)

                print(result)

                osc_client.send_message("/nudge-response",
                                        f"Sent BSS transition request to {mac1}: {result.stdout.strip()}")
        else:
            osc_client.send_message("/nudge-response", f"Could not find interface for client {mac1}")
    else:
        osc_client.send_message("/nudge-response", f"Nudge ignored: {mac1} is not connected")

def start_osc_server():
    dispatcher = Dispatcher()
    dispatcher.map("/nudge", handle_nudge)
    server = BlockingOSCUDPServer(("0.0.0.0", LISTEN_PORT), dispatcher)
    print(f"Listening for OSC messages on port {LISTEN_PORT}...")
    server.serve_forever()

def send_osc_message():
    while True:
        try:
            wifi_data = get_wifi_interfaces()
            wifi_json = json.dumps(wifi_data)
            osc_client.send_message(OSC_ADDRESS, wifi_json)
        except Exception as e:
            print("OSC send failed:", e)
        time.sleep(1)

# ------------------------------------------------------------------
# Main entry point: daemon mode vs. foreground with logging and graceful stop
# ------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "-d":
        print("Starting Wi-Fi OSC daemon in background...")
        is_daemon = True
        daemonize()

    if not is_daemon:
        signal.signal(signal.SIGINT, stop_daemon)
    signal.signal(signal.SIGTERM, stop_daemon)
    
    osc_server_thread = Thread(target=start_osc_server, daemon=True)
    osc_server_thread.start()
    
    osc_sender_thread = Thread(target=send_osc_message, daemon=True)
    osc_sender_thread.start()
    
    print("Wi-Fi OSC daemon running...")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        stop_daemon()
