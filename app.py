from flask import Flask, request, render_template, send_file,render_template_string,session
from PIL import Image, ImageOps
from io import BytesIO
import requests
import cloudinary
import cloudinary.uploader
import os
import base64
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from datetime import datetime, timedelta
import pytz
import redis

app = Flask(__name__)

app.secret_key = 'secret_key'  


redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

# === Rate limiter setup ===
limiter = Limiter(get_remote_address, app=app,storage_uri=redis_url,)

#==exempt users with a secret code from rate limiting ===
@limiter.request_filter
def exempt_users_with_secret_code():
    return session.get('exempt') == True


#=== Secret key for session management ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        code = request.form.get('secret_code')
        if code == "UNLIMITED_ACESS":
            session['exempt'] = True
            return "Exempted from rate limit!"
        else:
            session['exempt'] = False
            return "Invalid code"
    return   """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <style>
        body {
            font-family: sans-serif;
            background: #f0f8ff;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }

        .login-box {
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }

        input[type="text"] {
            padding: 10px;
            width: 200px;
            margin: 10px 0;
            border: 1px solid #ccc;
            border-radius: 5px;
        }

        input[type="submit"] {
            padding: 10px 20px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }

        input[type="submit"]:hover {
            background: #0056b3;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Premium Access</h2>
        <form method="post">
            <label>Enter Your Premium Code:</label><br>
            <input type="text" name="secret_code" required><br>
            <input type="submit" value="Login">
        </form>
    </div>
</body>
</html>
"""

#=== Error handler for rate limit exceeded ===

@app.errorhandler(RateLimitExceeded)
def handle_ratelimit(e):
    retry_after = e.retry_after if e.retry_after is not None else 600
    india_tz = pytz.timezone('Asia/Kolkata')
    next_time = datetime.now(india_tz) + timedelta(seconds=retry_after)
    formatted_time = next_time.strftime("%I:%M:%S %p")  

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rate Limit Exceeded</title>
        <style>
            body {{
                font-family: sans-serif;
                background: #fff3f3;
                text-align: center;
                padding: 2rem;
                color: #d00000;
            }}
            h1 {{
                font-size: 2rem;
            }}
        </style>
    </head>
    <body>
        <h1>⚠️ Rate Limit Exceeded</h1>
        <p>You’ve reached the limit. You can try again at <strong>{formatted_time}</strong>.</p>
        <p>Contact us at <a href="tel:+919718958028"><strong>+91 97189 58028</strong></a> for unlimited access.</p>


    </body>
    </html>
    """
    return render_template_string(html), 429


# Cloudinary and remove.bg API setup
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
@limiter.limit("25 per day")
def process():
    print("==== /process endpoint hit ====")

    if 'image' not in request.files:
        print("DEBUG: No image in request")
        return "No image uploaded", 400

    file = request.files['image']
    print(f"DEBUG: Received image file: {file.filename}")
    input_image = file.read()

    # Layout settings
    passport_width = 384
    passport_height = 472
    border = 2
    spacing = 60
    margin_x = 50
    margin_y = 50
    horizontal_gap = 10
    a4_w, a4_h = 2480, 3508
    copies = int(request.form.get("copies", 1))
    print(f"DEBUG: Copies requested = {copies}")

    # Step 1: Background removal
    print("DEBUG: Sending image to remove.bg...")
    response = requests.post(
        'https://api.remove.bg/v1.0/removebg',
        files={'image_file': input_image},
        data={'size': 'auto'},
        headers={'X-Api-Key': REMOVE_BG_API_KEY}
    )
    print(f"DEBUG: remove.bg response status = {response.status_code}")
    if response.status_code != 200:
        print(f"ERROR: Background removal failed - {response.text}")
        return f"Background removal failed: {response.text}", 500

    bg_removed = BytesIO(response.content)
    img = Image.open(bg_removed)
    print(f"DEBUG: Image mode after background removal: {img.mode}")

    if img.mode in ("RGBA", "LA"):
        print("DEBUG: Converting transparent background to white")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        processed_img = background
    else:
        processed_img = img.convert("RGB")

    # Step 3: Upload to Cloudinary
    buffer = BytesIO()
    processed_img.save(buffer, format="PNG")
    buffer.seek(0)
    print("DEBUG: Uploading to Cloudinary...")
    upload_result = cloudinary.uploader.upload(buffer, resource_type="image")
    image_url = upload_result.get("secure_url")
    print(f"DEBUG: Cloudinary URL: {image_url}")
    if not image_url:
        print("ERROR: Failed to get image URL from Cloudinary.")
        return "Cloudinary upload failed", 500

    # Step 4: Upscale via Hugging Face
    print("DEBUG: Downloading image from Cloudinary for enhancement...")
    cloud_img_data = requests.get(image_url).content
    img = Image.open(BytesIO(cloud_img_data))
    buf = BytesIO()
    img.save(buf, format="PNG")
    base64_img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    hf_api = "https://nightfury-image-face-upscale-restoration-gfpgan.hf.space/api/predict"
    payload = {
        "data": [
            base64_img,
            "v1.4",
            2.0
        ]
    }
    print("DEBUG: Sending image to Hugging Face enhancer...")
    response = requests.post(hf_api, json=payload)
    print(f"DEBUG: HF response status = {response.status_code}")
    if response.status_code != 200:
        print(f"ERROR: HF enhancement failed - {response.text}")
        return f"Upscaler API failed: {response.text}", 500

    result = response.json()
    output_base64 = result["data"][0].split(",")[1]
    img_data = base64.b64decode(output_base64)
    img = Image.open(BytesIO(img_data))
    print(f"DEBUG: Enhanced image mode = {img.mode}")

    # Step 5: RGB conversion
    if img.mode in ("RGBA", "LA"):
        print("DEBUG: Replacing transparency with white again post-enhancement")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        passport_img = background
    else:
        passport_img = img.convert("RGB")

    # Step 6: Resize and border
    passport_img = passport_img.resize((passport_width, passport_height), Image.LANCZOS)
    passport_img = ImageOps.expand(passport_img, border=border, fill='black')
    print(f"DEBUG: Passport image size after border = {passport_img.size}")

    # Step 7: Compose A4 layout
    a4 = Image.new("RGB", (a4_w, a4_h), "white")
    x, y = margin_x, margin_y
    paste_w = passport_width + 2 * border
    paste_h = passport_height + 2 * border
    placed = 0

    print("DEBUG: Placing images onto A4 sheet...")
    for _ in range(copies):
        if x + paste_w > a4_w:
            x = margin_x
            y += paste_h + spacing
        if y + paste_h > a4_h:
            print("DEBUG: Reached end of page")
            break
        a4.paste(passport_img, (x, y))
        print(f"DEBUG: Placed copy {placed + 1} at x={x}, y={y}")
        x += paste_w + horizontal_gap
        placed += 1

    print(f"DEBUG: Total placed = {placed}")

    # Step 8: Export to PDF
    output = BytesIO()
    a4.save(output, format="PDF", dpi=(300, 300))
    output.seek(0)
    print("DEBUG: Returning PDF file to client.")

    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="passport-sheet.pdf")


if __name__ == '__main__':
    app.run(debug=True)
