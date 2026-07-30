import boto3
import time
import sys

REGION = 'us-west-1'
S3_BUCKET_NAME = 'website-bucket-jaidev'

def delete_s3():
    s3_resource = boto3.resource('s3', region_name=REGION)
    bucket = s3_resource.Bucket(S3_BUCKET_NAME)
    try:
        bucket.load()
    except Exception:
        print(f"S3 bucket {S3_BUCKET_NAME} does not exist or access denied.")
        return
        
    print(f"Emptying S3 bucket '{S3_BUCKET_NAME}'...")
    try:
        bucket.objects.all().delete()
        print(f"Deleting S3 bucket '{S3_BUCKET_NAME}'...")
        bucket.delete()
        print("Bucket deleted successfully.")
    except Exception as e:
        print(f"Error emptying/deleting bucket: {e}")

def delete_cloudfront():
    cloudfront_client = boto3.client('cloudfront', region_name=REGION)
    
    # 1. Delete distribution
    dists = cloudfront_client.list_distributions().get('DistributionList', {}).get('Items', [])
    dist = next((d for d in dists if d['Comment'] == S3_BUCKET_NAME), None)
    
    if dist:
        dist_id = dist['Id']
        config_req = cloudfront_client.get_distribution_config(Id=dist_id)
        config = config_req['DistributionConfig']
        etag = config_req['ETag']
        
        if config['Enabled']:
            print(f"Disabling CloudFront distribution {dist_id}...")
            config['Enabled'] = False
            cloudfront_client.update_distribution(DistributionConfig=config, Id=dist_id, IfMatch=etag)
            
            print(f"Waiting for distribution {dist_id} to be disabled (this can take ~5 mins)...")
            waiter = cloudfront_client.get_waiter('distribution_deployed')
            waiter.wait(Id=dist_id)
            print(f"Distribution {dist_id} disabled.")
            
        config_req = cloudfront_client.get_distribution_config(Id=dist_id)
        etag = config_req['ETag']
        
        print(f"Deleting CloudFront distribution {dist_id}...")
        cloudfront_client.delete_distribution(Id=dist_id, IfMatch=etag)
        print("CloudFront Distribution deleted.")
    else:
        print("No CloudFront distribution found.")
        
    # 2. Delete OAC
    oac_list = cloudfront_client.list_origin_access_controls().get('OriginAccessControlList', {}).get('Items', [])
    existing_oac = next((o for o in oac_list if o['Name'] == f'OAC-{S3_BUCKET_NAME}'), None)
    if existing_oac:
        oac_id = existing_oac['Id']
        print(f"Deleting Origin Access Control {oac_id}...")
        try:
            oac_config = cloudfront_client.get_origin_access_control_config(Id=oac_id)
            cloudfront_client.delete_origin_access_control(Id=oac_id, IfMatch=oac_config['ETag'])
            print("OAC deleted.")
        except Exception as e:
            print(f"Error deleting OAC: {e}")
    else:
        print("No OAC found.")

def delete_lambda():
    lambda_client = boto3.client('lambda', region_name=REGION)
    try:
        print("Deleting Lambda function 'retrieve_users_data'...")
        lambda_client.delete_function(FunctionName='retrieve_users_data')
        print("Lambda function deleted.")
    except lambda_client.exceptions.ResourceNotFoundException:
        print("Lambda function 'retrieve_users_data' not found.")
    except Exception as e:
        print(f"Error deleting lambda: {e}")

def delete_dynamodb():
    dynamodb = boto3.client('dynamodb', region_name=REGION)
    try:
        print("Deleting DynamoDB table 'users_data'...")
        dynamodb.delete_table(TableName='users_data')
        print("Waiting for table to be deleted...")
        waiter = dynamodb.get_waiter('table_not_exists')
        waiter.wait(TableName='users_data')
        print("DynamoDB table deleted.")
    except dynamodb.exceptions.ResourceNotFoundException:
        print("DynamoDB table 'users_data' not found.")
    except Exception as e:
        print(f"Error deleting dynamodb: {e}")

def delete_apigw():
    apigw_client = boto3.client('apigateway', region_name=REGION)
    apis = apigw_client.get_rest_apis().get('items', [])
    existing_api = next((api for api in apis if api['name'] == 'users_request_api'), None)
    
    if existing_api:
        api_id = existing_api['id']
        try:
            print(f"Deleting API Gateway '{api_id}'...")
            apigw_client.delete_rest_api(restApiId=api_id)
            print("API Gateway deleted.")
        except Exception as e:
            print(f"Error deleting API Gateway: {e}")
    else:
        print("API Gateway 'users_request_api' not found.")

if __name__ == '__main__':
    print("=" * 60)
    print("Starting Teardown (Keeping IAM Intact)")
    print("=" * 60)
    delete_s3()
    delete_apigw()
    delete_lambda()
    delete_dynamodb()
    # Put CloudFront last since it takes a long time
    delete_cloudfront()
    print("=" * 60)
    print("Teardown complete!")
    print("=" * 60)
