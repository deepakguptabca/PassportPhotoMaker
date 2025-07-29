from flask import Flask, request, render_template, send_file
from PIL import Image, ImageOps
from io import BytesIO
import requests
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)

# API keys
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY", "dSKbkJd9Be1o2wAsj38G6aX7")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "dcajb02df"),
    api_key=os.getenv("CLOUDINARY_API_KEY", "862192414383365"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "TDuIQPd_iRf5_ThniMlwn8Gaaq8")
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    if 'image' not in request.files:
        return "No image uploaded", 400

    file = request.files['image']
    input_image = file.read()

       # 📌 Fixed layout values based on DFD.pdf
    passport_width = 384
    passport_height = 472
    border = 2
    spacing = 60
    margin_x = 50
    margin_y = 50
    horizontal_gap = 10
    a4_w, a4_h = 2480, 3508  # A4 @ 300 DPI

    copies = int(request.form.get("copies", 1))

    # =====================================================
    # OPTIONAL: Background Removal (Uncomment to enable)
    # =====================================================
    # response = requests.post(
    #     'https://api.remove.bg/v1.0/removebg',
    #     files={'image_file': input_image},
    #     data={'size': 'auto'},
    #     headers={'X-Api-Key': REMOVE_BG_API_KEY}
    # )
    # if response.status_code != 200:
    #     return f"Background removal failed: {response.text}", 500
    # bg_removed = BytesIO(response.content)

    # TEMP: Skip background removal for testing
    print("Skipping background removal (using original image)")
    bg_removed = BytesIO(input_image)

    # Upload to Cloudinary
    bg_removed.seek(0)
    upload_result = cloudinary.uploader.upload(bg_removed, resource_type="image")
    image_url = upload_result.get("secure_url")
    if not image_url:
        return "Cloudinary upload failed", 500

    # Cloudinary resize + enhancement
    transformed_url = image_url.replace(
        "/upload/",
        f"/upload/c_fill,g_face,w_{passport_width},h_{passport_height},e_improve,e_sharpen/"
    )
    img_data = requests.get(transformed_url).content
    img = Image.open(BytesIO(img_data))

    # Convert to RGB if needed
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        passport_img = background
    else:
        passport_img = img.convert("RGB")

    # Resize and add border
    passport_img = passport_img.resize((passport_width, passport_height), Image.LANCZOS)
    passport_img = ImageOps.expand(passport_img, border=border, fill='black')

    # Create A4 sheet
    a4 = Image.new("RGB", (a4_w, a4_h), "white")
    x, y = margin_x, margin_y
    paste_w = passport_width + 2 * border
    paste_h = passport_height + 2 * border
    placed = 0

    for _ in range(copies):
        if x + paste_w > a4_w:
            x = margin_x
            y += paste_h + spacing
        if y + paste_h > a4_h:
            break
        a4.paste(passport_img, (x, y))
        x += paste_w + horizontal_gap
        placed += 1

    # Save as PDF with 300 DPI (exact match to DFD)
    output = BytesIO()
    a4.save(output, format="PDF", dpi=(300, 300))
    output.seek(0)

    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="passport-sheet.pdf")

if __name__ == '__main__':
    app.run(debug=True)
