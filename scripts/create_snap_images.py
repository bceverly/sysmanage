#!/usr/bin/env python3
"""
Generate Snap Store images (icon and banner) for SysManage
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Color scheme from the existing logo
CYAN = (91, 212, 245)  # #5BD4F5
DARK_BG = (30, 41, 59)  # Dark slate
LIGHT_TEXT = (248, 250, 252)  # Almost white
GRADIENT_START = (15, 23, 42)  # Darker slate
GRADIENT_END = (30, 58, 138)  # Dark blue

def create_icon(output_path, size=512):
    """
    Create a clean 512x512 icon for the Snap Store
    Uses the existing logo with a subtle background
    """
    # Load the existing logo
    logo_path = "frontend/public/logo512.png"
    logo = Image.open(logo_path).convert("RGBA")

    # Create a new image with a gradient background
    img = Image.new('RGB', (size, size), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Create a subtle radial gradient effect
    for i in range(size // 2, 0, -1):
        alpha = i / (size // 2)
        color = tuple(int(GRADIENT_START[j] * alpha + GRADIENT_END[j] * (1 - alpha))
                     for j in range(3))
        draw.ellipse(
            [(size//2 - i, size//2 - i), (size//2 + i, size//2 + i)],
            fill=color
        )

    # Paste the logo in the center
    img.paste(logo, (0, 0), logo)

    img.save(output_path, 'PNG')
    print(f"Created icon: {output_path}")

def create_banner(output_path, width=1920, height=480):
    """
    Create a 1920x480 banner for the Snap Store
    """
    # Create gradient background
    img = Image.new('RGB', (width, height), GRADIENT_START)
    draw = ImageDraw.Draw(img)

    # Draw gradient
    for i in range(height):
        alpha = i / height
        color = tuple(int(GRADIENT_START[j] * (1 - alpha) + GRADIENT_END[j] * alpha)
                     for j in range(3))
        draw.line([(0, i), (width, i)], fill=color)

    # Load and add the logo on the left
    logo_path = "frontend/public/logo512.png"
    logo = Image.open(logo_path).convert("RGBA")

    # Resize logo to fit nicely in the banner
    logo_size = int(height * 0.6)
    logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

    # Position logo
    logo_x = int(height * 0.3)
    logo_y = (height - logo_size) // 2
    img.paste(logo, (logo_x, logo_y), logo)

    # Add text
    try:
        # Try to use a nice font
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    except:
        # Fallback to default
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw "SysManage" text
    text_x = logo_x + logo_size + 60
    text_y_main = height // 2 - 70

    draw.text((text_x, text_y_main), "SysManage", font=font_large, fill=LIGHT_TEXT)

    # Draw tagline
    text_y_sub = text_y_main + 130
    draw.text((text_x, text_y_sub), "Centralized System Management",
              font=font_small, fill=CYAN)

    img.save(output_path, 'PNG')
    print(f"Created banner: {output_path}")

def main():
    # Change to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)

    # Create output directory
    os.makedirs("installer/snap/gui", exist_ok=True)

    # Generate icon
    icon_path = "installer/snap/gui/icon.png"
    create_icon(icon_path)

    # Generate banner
    banner_path = "installer/snap/gui/banner.png"
    create_banner(banner_path)

    print("\nSnap Store images created successfully!")
    print(f"  Icon: {icon_path}")
    print(f"  Banner: {banner_path}")

if __name__ == "__main__":
    main()
