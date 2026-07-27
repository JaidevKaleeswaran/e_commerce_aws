import os
import boto3
import mimetypes

bucket_name = 'website-bucket-jaidev'
folder_path = 'webpage'

s3 = boto3.client('s3', region_name='us-west-1')

for filename in os.listdir(folder_path):
    file_path = os.path.join(folder_path, filename)
    if os.path.isfile(file_path):
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        print(f"Uploading {filename} to {bucket_name} as {content_type}...")
        with open(file_path, 'rb') as data:
            s3.put_object(
                Bucket=bucket_name,
                Key=filename,
                Body=data,
                ContentType=content_type
            )
print("Upload complete!")
