import botocore
import boto3
import time
import json

REGION = 'us-west-1'
S3_BUCKET_NAME = 'website-bucket-jaidev'

s3_client = boto3.client('s3', region_name=REGION)

def create_s3_bucket():
    """Create the S3 bucket."""
    print("─" * 60)
    print(f"Creating S3 Bucket '{S3_BUCKET_NAME}'...")
    print("─" * 60)
    try:
        # AWS quirk: only us-east-1 omits LocationConstraint. All other regions (including us-west-1) require it!
        if REGION == 'us-east-1':
            s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
        else:
            s3_client.create_bucket(
                Bucket=S3_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': REGION}
            )
        print(f"S3 bucket '{S3_BUCKET_NAME}' created!")
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        print(f"S3 bucket '{S3_BUCKET_NAME}' already exists (owned by you)")
    except s3_client.exceptions.BucketAlreadyExists:
        print(f"S3 bucket '{S3_BUCKET_NAME}' already exists (name globally taken)")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
            print(f"S3 bucket '{S3_BUCKET_NAME}' already exists (owned by you)")
        else:
            raise

def update_s3_bucket_policy(dist_arn):
    """Add OAC policy to the S3 bucket."""
    print("─" * 60)
    print(f"Applying Bucket Policy for CloudFront OAC...")
    print("─" * 60)
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "cloudfront.amazonaws.com"
                },
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*",
                "Condition": {
                    "StringEquals": {
                        "AWS:SourceArn": dist_arn
                    }
                }
            }
        ]
    }
    s3_client.put_bucket_policy(
        Bucket=S3_BUCKET_NAME,
        Policy=json.dumps(bucket_policy)
    )
    print("Bucket policy successfully applied!")

def create_cloudfront_distribution():
    """Create CloudFront distribution for the S3 bucket."""
    cloudfront_client = boto3.client('cloudfront', region_name=REGION)
    print("─" * 60)
    print(f"Creating/Updating CloudFront Distribution for '{S3_BUCKET_NAME}'...")
    print("─" * 60)
    
    # 1. Create or Find OAC
    oac_list = cloudfront_client.list_origin_access_controls().get('OriginAccessControlList', {}).get('Items', [])
    existing_oac = next((o for o in oac_list if o['Name'] == f'OAC-{S3_BUCKET_NAME}'), None)
    if existing_oac:
        oac_id = existing_oac['Id']
        print(f"OAC already exists: {oac_id}")
    else:
        oac_response = cloudfront_client.create_origin_access_control(
            OriginAccessControlConfig={
                'Name': f'OAC-{S3_BUCKET_NAME}',
                'Description': f'OAC for {S3_BUCKET_NAME}',
                'SigningProtocol': 'sigv4',
                'SigningBehavior': 'always',
                'OriginAccessControlOriginType': 's3'
            }
        )
        oac_id = oac_response['OriginAccessControl']['Id']
        print(f"Origin Access Control created: {oac_id}")

    # 2. Get or create Distribution
    domain_name = f"{S3_BUCKET_NAME}.s3.{REGION}.amazonaws.com"
    caller_reference = f"{S3_BUCKET_NAME}-{int(time.time())}"
    
    dists = cloudfront_client.list_distributions().get('DistributionList', {}).get('Items', [])
    dist = next((d for d in dists if d['Comment'] == S3_BUCKET_NAME), None)
    
    if dist:
        dist_id = dist['Id']
        dist_arn = dist['ARN']
        print(f"Found existing CloudFront Distribution: {dist_id}")
        config = cloudfront_client.get_distribution_config(Id=dist_id)
        dist_config = config['DistributionConfig']
        etag = config['ETag']
        
        needs_update = False
        if dist_config['Origins']['Items'][0].get('OriginAccessControlId') != oac_id:
            dist_config['Origins']['Items'][0]['OriginAccessControlId'] = oac_id
            needs_update = True
        
        if needs_update:
            cloudfront_client.update_distribution(
                DistributionConfig=dist_config,
                Id=dist_id,
                IfMatch=etag
            )
            print("Distribution updated with OAC!")
        else:
            print("Distribution already has OAC configured.")
    else:
        try:
            response = cloudfront_client.create_distribution(
                DistributionConfig={
                    'CallerReference': caller_reference,
                    'Comment': S3_BUCKET_NAME,
                    'Enabled': True,
                    'DefaultRootObject': 'index.html',
                    'Origins': {
                        'Quantity': 1,
                        'Items': [
                            {
                                'Id': f"S3-{S3_BUCKET_NAME}",
                                'DomainName': domain_name,
                                'OriginAccessControlId': oac_id,
                                'S3OriginConfig': {
                                    'OriginAccessIdentity': ''
                                }
                            }
                        ]
                    },
                    'DefaultCacheBehavior': {
                        'TargetOriginId': f"S3-{S3_BUCKET_NAME}",
                        'ViewerProtocolPolicy': 'redirect-to-https',
                        'MinTTL': 0,
                        'ForwardedValues': {
                            'QueryString': False,
                            'Cookies': {'Forward': 'none'}
                        },
                        'TrustedSigners': {
                            'Enabled': False,
                            'Quantity': 0
                        }
                    }
                }
            )
            dist_domain = response['Distribution']['DomainName']
            dist_arn = response['Distribution']['ARN']
            print(f"CloudFront Distribution created! Domain: {dist_domain}")
        except Exception as e:
            print(f"Error creating CloudFront distribution: {e}")
            return
            
    # 3. Apply Bucket Policy
    update_s3_bucket_policy(dist_arn)

def create_lambda_function():
    """Create a Lambda function from scratch."""
    print("─" * 60)
    print("Creating Lambda Function 'retrieve_users_data'...")
    print("─" * 60)
    
    iam_client = boto3.client('iam', region_name=REGION)
    lambda_client = boto3.client('lambda', region_name=REGION)
    
    role_name = 'retrieve_users_data_role'
    
    # 1. Get or Create IAM Execution Role
    sts_client = boto3.client('sts', region_name=REGION)
    account_id = sts_client.get_caller_identity()['Account']
    
    try:
        role_response = iam_client.get_role(RoleName=role_name)
        role_arn = role_response['Role']['Arn']
        print(f"Using existing IAM Role: {role_arn}")
    except iam_client.exceptions.NoSuchEntityException:
        assume_role_policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Effect": "Allow"
                }
            ]
        })
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy
        )
        role_arn = role_response['Role']['Arn']
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        print(f"Created new IAM Role: {role_arn}")
        print("Waiting 10 seconds for IAM role to propagate...")
        time.sleep(10)

    # Attach DynamoDB permissions
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName='DynamoDBAccess',
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:Scan",
                        "dynamodb:Query",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem"
                    ],
                    "Resource": f"arn:aws:dynamodb:{REGION}:{account_id}:table/users_data"
                }
            ]
        })
    )
    print("Attached DynamoDBAccess policy to Lambda Role.")

    # 2. Create dummy deployment package
    import zipfile
    import os
    zip_file_path = '/tmp/retrieve_users_data.zip'
    
    # Use the real index.mjs from the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_mjs_path = os.path.join(base_dir, 'index.mjs')
    
    with zipfile.ZipFile(zip_file_path, 'w') as z:
        z.write(index_mjs_path, 'index.mjs')
        
    with open(zip_file_path, 'rb') as f:
        zipped_code = f.read()
        
    # 3. Create Lambda Function
    try:
        response = lambda_client.create_function(
            FunctionName='retrieve_users_data',
            Runtime='nodejs22.x',
            Role=role_arn,
            Handler='index.handler',
            Code={'ZipFile': zipped_code},
            Architectures=['x86_64'],
            Publish=True
        )
        print(f"Lambda function 'retrieve_users_data' created! ARN: {response['FunctionArn']}")
    except lambda_client.exceptions.ResourceConflictException:
        print("Lambda function 'retrieve_users_data' already exists.")
    except Exception as e:
        print(f"Error creating Lambda function: {e}")

def create_api_gateway():
    """Create API Gateway REST API with Lambda Proxy Integration."""
    print("─" * 60)
    print("Creating API Gateway 'users_request_api' and configuring '/users' GET method...")
    print("─" * 60)
    
    apigw_client = boto3.client('apigateway', region_name=REGION)
    lambda_client = boto3.client('lambda', region_name=REGION)
    sts_client = boto3.client('sts', region_name=REGION)
    account_id = sts_client.get_caller_identity()['Account']
    
    # 1. Check if API already exists
    apis = apigw_client.get_rest_apis().get('items', [])
    existing_api = next((api for api in apis if api['name'] == 'users_request_api'), None)
    
    if existing_api:
        api_id = existing_api['id']
        print(f"API Gateway 'users_request_api' already exists! ID: {api_id}")
    else:
        response = apigw_client.create_rest_api(
            name='users_request_api',
            endpointConfiguration={'types': ['REGIONAL']}
        )
        api_id = response['id']
        print(f"API Gateway 'users_request_api' created! ID: {api_id}")
        
    # 2. Get Root Resource ID
    resources = apigw_client.get_resources(restApiId=api_id)['items']
    root_id = next(r['id'] for r in resources if r['path'] == '/')
    
    # 3. Create '/users' resource
    users_resource_id = None
    for r in resources:
        if r['path'] == '/users':
            users_resource_id = r['id']
            break
            
    if not users_resource_id:
        try:
            resource_response = apigw_client.create_resource(
                restApiId=api_id,
                parentId=root_id,
                pathPart='users'
            )
            users_resource_id = resource_response['id']
        except Exception as e:
            print(f"Error creating '/users' resource: {e}")
            return
            
    # 4. Create GET Method
    try:
        apigw_client.put_method(
            restApiId=api_id,
            resourceId=users_resource_id,
            httpMethod='GET',
            authorizationType='NONE'
        )
    except apigw_client.exceptions.ConflictException:
        pass # Method already exists
        
    # 5. Get Lambda ARN
    lambda_func = lambda_client.get_function(FunctionName='retrieve_users_data')
    lambda_arn = lambda_func['Configuration']['FunctionArn']
    
    # 6. Set up Lambda Proxy Integration
    uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    apigw_client.put_integration(
        restApiId=api_id,
        resourceId=users_resource_id,
        httpMethod='GET',
        type='AWS_PROXY',
        integrationHttpMethod='POST', # Lambda requires POST for integration
        uri=uri
    )
    print("Lambda Proxy Integration configured on GET /users!")
    
    # 7. Add permission to Lambda to allow API Gateway invocation
    source_arn = f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/GET/users"
    try:
        lambda_client.add_permission(
            FunctionName='retrieve_users_data',
            StatementId='apigateway-get-users',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=source_arn
        )
        print("Granted API Gateway permission to invoke Lambda.")
    except lambda_client.exceptions.ResourceConflictException:
        print("Lambda invoke permission already exists.")
        
    # 8. Deploy the API to 'prod' stage
    try:
        deployment_response = apigw_client.create_deployment(
            restApiId=api_id,
            stageName='prod'
        )
        deployment_id = deployment_response['id']
        print(f"API deployed to stage 'prod'! Deployment ID: {deployment_id}")
        invoke_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/prod/users"
        print(f"Invoke URL for testing: {invoke_url}")
    except Exception as e:
        print(f"Error deploying API: {e}")

def create_dynamodb_table():
    """Create DynamoDB table and populate initial data."""
    print("─" * 60)
    print("Creating DynamoDB Table 'users_data'...")
    print("─" * 60)
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    
    try:
        table = dynamodb.create_table(
            TableName='users_data',
            KeySchema=[
                {'AttributeName': 'users_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'users_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print("Waiting for 'users_data' table to be created...")
        table.wait_until_exists()
        print("DynamoDB Table 'users_data' created successfully!")
    except boto3.client('dynamodb', region_name=REGION).exceptions.ResourceInUseException:
        table = dynamodb.Table('users_data')
        print("DynamoDB Table 'users_data' already exists.")
        
    print("Inserting data item into 'users_data'...")
    table.put_item(
        Item={
            "users_id": "1",
            "name": "Test User",
            "email": "test@example.com"
        }
    )
    print("Data item successfully inserted!")

if __name__ == '__main__':
    print("=" * 60)
    print("Infrastructure Setup")
    print("=" * 60)
    print(f"Region:     {REGION}")
    print()
    create_s3_bucket()
    create_cloudfront_distribution()
    create_lambda_function()
    create_api_gateway()
    create_dynamodb_table()
    print("=" * 60)
    print("Infrastructure setup complete!")
    print("=" * 60)
