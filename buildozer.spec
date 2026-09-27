[app]
# Application title
title = DE CAMERA

# Package name
package.name = decamera
package.domain = org.decamera

# Source code location
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# Version
version = 0.1.0

# Requirements
requirements = python3,kivy,requests

# Permissions
permissions = INTERNET,CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# Android specific settings
android.permissions = INTERNET,CAMERA,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True

[buildozer]
# Log level
log_level = 2

# Warnings
warn_on_root = 1
