import os
import boto3
import mimetypes

bucket_name = 'website-bucket-jaidev'
folder_path = 'webpage'
region = 'us-west-1'

s3 = boto3.client('s3', region_name=region)

# Ensure common web MIME types are properly mapped
MIME_OVERRIDES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.mjs': 'application/javascript; charset=utf-8',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.ico': 'image/x-icon'
}

print(f"Starting upload from directory '{folder_path}' to S3 bucket '{bucket_name}'...")

count = 0
for root, _, files in os.walk(folder_path):
    for filename in files:
        if filename.startswith('.'):
            continue
        file_path = os.path.join(root, filename)
        # Compute relative key path inside S3 bucket
        rel_path = os.path.relpath(file_path, folder_path)
        s3_key = rel_path.replace(os.sep, '/')

        ext = os.path.splitext(filename)[1].lower()
        if ext in MIME_OVERRIDES:
            content_type = MIME_OVERRIDES[ext]
        else:
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'application/octet-stream'

        print(f"Uploading {s3_key} -> s3://{bucket_name}/{s3_key} ({content_type})...")
        with open(file_path, 'rb') as data:
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=data,
                ContentType=content_type
            )
        count += 1

print(f"Upload complete! Successfully uploaded {count} file(s).")
