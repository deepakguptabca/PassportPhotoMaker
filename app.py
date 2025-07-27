from flask import Flask, request, render_template, send_file
from PIL import Image, ImageOps
from io import BytesIO
import requests
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)

# Load API keys from environment variables or fallback values
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY", "V1zPsUPoWSEis2Jmn2ij2jkM")

# Cloudinary configuration
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

    copies = int(request.form.get("copies", 6))
    passport_width = int(request.form.get("width", 400))
    passport_height = int(request.form.get("height", 400))

    # Step 1: Background Removal
    response = requests.post(
        'https://api.remove.bg/v1.0/removebg',
        files={'image_file': input_image},
        data={'size': 'auto'},
        headers={'X-Api-Key': REMOVE_BG_API_KEY}
    )

    if response.status_code != 200:
        return f"Background removal failed: {response.text}", 500

    bg_removed = BytesIO(response.content)

    # Step 2: Upload to Cloudinary
    bg_removed.seek(0)
    upload_result = cloudinary.uploader.upload(bg_removed, resource_type="image")
    image_url = upload_result.get("secure_url")

    if not image_url:
        return "Cloudinary upload failed", 500

    # Step 3: Enhance via Cloudinary
    transformed_url = image_url.replace(
        "/upload/",
        "/upload/c_fill,g_face,w_600,h_600,e_improve,e_sharpen/"
    )

    # Step 4: Download, prepare passport photo
    img_data = requests.get(transformed_url).content
    img = Image.open(BytesIO(img_data))
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        passport_img = background
    else:
        passport_img = img.convert("RGB")

    border = int(request.form.get("border", 5))  # default to 10 if not provided


    passport_img = passport_img.resize((passport_width, passport_height))
    passport_img = ImageOps.expand(passport_img, border=border, fill='black')

    # Step 5: Create A4 sheet
    a4_w, a4_h = 2480, 3508
    a4 = Image.new("RGB", (a4_w, a4_h), "white")

    margin = 0
    spacing = int(request.form.get("spacing", 50))

    x, y = margin, margin
    paste_w = passport_width + 10
    paste_h = passport_height + 10

    for _ in range(copies):
        if x + paste_w > a4_w:
            x = margin
            y += paste_h + spacing
        if y + paste_h > a4_h:
            break
        a4.paste(passport_img, (x, y))
        x += paste_w + spacing

    output = BytesIO()
    a4.save(output, format="JPEG")
    output.seek(0)

    return send_file(output, mimetype="image/jpeg", as_attachment=True, download_name="passport-sheet.jpg")

if __name__ == '__main__':
    app.run(debug=True)
