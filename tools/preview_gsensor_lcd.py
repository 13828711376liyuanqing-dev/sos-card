"""SAM | 2026-10-10 11:35 +08:00 | Check embedded font layout, not panel acceptance.

Uses repository glyph bitmaps and conservative unkerned advances. This is a
host layout preview; LVGL rasterization and the physical panel remain separate.
"""
from pathlib import Path
import re
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


class Font:
    def __init__(self, size):
        path = ROOT / f"ble_app_uart_c/Src/external/lvgl_8.3.1/src/font/lv_font_montserrat_{size}.c"
        source = path.read_text(encoding="utf-8")
        bitmap = source.split("glyph_bitmap[]", 1)[1].split("{", 1)[1].split("};", 1)[0]
        bitmap = re.sub(r"/\*.*?\*/", "", bitmap, flags=re.S)
        self.bitmap = bytes(int(value, 16) for value in re.findall(r"0x[0-9a-fA-F]+", bitmap))
        self.glyphs = [dict((key, int(value)) for key, value in re.findall(r"\.(\w+)\s*=\s*(-?\d+)", entry))
                       for entry in re.findall(r"\{([^{}]*\.bitmap_index[^{}]*)\}", source)]
        self.height = int(re.search(r"\.line_height\s*=\s*(\d+)", source)[1])
        self.baseline = int(re.search(r"\.base_line\s*=\s*(\d+)", source)[1])

    def width(self, text):
        return sum((self.glyphs[ord(char) - 31]["adv_w"] + 8) // 16 for char in text)

    def draw(self, image, x, y, text, width):
        assert self.width(text) <= width, (text, self.width(text), width)
        assert y + self.height <= image.height
        for char in text:
            g = self.glyphs[ord(char) - 31]
            stride = (g["box_w"] + 1) // 2
            top = y + self.height - self.baseline - g["box_h"] - g["ofs_y"]
            for row in range(g["box_h"]):
                for col in range(g["box_w"]):
                    byte = self.bitmap[g["bitmap_index"] + row * stride + col // 2]
                    alpha = (byte >> (4 if col % 2 == 0 else 0)) & 15
                    if alpha >= 8:
                        px, py = x + g["ofs_x"] + col, top + row
                        assert 0 <= px < 200 and 0 <= py < 200
                        image.putpixel((px, py), 0)
            x += (g["adv_w"] + 8) // 16


def main():
    small, large = Font(14), Font(20)
    for ble in ["READY", "FAIL", "--"]:
        for alarm in ["OFF", "ON", "--"]:
            assert small.width(f"BLE {ble}  ALARM {alarm}") <= 184
    for value in [-2000, 1999, 0]:
        for axis in "XYZ":
            assert large.width(f"{axis}  {value:+d} mg") <= 176
    dest = ROOT / "doc/gsensor_lcd_preview"
    dest.mkdir(exist_ok=True)
    for state in ["normal", "error", "pending"]:
        img = Image.new("L", (200, 200), 255)
        for row, text in enumerate(["SOS CARD", "BLE READY  ALARM --", "BAT 90% EST  4.21V", "CHARGING"]):
            small.draw(img, 8, 6 + row * 16, text, 184)
        draw = ImageDraw.Draw(img)
        draw.rectangle((8, 76, 191, 82), outline=0)
        draw.rectangle((9, 77, 172, 81), fill=0)
        small.draw(img, 8, 90, "XYZ TEST (mg)", 184)
        for row, (axis, value) in enumerate(zip("XYZ", [993, 107, -348])):
            text = f"{axis}  {value:+d} mg" if state == "normal" else f"{axis}  -- mg"
            large.draw(img, 12, 110 + row * 22, text, 176)
        small.draw(img, 8, 181, {"normal": "LIVE / 2-3s", "error": "READ ERROR", "pending": "WAIT DATA"}[state], 184)
        img.save(dest / f"{state}.png")
    print("PASS: worst-case text bounds; normal/error/pending previews generated.")


if __name__ == "__main__":
    main()
