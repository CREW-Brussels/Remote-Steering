#!/usr/bin/env python3
import asyncio
import json
import socket
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
import websockets
from pythonosc.udp_client import SimpleUDPClient

# A set to hold connected WebSocket clients
clients = set()

# Create an OSC broadcast client that sends messages to the broadcast address.
OSC_BROADCAST_IP = "10.0.0.255"   # Change if needed
OSC_BROADCAST_PORT = 9022              # Use a non-privileged port
osc_broadcast_client = SimpleUDPClient(OSC_BROADCAST_IP, OSC_BROADCAST_PORT)
# Enable broadcast on the socket.
osc_broadcast_client._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

def handle_wifi_data(address, *args):
    #print("Received OSC message:", address, args)
    data = {
        "address": address,
        "args": args
    }
    message = json.dumps(data)
    asyncio.ensure_future(broadcast(message))

def handle_nudge_response(address, *args):
    print("Received OSC nudge-response:", address, args)
    data = {
        "address": address,
        "args": args
    }
    message = json.dumps(data)
    asyncio.ensure_future(broadcast(message))

async def broadcast(message):
    if clients:
        #print("Broadcasting message to", len(clients), "clients")
        # Wrap each send() coroutine as a task.
        tasks = [asyncio.create_task(client.send(message)) for client in clients]
        await asyncio.wait(tasks)

def send_nudge(nudge_obj):
    # Extract nudge details from the object.
    client_mac = nudge_obj.get("client", "")
    neighbor = nudge_obj.get("neighbor", "")
    # Send OSC message with address "/nudge" and arguments [client_mac, neighbor]
    osc_broadcast_client.send_message("/nudge", [client_mac, neighbor])
    print(f"Broadcasted nudge message: /nudge [{client_mac}, {neighbor}]")

async def websocket_handler(websocket, path="/"):
    print("WebSocket client connected:", websocket.remote_address)
    clients.add(websocket)
    try:
        async for message in websocket:
            #print("Received message from client:", message)
            try:
                msg_obj = json.loads(message)
                if msg_obj.get("type") == "nudge":
                    send_nudge(msg_obj)
                else:
                    print("Received non-nudge message:", msg_obj)
            except Exception as e:
                print("Error processing websocket message:", e)
    except Exception as e:
        print("Exception in websocket_handler:", e)
    finally:
        clients.remove(websocket)
        print("WebSocket client disconnected:", websocket.remote_address)

async def main():
    # Set up the OSC dispatcher to map messages.
    dispatcher = Dispatcher()
    # Map WiFi data messages (e.g. "/wifi-data/SomeServer")
    dispatcher.map("/wifi-data/*", handle_wifi_data)
    # Map nudge response messages.
    dispatcher.map("/nudge-response", handle_nudge_response)
    
    # Create the OSC server on UDP port 9021.
    osc_server = AsyncIOOSCUDPServer(("0.0.0.0", 9021), dispatcher, asyncio.get_event_loop())
    transport, protocol = await osc_server.create_serve_endpoint()

    # Start the WebSocket server on port 8765 with a ping interval.
    ws_server = await websockets.serve(websocket_handler, "0.0.0.0", 8765, ping_interval=20)
    
    print("OSC-to-WebSocket Relay running:")
    print("  OSC listening on UDP port 9021")
    print("  WebSocket server on port 8765")
    print(f"  OSC broadcast client sending to {OSC_BROADCAST_IP}:{OSC_BROADCAST_PORT}")
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
