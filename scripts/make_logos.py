"""Crop final - sin texto. Solo el cuerpo del ninja."""
from pathlib import Path
import numpy as np
from PIL import Image

src = Path("assets/logo.png")
img = Image.open(src)
print(f"Original: {img.size} mode={img.mode}")

# Crop mas agresivo en Y para evitar el texto
# Imagen original 2816x1536. El texto esta aprox y > 1100
# Ninja va de y=440 a y=1100
ninja_box = (570, 440, 1530, 1080)
ninja = img.crop(ninja_box)
ninja_rgba = ninja.convert("RGBA")
arr = np.array(ninja_rgba)
# Quitar fondo blanco
mask_white = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
arr[mask_white, 3] = 0
ninja_clean = Image.fromarray(arr, "RGBA")
# Trim transparente
bbox = ninja_clean.getbbox()
ninja_clean = ninja_clean.crop(bbox)
# Pad
pad = max(ninja_clean.size) // 10
new_w = ninja_clean.size[0] + pad * 2
new_h = ninja_clean.size[1] + pad * 2
padded = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
padded.paste(ninja_clean, (pad, pad), ninja_clean)
ninja_clean = padded
ninja_clean.thumbnail((512, 512), Image.LANCZOS)
ninja_path = Path("static/img/ninja-mascot.png")
ninja_clean.save(ninja_path, "PNG", optimize=True)
print(f"Ninja: {ninja_clean.size} -> {ninja_path.stat().st_size // 1024} KB")

# Favicon
fav = ninja_clean.copy()
fav.thumbnail((32, 32), Image.LANCZOS)
fav.save("static/img/favicon.png", "PNG", optimize=True)
print(f"Favicon 32x32: {fav.size}")

# Apple touch 180
apple = ninja_clean.copy()
apple.thumbnail((180, 180), Image.LANCZOS)
apple.save("static/img/apple-touch-icon.png", "PNG", optimize=True)
print(f"Apple touch 180: {apple.size}")

print("OK")
