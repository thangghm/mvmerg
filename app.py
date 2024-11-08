from flask import Flask, request, jsonify
import requests
import tempfile
import os
import subprocess
import boto3
from botocore.exceptions import NoCredentialsError
import uuid
from dotenv import load_dotenv

app = Flask(__name__)

#Tai bien moi truong tu file .env
load_dotenv()

#lay thong tin tu bien moi truong
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')

#kiem tra cac bien moi truong
if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, S3_BUCKET_NAME, CLOUDFRONT_DOMAIN]):
    raise Exception("Vui long dam bao cac bien moi truong duoc thiet lap.")

#khoi tao client s3 va xac thuc
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_DEFAULT_REGION
)

@app.route('/merge', methods=['POST'])
def merge_audio_image():
    data = request.get_json()
    mp3_url = data.get('mp3_url')
    jpg_url = data.get('jpg_url')
    
    if not mp3_url or not jpg_url:
        return jsonify({'error': 'Vui lòng cung cấp mp3_url và jpg_url'}), 400
    
    try:
        # Tạo file tạm cho MP3 và JPG
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file, \
             tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as jpg_file, \
             tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:

            # Tải file MP3
            r_mp3 = requests.get(mp3_url)
            if r_mp3.status_code != 200:
                return jsonify({'error': 'Không thể tải file MP3'}), 400
            mp3_file.write(r_mp3.content)
            mp3_file.flush()

            # Tải file JPG
            r_jpg = requests.get(jpg_url)
            if r_jpg.status_code != 200:
                return jsonify({'error': 'Không thể tải file JPG'}), 400
            jpg_file.write(r_jpg.content)
            jpg_file.flush()

            # Sử dụng ffmpeg để ghép audio và ảnh thành video với kích thước tối ưu
            command = [
                'ffmpeg',
                '-loop', '1',         # Lặp lại hình ảnh
                '-i', jpg_file.name,
                '-i', mp3_file.name,
                '-c:v', 'libx264',
                '-preset', 'veryfast', # Sử dụng preset veryfast để giảm kích thước file
                '-crf', '28',          # Chất lượng video, giá trị cao hơn để giảm kích thước file
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',           # Dừng khi file ngắn nhất kết thúc (ở đây là âm thanh)
                output_file.name,
                '-y'  # Ghi đè nếu file output đã tồn tại
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if result.returncode != 0:
                return jsonify({'error': 'Lỗi khi ghép file', 'detail': result.stderr.decode()}), 500

            # Upload file output lên S3 (không thiết lập ACL)
            s3_key = f"videos/{uuid.uuid4()}.mp4"  # Tạo tên file duy nhất
            try:
                s3_client.upload_file(
                    output_file.name,
                    S3_BUCKET_NAME,
                    s3_key,
                    ExtraArgs={
                        'ContentType': 'video/mp4'
                    }
                )
            except NoCredentialsError:
                return jsonify({'error': 'Không tìm thấy thông tin AWS credentials'}), 500

            # Tạo URL truy cập file thông qua CloudFront
            cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"

            # Trả về URL của CloudFront
            return jsonify({'url': cloudfront_url})

    finally:
        # Xóa các file tạm
        if os.path.exists(mp3_file.name):
            os.unlink(mp3_file.name)
        if os.path.exists(jpg_file.name):
            os.unlink(jpg_file.name)
        if os.path.exists(output_file.name):
            os.unlink(output_file.name)

@app.route('/')
def index():
    return "Hello, World!"

if __name__ == '__main__':
    app.run(debug=True)
