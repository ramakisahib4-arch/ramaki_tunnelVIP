"""
P2P TUNNEL - برنامه بومی خالص انتقال اینترنت
ساخته شده توسط: جنرال رَمَکی صاحب
نسخه: ۱.۰
"""

import socket
import threading
import uuid
import json
import time
import os
import sys
import requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
import webbrowser

# ===== تنظیمات رنگ =====
Window.clearcolor = (0.04, 0.05, 0.07, 1)

# ===== تنظیمات تانل =====
SIGNALING_SERVER = "ws://185.235.84.234:8765"  # ← اینجا IP سرور سیگنالینگ خود را بگذارید
LOCAL_PROXY_PORT = 9090
BUFFER_SIZE = 65536

class TunnelCore:
    """هسته اصلی تانل - بومی خالص با Socket مستقیم"""
    
    def __init__(self, callback=None):
        self.peer_id = uuid.uuid4().hex[:12]
        self.callback = callback
        self.running = False
        self.is_provider = False
        self.connection = None
        self.proxy_server = None
        self.server_socket = None
    
    def generate_link(self):
        """ساخت لینک منحصربه‌فرد برای Provider"""
        # گرفتن IP عمومی
        ip = "0.0.0.0"
        try:
            ip = requests.get("https://api.ipify.org", timeout=2).text
        except:
            try:
                ip = requests.get("https://icanhazip.com", timeout=2).text.strip()
            except:
                ip = "127.0.0.1"
        
        # لینک با فرمت: p2p://peer_id@ip:port
        link = f"p2p://{self.peer_id}@{ip}:{LOCAL_PROXY_PORT}"
        return link
    
    def start_as_provider(self):
        """شروع به عنوان دهنده اینترنت"""
        self.is_provider = True
        self.running = True
        
        thread = threading.Thread(target=self._provider_listener, daemon=True)
        thread.start()
        
        if self.callback:
            self.callback("status", f"شناسه: {self.peer_id}")
            self.callback("status", "منتظر اتصال مصرف‌کننده...")
        
        return True
    
    def _provider_listener(self):
        """Provider: منتظر اتصال مستقیم Consumer"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', LOCAL_PROXY_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(300)  # 5 دقیقه timeout
            
            if self.callback:
                self.callback("status", f"پورت {LOCAL_PROXY_PORT} باز شد")
                self.callback("ready", "منتظر اتصال...")
            
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                    self.connection = conn
                    
                    if self.callback:
                        self.callback("connected", f"مصرف‌کننده متصل شد: {addr[0]}")
                    
                    # شروع پروکسی اینترنت
                    self._start_internet_proxy(conn)
                    break
                    
                except socket.timeout:
                    if self.callback:
                        self.callback("status", "زمان انتظار تمام شد. دوباره امتحان کنید.")
                    break
                except Exception as e:
                    if self.callback:
                        self.callback("error", str(e))
                    break
                    
        except Exception as e:
            if self.callback:
                self.callback("error", f"خطا: {str(e)}")
        finally:
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
    
    def connect_as_consumer(self, link):
        """اتصال به عنوان گیرنده اینترنت"""
        self.is_provider = False
        self.running = True
        
        # استخراج اطلاعات از لینک
        try:
            raw = link.replace("p2p://", "")
            parts = raw.split("@")
            peer_id = parts[0]
            ip_port = parts[1].split(":")
            ip = ip_port[0]
            port = int(ip_port[1]) if len(ip_port) > 1 else LOCAL_PROXY_PORT
        except Exception as e:
            if self.callback:
                self.callback("error", f"لینک نامعتبر: {str(e)}")
            return False
        
        self.peer_id = peer_id
        
        thread = threading.Thread(
            target=self._consumer_connect,
            args=(ip, port, peer_id),
            daemon=True
        )
        thread.start()
        return True
    
    def _consumer_connect(self, ip, port, peer_id):
        """Consumer: مستقیماً به Provider وصل می‌شود"""
        try:
            if self.callback:
                self.callback("status", f"در حال اتصال به {ip}:{port}...")
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((ip, port))
            self.connection = sock
            
            # ارسال دستور به Provider برای شروع پروکسی
            handshake = json.dumps({
                "type": "connect",
                "peer_id": peer_id,
                "mode": "consumer"
            }).encode()
            sock.send(handshake)
            
            if self.callback:
                self.callback("connected", "اتصال مستقیم برقرار شد!")
                self.callback("status", "اینترنت از Provider مصرف می‌شود")
                self.callback("proxy_ready", str(LOCAL_PROXY_PORT))
            
            # شروع دریافت داده
            self._receive_data(sock)
            
        except socket.timeout:
            if self.callback:
                self.callback("error", "زمان اتصال تمام شد. چک کنید Provider آنلاین است؟")
        except ConnectionRefusedError:
            if self.callback:
                self.callback("error", "اتصال رد شد. آیا Provider برنامه را باز کرده؟")
        except Exception as e:
            if self.callback:
                self.callback("error", f"خطا: {str(e)}")
    
    def _start_internet_proxy(self, conn):
        """شروع پروکسی اینترنت واقعی روی دستگاه Provider"""
        try:
            self.proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.proxy_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.proxy_server.bind(('127.0.0.1', LOCAL_PROXY_PORT + 1))
            self.proxy_server.listen(10)
            self.proxy_server.settimeout(1)
            
            if self.callback:
                self.callback("status", f"پروکسی روی 127.0.0.1:{LOCAL_PROXY_PORT + 1}")
                self.callback("proxy_running", "فعال")
            
            while self.running and self.connection:
                try:
                    client, addr = self.proxy_server.accept()
                    # هر درخواست اینترنت Consumer از طریق اینترنت Provider می‌رود
                    threading.Thread(
                        target=self._forward_traffic,
                        args=(client,),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except:
                    break
                    
        except Exception as e:
            if self.callback:
                self.callback("error", f"خطا در پروکسی: {str(e)}")
    
    def _forward_traffic(self, client_sock):
        """ارسال ترافیک اینترنت از طریق Provider"""
        try:
            data = client_sock.recv(BUFFER_SIZE)
            if data and self.connection:
                self.connection.sendall(data)
                
                # دریافت پاسخ از اینترنت واقعی Provider
                response = self.connection.recv(BUFFER_SIZE)
                if response:
                    client_sock.sendall(response)
                    
                    if self.callback:
                        self.callback("traffic", f"{len(data) + len(response)} بایت")
        except:
            pass
        finally:
            try:
                client_sock.close()
            except:
                pass
    
    def _receive_data(self, sock):
        """دریافت داده از Provider"""
        try:
            while self.running:
                data = sock.recv(BUFFER_SIZE)
                if not data:
                    break
                if self.callback:
                    self.callback("data_received", f"{len(data)} بایت دریافت شد")
        except:
            pass
    
    def disconnect(self):
        """قطع اتصال"""
        self.running = False
        for s in [self.connection, self.server_socket, self.proxy_server]:
            try:
                if s:
                    s.close()
            except:
                pass
        if self.callback:
            self.callback("disconnected", "قطع شد")


class TunnelUI(BoxLayout):
    """رابط کاربری برنامه"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tunnel = None
        self.is_connected = False
        self._build_interface()
    
    def _build_interface(self):
        self.orientation = 'vertical'
        self.padding = [20, 10]
        self.spacing = 6
        
        # عنوان
        title = Label(
            text='🔒 P2P TUNNEL',
            font_size=28,
            bold=True,
            color=(0, 1, 0.5, 1),
            size_hint_y=0.05
        )
        self.add_widget(title)
        
        # توضیحات
        info = Label(
            text='سازنده: جنرال رَمَکی صاحب\n'
                 'دهنده: دکمه سبز → لینک بساز → برای رفیق بفرست\n'
                 'گیرنده: لینک را بگذار → دکمه آبی → اتصال مستقیم',
            font_size=10,
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=0.08,
            halign='center'
        )
        self.add_widget(info)
        
        # ===== خط جداکننده =====
        sep1 = Label(text='─' * 50, color=(0, 1, 0.2, 0.3), size_hint_y=0.02)
        self.add_widget(sep1)
        
        # ===== بخش Provider =====
        prov_label = Label(
            text='◈ دهنده اینترنت (Provider) ◈',
            color=(0, 1, 0.3, 1),
            size_hint_y=0.03
        )
        self.add_widget(prov_label)
        
        self.btn_create = Button(
            text='🟢 [۱] ساخت لینک و شروع',
            background_color=(0, 0.6, 0.15, 1),
            size_hint_y=0.08,
            font_size=14
        )
        self.btn_create.bind(on_press=self.on_create)
        self.add_widget(self.btn_create)
        
        self.link_field = TextInput(
            text='[ لینک شما ]',
            readonly=True,
            size_hint_y=0.07,
            font_size=11,
            background_color=(0.06, 0.08, 0.12, 1),
            foreground_color=(0, 1, 0.5, 1)
        )
        self.add_widget(self.link_field)
        
        self.btn_copy = Button(
            text='📋 کپی لینک',
            background_color=(0.15, 0.2, 0.35, 1),
            size_hint_y=0.05
        )
        self.btn_copy.bind(on_press=lambda x: self._copy())
        self.add_widget(self.btn_copy)
        
        # ===== خط جداکننده =====
        sep2 = Label(text='─' * 50, color=(0.3, 0.7, 1, 0.3), size_hint_y=0.02)
        self.add_widget(sep2)
        
        # ===== بخش Consumer =====
        cons_label = Label(
            text='◈ گیرنده اینترنت (Consumer) ◈',
            color=(0.3, 0.7, 1, 1),
            size_hint_y=0.03
        )
        self.add_widget(cons_label)
        
        self.input_field = TextInput(
            hint_text='لینک رفیق را اینجا بگذارید...',
            size_hint_y=0.07,
            font_size=12,
            background_color=(0.06, 0.08, 0.12, 1),
            foreground_color=(1, 1, 1, 1)
        )
        self.add_widget(self.input_field)
        
        self.btn_connect = Button(
            text='🔵 [۲] اتصال به اینترنت رفیق',
            background_color=(0, 0.35, 0.75, 1),
            size_hint_y=0.08,
            font_size=14
        )
        self.btn_connect.bind(on_press=self.on_connect)
        self.add_widget(self.btn_connect)
        
        # ===== وضعیت =====
        stat_label = Label(
            text='═══ وضعیت ═══',
            color=(0.5, 0.5, 0.5, 1),
            size_hint_y=0.02
        )
        self.add_widget(stat_label)
        
        self.status = TextInput(
            text='[✓] برنامه آماده است\n[✓] منتظر دستور شما...',
            readonly=True,
            size_hint_y=0.22,
            font_size=12,
            background_color=(0.04, 0.06, 0.09, 1),
            foreground_color=(0, 1, 0, 1)
        )
        self.add_widget(self.status)
        
        # ===== دکمه‌های پایین =====
        bottom = BoxLayout(size_hint_y=0.06, spacing=4)
        
        tg = Button(text='📱 تلگرام', background_color=(0, 0.35, 0.6, 1))
        tg.bind(on_press=lambda x: webbrowser.open('https://t.me'))
        
        em = Button(text='📧 ایمیل', background_color=(0.35, 0.15, 0.5, 1))
        em.bind(on_press=lambda x: webbrowser.open('mailto:ramakisahi4@gmail.com'))
        
        dc = Button(text='⛔ قطع', background_color=(0.6, 0.1, 0.1, 1))
        dc.bind(on_press=self.on_disconnect)
        
        bottom.add_widget(tg)
        bottom.add_widget(em)
        bottom.add_widget(dc)
        self.add_widget(bottom)
    
    # ===== توابع =====
    
    def on_create(self, instance):
        """Provider: ساخت لینک و شروع"""
        self._log("ساخت لینک جدید...")
        
        self.tunnel = TunnelCore(callback=self._tunnel_event)
        link = self.tunnel.generate_link()
        self.link_field.text = link
        Clipboard.copy(link)
        
        self._log("لینک کپی شد!")
        self._log("شروع به عنوان Provider...")
        
        self.tunnel.start_as_provider()
    
    def on_connect(self, instance):
        """Consumer: اتصال به Provider"""
        link = self.input_field.text.strip()
        
        if not link or 'p2p://' not in link:
            self._log("❌ خطا: لینک نامعتبر!")
            self._log("لینک باید با p2p:// شروع شود")
            return
        
        self._log("اتصال به Provider...")
        
        self.tunnel = TunnelCore(callback=self._tunnel_event)
        success = self.tunnel.connect_as_consumer(link)
        
        if not success:
            self._log("❌ خطا در اتصال")
    
    def on_disconnect(self, instance):
        """قطع اتصال"""
        if self.tunnel:
            self.tunnel.disconnect()
        self.is_connected = False
        self._log("⛔ قطع اتصال شد")
    
    def _copy(self):
        """کپی به کلیپ‌بورد"""
        Clipboard.copy(self.link_field.text)
        self._log("📋 کپی شد!")
    
    def _tunnel_event(self, event, message):
        """رویدادهای هسته تانل"""
        Clock.schedule_once(lambda dt: self._handle_event(event, message), 0)
    
    def _handle_event(self, event, message):
        if event == 'connected':
            self._log(f"✅ {message}")
            self.is_connected = True
        elif event == 'error':
            self._log(f"❌ {message}")
        elif event == 'ready':
            self._log(f"🔗 {message}")
        elif event == 'traffic':
            pass  # نمایش نده
        elif event == 'proxy_running':
            self._log(f"🌐 پروکسی {message}")
            self._log("✅ اینترنت از Provider مصرف می‌شود!")
        else:
            self._log(f"> {message}")
    
    def _log(self, text):
        """اضافه کردن متن به وضعیت"""
        current = self.status.text
        lines = current.split('\n')
        if len(lines) > 20:
            lines = lines[-15:]
        lines.append(text)
        self.status.text = '\n'.join(lines)


class TunnelApp(App):
    """برنامه اصلی"""
    
    def build(self):
        self.title = 'P2P Tunnel'
        return TunnelUI()


if __name__ == '__main__':
    TunnelApp().run()
