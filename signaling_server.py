"""
Signaling Server برای P2P Tunnel
این فایل را روی یک سرور ابری (VPS) اجرا کنید
اجرا: python3 signaling_server.py
"""

import asyncio
import json
import uuid
import websockets
import sys

PORT = 8765
clients = {}

async def handler(websocket):
    client_id = str(uuid.uuid4())[:8]
    clients[client_id] = websocket
    
    try:
        await websocket.send(json.dumps({
            "type": "welcome",
            "client_id": client_id,
            "message": "به سرور سیگنالینگ خوش آمدید"
        }))
        
        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                
                if msg_type == "register":
                    # Provider ثبت می‌کند که آماده است
                    await websocket.send(json.dumps({
                        "type": "registered",
                        "client_id": client_id,
                        "status": "ready"
                    }))
                    print(f"[+] Provider ثبت شد: {client_id}")
                
                elif msg_type == "find":
                    # Consumer به دنبال Provider می‌گردد
                    target_id = data.get("target_id")
                    if target_id in clients:
                        # به Provider بگو کسی می‌خواهد وصل شود
                        await clients[target_id].send(json.dumps({
                            "type": "connection_request",
                            "from": client_id
                        }))
                        
                        await websocket.send(json.dumps({
                            "type": "found",
                            "target_id": target_id,
                            "message": "Provider پیدا شد"
                        }))
                        print(f"[→] درخواست اتصال: {client_id} → {target_id}")
                    else:
                        await websocket.send(json.dumps({
                            "type": "not_found",
                            "message": "Provider آنلاین نیست"
                        }))
                
                elif msg_type == "signal":
                    # پیام سیگنالینگ WebRTC
                    target = data.get("target")
                    if target in clients:
                        await clients[target].send(json.dumps(data))
                
                elif msg_type == "keep_alive":
                    await websocket.send(json.dumps({"type": "alive"}))
                    
            except json.JSONDecodeError:
                pass
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if client_id in clients:
            del clients[client_id]
            print(f"[-] Client left: {client_id}")
            # به بقیه بگو این کاربر رفت
            for cid, ws in clients.items():
                try:
                    asyncio.create_task(ws.send(json.dumps({
                        "type": "peer_left",
                        "peer_id": client_id
                    })))
                except:
                    pass

async def main():
    print(f"[*] Signaling Server شروع شد روی پورت {PORT}")
    print(f"[*] منتظر اتصال کلاینت‌ها...")
    
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] سرور متوقف شد")
        sys.exit(0)
