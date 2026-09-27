[app]

# ПолинаGram — Android сборка
title = PolinaGram
package.name = polinagram
package.domain = org.polinagram

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1.0

requirements = python3,kivy==2.3.0,requests,websockets,PyJWT,urllib3,chardet,idna,certifi

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.ndk = 25.2.9519653
android.accept_sdk_license = True

# Релизная подпись (см. README, раздел «Подпись APK»):
# android.keystore = release.keystore
# android.keystore.alias = polinagram

[buildozer]

log_level = 2
warn_on_root = 0
