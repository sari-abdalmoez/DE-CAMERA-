[app]
title = DE CAMERA
package.name = decamera
package.domain = com.sari
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json
version = 1.0.0

requirements = python3,kivy==2.3.1,pillow==10.4.0,numpy==1.26.4,pyjnius

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

android.permissions = CAMERA,RECORD_AUDIO,READ_MEDIA_IMAGES,WRITE_EXTERNAL_STORAGE

[buildozer]
log_level = 2
warn_on_root = 1
