#!/usr/bin/env python3
"""
EasyPaper Icon Generator
Generates all required icon formats (.icns, .ico, PNGs, SVG) from the master artwork
and applies them to src-tauri/icons, frontend/public, and frontend/dist.
"""

import os
import sys
import shutil
import base64
import tempfile
import subprocess
from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE_IMAGE = "/Users/chunghj/.gemini/antigravity/brain/b5e1be31-6665-4c83-814e-80cdd9c70ea9/easypaper_neon_stack_1789314029658.jpg"

TAURI_ICONS_DIR = os.path.join(REPO_ROOT, "src-tauri", "icons")
FRONTEND_PUBLIC_DIR = os.path.join(REPO_ROOT, "frontend", "public")
FRONTEND_DIST_DIR = os.path.join(REPO_ROOT, "frontend", "dist")

def create_master_1024(source_path: str) -> Image.Image:
    """Extract squircle, apply Apple-standard superellipse corner mask, drop shadow, and place on 1024x1024 canvas."""
    src = Image.open(source_path).convert("RGBA")
    
    # Crop squircle bounding box
    crop_box = (175, 178, 849, 842)
    sq = src.crop(crop_box)
    w, h = sq.size
    
    # Rounded squircle mask
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    r = int(w * 0.22)
    draw.rounded_rectangle([0, 0, w, h], radius=r, fill=255)
    
    sq_masked = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sq_masked.paste(sq, (0, 0), mask)
    
    # Scale to macOS standard grid (approx 85% of 1024 = 870px)
    target_size = 870
    sq_resized = sq_masked.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    # Canvas with shadow
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    pos = ((1024 - target_size) // 2, (1024 - target_size) // 2)
    
    # Soft ambient drop shadow
    shadow_mask = Image.new("L", (target_size, target_size), 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shadow_draw.rounded_rectangle([0, 0, target_size, target_size], radius=int(target_size * 0.22), fill=130)
    
    shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 140))
    shadow.paste(shadow_layer, (pos[0], pos[1] + 14), shadow_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    
    canvas.paste(shadow, (0, 0), shadow)
    canvas.paste(sq_resized, pos, sq_resized)
    return canvas

def generate_icons():
    print(f"[1/5] Creating 1024x1024 master icon from {SOURCE_IMAGE}...")
    master = create_master_1024(SOURCE_IMAGE)
    
    master_path = os.path.join(TAURI_ICONS_DIR, "icon_1024.png")
    master.save(master_path, format="PNG")
    print(f"Saved master icon to {master_path}")
    
    # 1. Generate src-tauri/icons/ PNG sizes
    tauri_sizes = {
        "32x32.png": 32,
        "64x64.png": 64,
        "128x128.png": 128,
        "128x128@2x.png": 256,
        "Square30x30Logo.png": 30,
        "Square44x44Logo.png": 44,
        "Square71x71Logo.png": 71,
        "Square89x89Logo.png": 89,
        "Square107x107Logo.png": 107,
        "Square142x142Logo.png": 142,
        "Square150x150Logo.png": 150,
        "Square284x284Logo.png": 284,
        "Square310x310Logo.png": 310,
        "StoreLogo.png": 50,
        "icon.png": 512,
    }
    
    print("[2/5] Generating Tauri PNG icons...")
    for filename, size in tauri_sizes.items():
        out_path = os.path.join(TAURI_ICONS_DIR, filename)
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(out_path, format="PNG")
        print(f"  -> {filename} ({size}x{size})")
        
    # 2. Generate macOS .icns via iconutil
    print("[3/5] Generating macOS icon.icns via iconutil...")
    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = os.path.join(tmpdir, "icon.iconset")
        os.makedirs(iconset_dir, exist_ok=True)
        
        icns_sizes = [
            ("icon_16x16.png", 16),
            ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32),
            ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512),
            ("icon_512x512@2x.png", 1024),
        ]
        
        for name, sz in icns_sizes:
            resized = master.resize((sz, sz), Image.Resampling.LANCZOS)
            resized.save(os.path.join(iconset_dir, name), format="PNG")
            
        icns_dest = os.path.join(TAURI_ICONS_DIR, "icon.icns")
        subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_dest], check=True)
        print(f"  -> icon.icns generated ({os.path.getsize(icns_dest):,} bytes)")

    # 3. Generate Windows icon.ico
    print("[4/5] Generating Windows icon.ico...")
    ico_dest = os.path.join(TAURI_ICONS_DIR, "icon.ico")
    master.save(ico_dest, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"  -> icon.ico generated ({os.path.getsize(ico_dest):,} bytes)")
    
    # 4. Generate frontend icons
    print("[5/5] Generating frontend public & dist icons...")
    frontend_sizes = {
        "app-icon.png": 512,
        "icon-512.png": 512,
        "icon-192.png": 192,
        "apple-touch-icon.png": 180,
        "favicon-32x32.png": 32,
        "favicon-16x16.png": 16,
    }
    
    targets = [FRONTEND_PUBLIC_DIR]
    if os.path.isdir(FRONTEND_DIST_DIR):
        targets.append(FRONTEND_DIST_DIR)
        
    for target_dir in targets:
        os.makedirs(target_dir, exist_ok=True)
        for filename, size in frontend_sizes.items():
            out_path = os.path.join(target_dir, filename)
            resized = master.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(out_path, format="PNG")
            
        # favicon.ico
        fav_ico_dest = os.path.join(target_dir, "favicon.ico")
        master.save(fav_ico_dest, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        
        # icon.svg wrapping 512x512 base64 PNG
        img_512 = master.resize((512, 512), Image.Resampling.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp_png:
            img_512.save(tmp_png.name, format="PNG")
            with open(tmp_png.name, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        
        svg_content = f'''<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <image href="data:image/png;base64,{b64}" x="0" y="0" width="512" height="512" />
</svg>
'''
        with open(os.path.join(target_dir, "icon.svg"), "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"  -> Updated {target_dir}")

    print("\nAll EasyPaper icon assets have been generated successfully!")

if __name__ == "__main__":
    generate_icons()
