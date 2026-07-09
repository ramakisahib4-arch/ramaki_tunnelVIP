[app]
title = P2P Tunnel
package.name = p2ptunnel
package.domain = org.ramaki
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy,requests,websockets,android
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.2.1
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[app]
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, FOREGROUND_SERVICE
android.api = 31
android.minapi = 21
android.sdk = 34
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.wakelock = True
