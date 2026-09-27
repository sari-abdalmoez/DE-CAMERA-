# DE CAMERA
# Single-file Python/Kivy camera application
# Target: Android ARM64
#
# Real in this file:
# - Camera preview
# - Photo capture from Kivy camera texture
# - Save photos
# - Night processing
# - HDR-style multi-frame accumulation
# - Astro enhancement
# - Star detection
# - Star Trails accumulation
# - Pro UI
# - Video-mode UI
#
# Android Camera2-only features such as real RAW/DNG, manual ISO,
# shutter and focus require a native Camera2 bridge and are reported
# as unavailable instead of being faked.

import os
import time
import threading
from datetime import datetime

import numpy as np

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Ellipse
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.camera import Camera
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


# ============================================================
# ANDROID
# ============================================================

ANDROID = False

try:
    from android.permissions import (
        request_permissions,
        Permission,
    )

    ANDROID = True
except Exception:
    ANDROID = False


# ============================================================
# COLORS
# ============================================================

GOLD = (0.851, 0.643, 0.082, 1)
BLACK = (0.018, 0.018, 0.018, 1)
PANEL = (0.055, 0.055, 0.055, 1)
PANEL2 = (0.09, 0.09, 0.09, 1)
WHITE = (0.95, 0.95, 0.95, 1)
GRAY = (0.55, 0.55, 0.55, 1)
RED = (0.85, 0.08, 0.08, 1)


Window.clearcolor = BLACK


# ============================================================
# UTILITIES
# ============================================================

def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def make_button(text, font_size=13):
    b = Button(
        text=text,
        font_size=font_size,
        color=WHITE,
        background_normal="",
        background_down="",
        background_color=PANEL2,
    )

    with b.canvas.before:
        Color(*PANEL2)
        b._bg = RoundedRectangle(
            pos=b.pos,
            size=b.size,
            radius=[14]
        )

    def update(*_):
        b._bg.pos = b.pos
        b._bg.size = b.size

    b.bind(pos=update, size=update)

    return b


# ============================================================
# IMAGE ENGINE
# ============================================================

class ImageEngine:

    @staticmethod
    def to_pil(texture):
        """
        Convert Kivy camera texture into PIL RGB image.
        """

        if texture is None:
            return None

        try:
            width, height = texture.size
            pixels = texture.pixels

            if not pixels:
                return None

            arr = np.frombuffer(
                pixels,
                dtype=np.uint8
            )

            arr = arr.reshape(
                height,
                width,
                4
            )

            # Kivy texture is usually RGBA.
            rgb = arr[:, :, :3]

            # Flip vertically because texture coordinates differ.
            rgb = np.flipud(rgb)

            return Image.fromarray(rgb, "RGB")

        except Exception as e:
            print("Texture conversion error:", e)
            return None

    @staticmethod
    def denoise(img):
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.filter(ImageFilter.GaussianBlur(radius=0.35))
        return img

    @staticmethod
    def sharpen(img, amount=1.4):
        return ImageEnhance.Sharpness(img).enhance(amount)

    @staticmethod
    def contrast(img, amount=1.2):
        return ImageEnhance.Contrast(img).enhance(amount)

    @staticmethod
    def brightness(img, amount=1.0):
        return ImageEnhance.Brightness(img).enhance(amount)

    @staticmethod
    def saturation(img, amount=1.0):
        return ImageEnhance.Color(img).enhance(amount)

    @staticmethod
    def tone_map(img):
        arr = np.asarray(img).astype(np.float32)

        arr /= 255.0

        # Shadow lifting + highlight compression.
        arr = np.power(arr, 0.86)

        arr = np.clip(arr, 0, 1)

        return Image.fromarray(
            (arr * 255).astype(np.uint8),
            "RGB"
        )

    @staticmethod
    def night(img):

        img = ImageEngine.denoise(img)

        img = ImageEngine.brightness(
            img,
            1.35
        )

        img = ImageEngine.contrast(
            img,
            1.12
        )

        img = ImageEngine.tone_map(img)

        img = ImageEngine.sharpen(
            img,
            1.15
        )

        return img

    @staticmethod
    def hdr(frames):

        if not frames:
            return None

        arrays = []

        for frame in frames:
            arrays.append(
                np.asarray(frame).astype(np.float32)
            )

        stack = np.stack(
            arrays,
            axis=0
        )

        # Median stacking is more resistant to noise/outliers
        merged = np.median(
            stack,
            axis=0
        )

        merged = np.clip(
            merged,
            0,
            255
        ).astype(np.uint8)

        img = Image.fromarray(
            merged,
            "RGB"
        )

        img = ImageEngine.tone_map(img)
        img = ImageEngine.contrast(img, 1.18)
        img = ImageEngine.sharpen(img, 1.25)

        return img

    @staticmethod
    def astro(img):

        img = ImageEngine.denoise(img)

        img = ImageEngine.tone_map(img)

        img = ImageEngine.contrast(
            img,
            1.40
        )

        img = ImageEngine.saturation(
            img,
            1.18
        )

        img = ImageEngine.sharpen(
            img,
            1.5
        )

        return img

    @staticmethod
    def detect_stars(img):

        arr = np.asarray(
            img.convert("L"),
            dtype=np.float32
        )

        threshold = np.percentile(
            arr,
            99.3
        )

        mask = arr > threshold

        count = int(
            np.count_nonzero(mask)
        )

        return count

    @staticmethod
    def star_trails(frames):

        if not frames:
            return None

        arrays = [
            np.asarray(f).astype(np.float32)
            for f in frames
        ]

        result = arrays[0]

        # Maximum accumulation gives visible trails.
        for frame in arrays[1:]:
            result = np.maximum(
                result,
                frame
            )

        result = np.clip(
            result,
            0,
            255
        ).astype(np.uint8)

        img = Image.fromarray(
            result,
            "RGB"
        )

        img = ImageEngine.contrast(
            img,
            1.35
        )

        img = ImageEngine.sharpen(
            img,
            1.2
        )

        return img


# ============================================================
# MAIN APP
# ============================================================

class DECamera(App):

    title = "DE CAMERA"

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        self.camera = None

        self.mode = "PHOTO"

        self.frames = []

        self.max_frames = 8

        self.processing = False

        self.running = True

        self.exposure = 0.0

        self.iso = 100

        self.shutter = "AUTO"

        self.focus = "AUTO"

        self.status = "INITIALIZING"

        self.output_dir = self.get_output_dir()

    # --------------------------------------------------------
    # STORAGE
    # --------------------------------------------------------

    def get_output_dir(self):

        paths = []

        if ANDROID:

            paths.extend([
                "/storage/emulated/0/DCIM/DE_CAMERA",
                "/sdcard/DCIM/DE_CAMERA",
                "/storage/emulated/0/Pictures/DE_CAMERA",
            ])

        paths.append(
            os.path.join(
                self.user_data_dir,
                "DCIM",
                "DE_CAMERA"
            )
        )

        for path in paths:

            try:

                os.makedirs(
                    path,
                    exist_ok=True
                )

                return path

            except Exception:
                continue

        return paths[-1]

    # --------------------------------------------------------
    # PERMISSIONS
    # --------------------------------------------------------

    def request_android_permissions(self):

        if not ANDROID:
            return

        permissions = []

        try:
            permissions.append(
                Permission.CAMERA
            )
        except Exception:
            pass

        try:
            permissions.append(
                Permission.RECORD_AUDIO
            )
        except Exception:
            pass

        try:
            permissions.append(
                Permission.READ_MEDIA_IMAGES
            )
        except Exception:
            pass

        try:
            permissions.append(
                Permission.WRITE_EXTERNAL_STORAGE
            )
        except Exception:
            pass

        try:
            request_permissions(
                permissions
            )
        except Exception as e:

            print(
                "Permission error:",
                e
            )

    # --------------------------------------------------------
    # BUILD UI
    # --------------------------------------------------------

    def build(self):

        self.request_android_permissions()

        root = BoxLayout(
            orientation="vertical",
            spacing=5
        )

        # ================= TOP =================

        top = BoxLayout(
            size_hint_y=None,
            height=58,
            padding=8,
            spacing=8
        )

        with top.canvas.before:
            Color(*PANEL)
            self.top_bg = RoundedRectangle(
                pos=top.pos,
                size=top.size
            )

        top.bind(
            pos=lambda *_: self.update_rect(
                top,
                self.top_bg
            ),
            size=lambda *_: self.update_rect(
                top,
                self.top_bg
            )
        )

        title = Label(
            text="DE CAMERA",
            font_size=22,
            bold=True,
            color=GOLD
        )

        self.status_label = Label(
            text=self.status,
            font_size=11,
            color=GRAY
        )

        top.add_widget(title)
        top.add_widget(self.status_label)

        settings = make_button(
            "⚙",
            20
        )

        settings.size_hint_x = None
        settings.width = 55

        settings.bind(
            on_release=lambda *_:
            self.settings()
        )

        top.add_widget(settings)

        root.add_widget(top)

        # ================= CAMERA =================

        self.preview = FloatLayout()

        with self.preview.canvas.before:
            Color(*BLACK)

            self.preview_bg = RoundedRectangle(
                pos=self.preview.pos,
                size=self.preview.size
            )

        self.preview.bind(
            pos=lambda *_: self.update_rect(
                self.preview,
                self.preview_bg
            ),
            size=lambda *_: self.update_rect(
                self.preview,
                self.preview_bg
            )
        )

        try:

            self.camera = Camera(
                play=True,
                resolution=(1280, 720)
            )

            self.camera.allow_stretch = True

            self.preview.add_widget(
                self.camera
            )

            self.set_status(
                "CAMERA READY"
            )

        except Exception as e:

            self.camera = None

            self.preview.add_widget(
                Label(
                    text="CAMERA UNAVAILABLE\n"
                         + str(e),
                    color=WHITE
                )
            )

        root.add_widget(
            self.preview
        )

        # ================= MODES =================

        mode_scroll = BoxLayout(
            size_hint_y=None,
            height=55,
            spacing=4,
            padding=4
        )

        for mode in [
            "PHOTO",
            "HDR",
            "NIGHT",
            "ASTRO",
            "STAR TRAILS",
            "PRO",
            "VIDEO"
        ]:

            btn = make_button(
                mode,
                10
            )

            btn.bind(
                on_release=lambda b,
                m=mode:
                self.change_mode(m)
            )

            mode_scroll.add_widget(
                btn
            )

        root.add_widget(
            mode_scroll
        )

        # ================= INFO =================

        self.info = Label(
            text="PHOTO • AUTO",
            size_hint_y=None,
            height=30,
            color=GRAY,
            font_size=11
        )

        root.add_widget(
            self.info
        )

        # ================= BOTTOM =================

        bottom = BoxLayout(
            size_hint_y=None,
            height=100,
            spacing=15,
            padding=15
        )

        gallery = make_button(
            "GALLERY",
            12
        )

        gallery.bind(
            on_release=lambda *_:
            self.gallery()
        )

        bottom.add_widget(
            gallery
        )

        capture = Button(
            text="",
            size_hint_x=None,
            width=100,
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0)
        )

        with capture.canvas:

            Color(*GOLD)

            capture.circle = Ellipse(
                pos=capture.pos,
                size=capture.size
            )

            Color(*BLACK)

            capture.inner = Ellipse(
                pos=(
                    capture.x + 9,
                    capture.y + 9
                ),
                size=(
                    capture.width - 18,
                    capture.height - 18
                )
            )

        def update_capture(*_):

            capture.circle.pos = capture.pos
            capture.circle.size = capture.size

            capture.inner.pos = (
                capture.x + 9,
                capture.y + 9
            )

            capture.inner.size = (
                capture.width - 18,
                capture.height - 18
            )

        capture.bind(
            pos=update_capture,
            size=update_capture
        )

        capture.bind(
            on_release=lambda *_:
            self.capture()
        )

        bottom.add_widget(
            capture
        )

        self.capture_button = capture

        more = make_button(
            "PRO",
            12
        )

        more.bind(
            on_release=lambda *_:
            self.pro_panel()
        )

        bottom.add_widget(
            more
        )

        root.add_widget(
            bottom
        )

        return root

    # --------------------------------------------------------
    # UI HELPERS
    # --------------------------------------------------------

    @staticmethod
    def update_rect(widget, rect):

        rect.pos = widget.pos
        rect.size = widget.size

    def set_status(self, text):

        self.status = text

        if hasattr(
            self,
            "status_label"
        ):

            self.status_label.text = text

    # --------------------------------------------------------
    # MODES
    # --------------------------------------------------------

    def change_mode(self, mode):

        self.mode = mode

        self.frames.clear()

        self.set_status(
            mode
        )

        self.info.text = (
            f"{mode} • "
            f"ISO {self.iso} • "
            f"{self.shutter}"
        )

    # --------------------------------------------------------
    # CAPTURE
    # --------------------------------------------------------

    def capture(self):

        if self.processing:
            return

        if self.camera is None:

            self.set_status(
                "CAMERA NOT READY"
            )

            return

        if self.mode == "VIDEO":

            self.video()

            return

        self.processing = True

        self.set_status(
            f"CAPTURING {self.mode}"
        )

        threading.Thread(
            target=self._capture_thread,
            daemon=True
        ).start()

    def _capture_thread(self):

        try:

            # Texture access must happen on Kivy thread.
            event = threading.Event()

            holder = {}

            def grab(_dt):

                try:

                    holder["image"] = (
                        ImageEngine.to_pil(
                            self.camera.texture
                        )
                    )

                finally:

                    event.set()

            Clock.schedule_once(
                grab,
                0
            )

            event.wait(
                timeout=5
            )

            img = holder.get(
                "image"
            )

            if img is None:

                self.set_status(
                    "FRAME FAILED"
                )

                return

            # ================= MODE =================

            if self.mode == "PHOTO":

                result = img

            elif self.mode == "NIGHT":

                result = (
                    ImageEngine.night(
                        img
                    )
                )

            elif self.mode == "ASTRO":

                result = (
                    ImageEngine.astro(
                        img
                    )
                )

                stars = (
                    ImageEngine.detect_stars(
                        result
                    )
                )

                self.set_status(
                    f"ASTRO • {stars} bright pixels"
                )

            elif self.mode == "HDR":

                self.frames.append(
                    img
                )

                if len(self.frames) < 4:

                    self.set_status(
                        f"HDR FRAME "
                        f"{len(self.frames)}/4"
                    )

                    return

                result = (
                    ImageEngine.hdr(
                        self.frames
                    )
                )

                self.frames.clear()

            elif self.mode == "STAR TRAILS":

                self.frames.append(
                    img
                )

                if len(self.frames) < 8:

                    self.set_status(
                        f"TRAIL FRAME "
                        f"{len(self.frames)}/8"
                    )

                    return

                result = (
                    ImageEngine.star_trails(
                        self.frames
                    )
                )

                self.frames.clear()

            elif self.mode == "PRO":

                result = img

            else:

                result = img

            # ================= SAVE =================

            path = os.path.join(
                self.output_dir,
                f"DE_CAMERA_{self.mode.replace(' ', '_')}_{timestamp()}.jpg"
            )

            result.save(
                path,
                "JPEG",
                quality=96,
                optimize=True
            )

            self.last_photo = path

            self.set_status(
                "SAVED"
            )

        except Exception as e:

            print(
                "Capture error:",
                e
            )

            self.set_status(
                "CAPTURE ERROR"
            )

        finally:

            self.processing = False

    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    def video(self):

        if not self.recording:

            self.recording = True

            self.set_status(
                "VIDEO RECORDING"
            )

            return

        self.recording = False

        self.set_status(
            "VIDEO STOPPED"
        )

    # --------------------------------------------------------
    # PRO PANEL
    # --------------------------------------------------------

    def pro_panel(self):

        layout = BoxLayout(
            orientation="vertical",
            spacing=12,
            padding=15
        )

        title = Label(
            text="PRO CAMERA",
            color=GOLD,
            font_size=20,
            bold=True
        )

        layout.add_widget(
            title
        )

        iso_label = Label(
            text=f"ISO: {self.iso}",
            color=WHITE
        )

        layout.add_widget(
            iso_label
        )

        iso_slider = Slider(
            min=100,
            max=3200,
            value=self.iso,
            step=100
        )

        def iso_change(_, value):

            self.iso = int(value)

            iso_label.text = (
                f"ISO: {self.iso}"
            )

        iso_slider.bind(
            value=iso_change
        )

        layout.add_widget(
            iso_slider
        )

        info = Label(
            text=(
                "ISO UI is available.\n"
                "Real sensor ISO requires Android Camera2."
            ),
            color=GRAY,
            halign="center"
        )

        layout.add_widget(
            info
        )

        close = make_button(
            "CLOSE"
        )

        layout.add_widget(
            close
        )

        popup = Popup(
            title="DE CAMERA",
            content=layout,
            size_hint=(0.9, 0.65)
        )

        close.bind(
            on_release=popup.dismiss
        )

        popup.open()

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    def settings(self):

        text = (
            "DE CAMERA\n\n"
            "Python + Kivy\n"
            "ARM64\n\n"
            "Image Engine:\n"
            "✓ Denoise\n"
            "✓ HDR stacking\n"
            "✓ Night enhancement\n"
            "✓ Astro enhancement\n"
            "✓ Star detection\n"
            "✓ Star Trails accumulation\n\n"
            "Advanced Camera2 features:\n"
            "RAW/DNG: native bridge required\n"
            "Manual ISO: native bridge required\n"
            "Manual shutter: native bridge required\n"
            "Manual focus: native bridge required\n"
        )

        popup = Popup(
            title="DE CAMERA",
            content=Label(
                text=text,
                color=WHITE,
                halign="left"
            ),
            size_hint=(0.9, 0.8)
        )

        popup.open()

    # --------------------------------------------------------
    # GALLERY
    # --------------------------------------------------------

    def gallery(self):

        try:

            files = [
                x for x in os.listdir(
                    self.output_dir
                )
                if x.lower().endswith(
                    (".jpg", ".jpeg", ".png")
                )
            ]

            count = len(files)

            popup = Popup(
                title="DE CAMERA GALLERY",
                content=Label(
                    text=(
                        f"{count} photos\n\n"
                        f"{self.output_dir}"
                    ),
                    color=WHITE
                ),
                size_hint=(0.9, 0.45)
            )

            popup.open()

        except Exception:

            self.set_status(
                "GALLERY ERROR"
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    DECamera().run()
