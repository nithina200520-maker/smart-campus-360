import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

img_dir = Path("app/static/images")
img_dir.mkdir(parents=True, exist_ok=True)

placeholders = [
    ("placeholder_node.jpg", "Campus Point of Interest", (30, 58, 138), (255, 255, 255)),
    ("placeholder_gate.jpg", "Main Campus Entrance Gate", (15, 23, 42), (245, 158, 11)),
    ("placeholder_admin.jpg", "Administrative Block Reception", (30, 58, 138), (255, 255, 255)),
    ("placeholder_office.jpg", "Principal & Dean Executive Office", (88, 28, 135), (255, 255, 255)),
    ("placeholder_lab.jpg", "Computer Science & AI Labs", (37, 99, 235), (255, 255, 255)),
    ("placeholder_library.jpg", "Central Library & Digital Reading Room", (180, 83, 9), (255, 255, 255)),
    ("placeholder_canteen.jpg", "Campus Canteen & Cafeteria", (185, 28, 28), (255, 255, 255)),
    ("placeholder_workshop.jpg", "Mechanical Engineering Workshops", (71, 85, 105), (255, 255, 255)),
    ("placeholder_sports.jpg", "College Sports Ground & Pavilion", (21, 128, 61), (255, 255, 255)),
    ("placeholder_audi.jpg", "Sir M. Visvesvaraya Auditorium", (109, 40, 217), (255, 255, 255)),
    ("food_dosa.jpg", "Crispy Masala Dosa", (217, 119, 6), (255, 255, 255)),
    ("food_idli.jpg", "Idli Vada Sambar Combo", (202, 138, 4), (255, 255, 255)),
    ("food_meals.jpg", "South Indian Thali Meals", (22, 101, 52), (255, 255, 255)),
    ("food_friedrice.jpg", "Veg Fried Rice & Manchurian", (194, 65, 12), (255, 255, 255)),
    ("food_coffee.jpg", "South Indian Filter Coffee", (120, 53, 15), (255, 255, 255)),
    ("food_juice.jpg", "Fresh Mint Lemon Juice", (13, 148, 136), (255, 255, 255)),
    ("food_samosa.jpg", "Hot Samosas with Chutney", (234, 88, 12), (255, 255, 255)),
]

for filename, text, bg_color, text_color in placeholders:
    filepath = img_dir / filename
    if not filepath.exists():
        im = Image.new("RGB", (640, 360), color=bg_color)
        draw = ImageDraw.Draw(im)
        # Decorative border
        draw.rectangle([10, 10, 630, 350], outline=(255, 255, 255, 128), width=3)
        # Add labels
        header = "GEC MOSALEHOSAHALLI (HASSAN)"
        sub = "[SAMPLE DATA - CALIBRATION PHOTO]"
        draw.text((320, 100), header, fill=(245, 158, 11), anchor="mm")
        draw.text((320, 180), text, fill=text_color, anchor="mm")
        draw.text((320, 260), sub, fill=(203, 213, 225), anchor="mm")
        im.save(filepath, "JPEG", quality=85)

print("Generated sample placeholder images successfully.")
