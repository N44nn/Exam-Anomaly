"""Create sample_sheet.png for the PaddleOCR demo (S047 / exam 5)."""
from PIL import Image, ImageDraw, ImageFont

lines = [
    "Q1: A stack is LIFO. Push puts an item on top and pop removes the top item.",
    "Q2: A binary search tree orders keys so left children are smaller and right larger.",
    "Q3: Breadth first search uses a queue to visit nodes level by level.",
    "Q4: Big O notation bounds how an algorithm scales. Binary search is O(log n).",
    "Q5: Kruskal builds an MST by sorting edges and adding edges that do not cycle.",
]

font = None
for f in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
    "arial.ttf",
]:
    try:
        font = ImageFont.truetype(f, 28)
        break
    except Exception:
        pass
font = font or ImageFont.load_default()

img = Image.new("RGB", (1600, 60 + 55 * len(lines)), "white")
d = ImageDraw.Draw(img)
for i, l in enumerate(lines):
    d.text((24, 30 + 55 * i), l, fill="black", font=font)
img.save("sample_sheet.png")
print("saved sample_sheet.png")
