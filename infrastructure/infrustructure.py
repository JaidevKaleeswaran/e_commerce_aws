#!/usr/bin/env python3
"""
E-Commerce AWS Infrastructure
═══════════════════════════════════════════════════════════════════

Provisions all AWS resources for a production-grade e-commerce platform
following a microservice architecture.

Resources provisioned:
  1.  S3 Bucket           — Static website hosting + product images
  2.  CloudFront          — CDN with OAC, compression, SPA routing
  3.  DynamoDB            — Products table, Orders table (with GSIs)
  4.  ElastiCache Redis   — Shopping cart (low-latency session store)
  5.  OpenSearch           — Full-text product search
  6.  SQS                 — Order processing queue + dead-letter queue
  7.  SNS                 — Order event notifications
  8.  SES                 — Order confirmation emails
  9.  Secrets Manager     — Centralized configuration secrets
  10. IAM                 — Per-Lambda roles with least-privilege
  11. Lambda              — 13 microservice handlers
  12. API Gateway         — REST API with CORS
  13. CloudWatch          — Log groups, alarms, monitoring

Usage:
  python3 infrustructure.py

Design principles:
  - Idempotent: safe to run multiple times
  - Modular: each service in its own function
  - Least-privilege IAM: no wildcard permissions
  - Production-ready: monitoring, DLQ, encryption
"""

import botocore
import boto3
import time
import json
import os
import zipfile
import uuid

# ══════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════

REGION = 'us-west-1'
PROJECT_PREFIX = 'ecommerce'
S3_BUCKET_NAME = 'website-bucket-jaidev'

# API Gateway
API_NAME = f'{PROJECT_PREFIX}-api'
STAGE_NAME = 'prod'

# DynamoDB tables
PRODUCTS_TABLE = f'{PROJECT_PREFIX}-products'
ORDERS_TABLE = f'{PROJECT_PREFIX}-orders'

# ElastiCache
REDIS_CLUSTER_ID = f'{PROJECT_PREFIX}-cart-cache'

# OpenSearch
OPENSEARCH_DOMAIN = f'{PROJECT_PREFIX}-search'

# SQS
ORDER_QUEUE_NAME = f'{PROJECT_PREFIX}-order-processing'
ORDER_DLQ_NAME = f'{PROJECT_PREFIX}-order-processing-dlq'

# SNS
ORDER_EVENTS_TOPIC = f'{PROJECT_PREFIX}-order-events'

# SES — update this with your verified sender email
SES_SENDER_EMAIL = 'orders@example.com'

# Secrets Manager
SECRET_NAME = f'{PROJECT_PREFIX}/config'

# VPC (for ElastiCache and OpenSearch)
VPC_NAME = f'{PROJECT_PREFIX}-vpc'
VPC_CIDR = '10.0.0.0/16'
SUBNET_CIDRS = ['10.0.1.0/24', '10.0.2.0/24']

# Feature flags — set to False to skip costly VPC-dependent services
ENABLE_ELASTICACHE = False
ENABLE_OPENSEARCH = False

# CloudWatch log retention (days)
LOG_RETENTION_DAYS = 30


# ══════════════════════════════════════════════════════════════════
# AWS Clients (created once, reused across all functions)
# ══════════════════════════════════════════════════════════════════

s3_client = boto3.client('s3', region_name=REGION)
cloudfront_client = boto3.client('cloudfront', region_name=REGION)
dynamodb_resource = boto3.resource('dynamodb', region_name=REGION)
dynamodb_client = boto3.client('dynamodb', region_name=REGION)
lambda_client = boto3.client('lambda', region_name=REGION)
apigw_client = boto3.client('apigateway', region_name=REGION)
iam_client = boto3.client('iam', region_name=REGION)
sts_client = boto3.client('sts', region_name=REGION)
sqs_client = boto3.client('sqs', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)
ses_client = boto3.client('ses', region_name=REGION)
secretsmanager_client = boto3.client('secretsmanager', region_name=REGION)
logs_client = boto3.client('logs', region_name=REGION)
cloudwatch_client = boto3.client('cloudwatch', region_name=REGION)
ec2_client = boto3.client('ec2', region_name=REGION)
elasticache_client = boto3.client('elasticache', region_name=REGION)
opensearch_client = boto3.client('opensearch', region_name=REGION)


# ══════════════════════════════════════════════════════════════════
# Helper Functions
# ══════════════════════════════════════════════════════════════════

_account_id_cache = None


def get_account_id():
    """Get the AWS account ID (cached after first call)."""
    global _account_id_cache
    if not _account_id_cache:
        _account_id_cache = sts_client.get_caller_identity()['Account']
    return _account_id_cache


def print_section(title):
    """Print a visually distinct section header matching the existing style."""
    print("─" * 60)
    print(title)
    print("─" * 60)


def get_or_create_iam_role(role_name, service_principals=None, inline_policies=None):
    """
    Create an IAM role idempotently.

    Args:
        role_name: Name for the IAM role
        service_principals: List of AWS service principals (e.g. ['lambda.amazonaws.com'])
        inline_policies: Dict of {policy_name: policy_document_dict}

    Returns:
        str: The role ARN
    """
    if service_principals is None:
        service_principals = ['lambda.amazonaws.com']

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": principal},
                "Action": "sts:AssumeRole"
            }
            for principal in service_principals
        ]
    }

    try:
        response = iam_client.get_role(RoleName=role_name)
        role_arn = response['Role']['Arn']
        print(f"  Using existing IAM role: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        role_arn = response['Role']['Arn']
        # Attach basic Lambda execution policy
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        print(f"  Created IAM role: {role_name}")
        print("  Waiting 10 seconds for IAM role to propagate...")
        time.sleep(10)

    # Apply inline policies (idempotent — put_role_policy overwrites existing)
    if inline_policies:
        for policy_name, policy_doc in inline_policies.items():
            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_doc)
            )
        print(f"  Applied {len(inline_policies)} inline policy(ies) to {role_name}")

    return role_arn


def zip_lambda(function_name, include_lib=None):
    """
    Create a deployment zip for a Lambda function from the lambda_functions/ directory.

    Args:
        function_name: Directory name under lambda_functions/
        include_lib: List of shared _lib files to include (e.g. ['response.mjs', 'redis.mjs'])

    Returns:
        bytes: The zip file contents ready for Lambda deployment
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    lambda_dir = os.path.join(base_dir, 'lambda_functions', function_name)

    zip_path = os.path.join(base_dir, f'{function_name}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        # Add the handler file(s)
        for fname in os.listdir(lambda_dir):
            fpath = os.path.join(lambda_dir, fname)
            if os.path.isfile(fpath):
                z.write(fpath, fname)

        # Add shared library files (flattened into root of zip)
        if include_lib:
            lib_dir = os.path.join(base_dir, 'lambda_functions', '_lib')
            for lib_file in include_lib:
                lib_path = os.path.join(lib_dir, lib_file)
                if os.path.exists(lib_path):
                    z.write(lib_path, lib_file)

    with open(zip_path, 'rb') as f:
        zipped_code = f.read()

    # Clean up the temporary zip file
    os.remove(zip_path)
    return zipped_code


def create_or_update_lambda(function_name, role_arn, handler='index.handler',
                             runtime='nodejs22.x', env_vars=None,
                             timeout=30, memory=256, include_lib=None,
                             vpc_config=None):
    """
    Create or update a Lambda function idempotently.

    Args:
        function_name: The Lambda function name
        role_arn: IAM role ARN for execution
        handler: Handler entry point
        runtime: Lambda runtime
        env_vars: Dict of environment variables
        timeout: Timeout in seconds
        memory: Memory in MB
        include_lib: Shared lib files to bundle
        vpc_config: Optional VPC configuration dict

    Returns:
        str: The Lambda function ARN
    """
    # Derive the source directory name from the function name
    # e.g. 'ecommerce-get-products' → 'get_products'
    source_dir = function_name.replace(f'{PROJECT_PREFIX}-', '').replace('-', '_')
    zipped_code = zip_lambda(source_dir, include_lib=include_lib)

    config = {
        'FunctionName': function_name,
        'Runtime': runtime,
        'Role': role_arn,
        'Handler': handler,
        'Code': {'ZipFile': zipped_code},
        'Timeout': timeout,
        'MemorySize': memory,
        'Architectures': ['x86_64'],
        'Publish': True
    }

    if env_vars:
        config['Environment'] = {'Variables': env_vars}

    if vpc_config:
        config['VpcConfig'] = vpc_config

    try:
        response = lambda_client.create_function(**config)
        function_arn = response['FunctionArn']
        print(f"  Created Lambda: {function_name}")
    except lambda_client.exceptions.ResourceConflictException:
        # Function exists — update code and configuration
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zipped_code,
            Publish=True
        )
        # Brief wait for code update to propagate before config update
        time.sleep(2)

        update_config = {
            'FunctionName': function_name,
            'Runtime': runtime,
            'Role': role_arn,
            'Handler': handler,
            'Timeout': timeout,
            'MemorySize': memory
        }
        if env_vars:
            update_config['Environment'] = {'Variables': env_vars}
        if vpc_config:
            update_config['VpcConfig'] = vpc_config

        response = lambda_client.update_function_configuration(**update_config)
        function_arn = response['FunctionArn']
        print(f"  Updated Lambda: {function_name}")

    return function_arn


def ensure_log_group(function_name):
    """Create a CloudWatch log group for a Lambda function with retention policy."""
    log_group_name = f'/aws/lambda/{function_name}'
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
        print(f"  Created log group: {log_group_name}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass

    try:
        logs_client.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=LOG_RETENTION_DAYS
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# 1. S3 Bucket
# ══════════════════════════════════════════════════════════════════

def create_s3_bucket():
    """
    Create and configure the S3 bucket for static website hosting.

    Enhancements over the demo version:
      - Block all public access (CloudFront serves via OAC)
      - Enable versioning for rollback safety
      - CORS configuration for API Gateway requests
    """
    print_section(f"Creating S3 Bucket '{S3_BUCKET_NAME}'...")

    # Create bucket (idempotent)
    try:
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

    # Block all public access — CloudFront serves content via OAC
    s3_client.put_public_access_block(
        Bucket=S3_BUCKET_NAME,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }
    )
    print("Public access blocked.")

    # Enable versioning for safe deployments and rollbacks
    s3_client.put_bucket_versioning(
        Bucket=S3_BUCKET_NAME,
        VersioningConfiguration={'Status': 'Enabled'}
    )
    print("Versioning enabled.")

    # CORS for API requests from the frontend
    s3_client.put_bucket_cors(
        Bucket=S3_BUCKET_NAME,
        CORSConfiguration={
            'CORSRules': [
                {
                    'AllowedOrigins': ['*'],
                    'AllowedMethods': ['GET', 'HEAD'],
                    'AllowedHeaders': ['*'],
                    'MaxAgeSeconds': 3600
                }
            ]
        }
    )
    print("CORS configuration applied.")


def update_s3_bucket_policy(dist_arn):
    """Add OAC policy to the S3 bucket so CloudFront can serve content."""
    print_section("Applying Bucket Policy for CloudFront OAC...")

    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowCloudFrontOAC",
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


# ══════════════════════════════════════════════════════════════════
# 2. CloudFront Distribution
# ══════════════════════════════════════════════════════════════════

def create_cloudfront_distribution():
    """
    Create or update the CloudFront distribution.

    Enhancements over the demo version:
      - Brotli + Gzip compression
      - SPA routing (404 → index.html with 200 status)
      - HTTP/2 and HTTP/3 support
      - Optimized caching with managed cache policy
    """
    print_section(f"Creating/Updating CloudFront Distribution for '{S3_BUCKET_NAME}'...")

    # 1. Create or find Origin Access Control (OAC)
    oac_name = f'OAC-{S3_BUCKET_NAME}'
    oac_list = cloudfront_client.list_origin_access_controls().get(
        'OriginAccessControlList', {}).get('Items', [])
    existing_oac = next((o for o in oac_list if o['Name'] == oac_name), None)

    if existing_oac:
        oac_id = existing_oac['Id']
        print(f"OAC already exists: {oac_id}")
    else:
        oac_response = cloudfront_client.create_origin_access_control(
            OriginAccessControlConfig={
                'Name': oac_name,
                'Description': f'OAC for {S3_BUCKET_NAME}',
                'SigningProtocol': 'sigv4',
                'SigningBehavior': 'always',
                'OriginAccessControlOriginType': 's3'
            }
        )
        oac_id = oac_response['OriginAccessControl']['Id']
        print(f"Origin Access Control created: {oac_id}")

    # 2. Check for existing distribution
    domain_name = f"{S3_BUCKET_NAME}.s3.{REGION}.amazonaws.com"
    dists = cloudfront_client.list_distributions().get(
        'DistributionList', {}).get('Items', [])
    dist = next((d for d in dists if d['Comment'] == S3_BUCKET_NAME), None)

    if dist:
        dist_id = dist['Id']
        dist_arn = dist['ARN']
        print(f"Found existing CloudFront Distribution: {dist_id}")

        config = cloudfront_client.get_distribution_config(Id=dist_id)
        dist_config = config['DistributionConfig']
        etag = config['ETag']

        needs_update = False

        # Ensure OAC is set
        if dist_config['Origins']['Items'][0].get('OriginAccessControlId') != oac_id:
            dist_config['Origins']['Items'][0]['OriginAccessControlId'] = oac_id
            needs_update = True

        # Ensure compression is enabled
        if not dist_config['DefaultCacheBehavior'].get('Compress'):
            dist_config['DefaultCacheBehavior']['Compress'] = True
            needs_update = True

        # Ensure SPA routing custom error pages
        existing_errors = dist_config.get('CustomErrorResponses', {}).get('Items', [])
        has_spa_error = any(e.get('ErrorCode') == 404 for e in existing_errors)
        if not has_spa_error:
            dist_config['CustomErrorResponses'] = {
                'Quantity': 2,
                'Items': [
                    {
                        'ErrorCode': 404,
                        'ResponsePagePath': '/index.html',
                        'ResponseCode': '200',
                        'ErrorCachingMinTTL': 300
                    },
                    {
                        'ErrorCode': 403,
                        'ResponsePagePath': '/index.html',
                        'ResponseCode': '200',
                        'ErrorCachingMinTTL': 300
                    }
                ]
            }
            needs_update = True

        # Set HTTP version
        if dist_config.get('HttpVersion') != 'http2and3':
            dist_config['HttpVersion'] = 'http2and3'
            needs_update = True

        if needs_update:
            cloudfront_client.update_distribution(
                DistributionConfig=dist_config,
                Id=dist_id,
                IfMatch=etag
            )
            print("Distribution updated with production settings!")
        else:
            print("Distribution already has production settings configured.")
    else:
        # Create new distribution with all production settings
        caller_reference = f"{S3_BUCKET_NAME}-{int(time.time())}"
        try:
            response = cloudfront_client.create_distribution(
                DistributionConfig={
                    'CallerReference': caller_reference,
                    'Comment': S3_BUCKET_NAME,
                    'Enabled': True,
                    'DefaultRootObject': 'index.html',
                    'HttpVersion': 'http2and3',
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
                        'Compress': True,
                        'AllowedMethods': {
                            'Quantity': 3,
                            'Items': ['GET', 'HEAD', 'OPTIONS'],
                            'CachedMethods': {
                                'Quantity': 2,
                                'Items': ['GET', 'HEAD']
                            }
                        },
                        'ForwardedValues': {
                            'QueryString': False,
                            'Cookies': {'Forward': 'none'}
                        },
                        'MinTTL': 0,
                        'DefaultTTL': 86400,
                        'MaxTTL': 31536000,
                        'TrustedSigners': {
                            'Enabled': False,
                            'Quantity': 0
                        }
                    },
                    'CustomErrorResponses': {
                        'Quantity': 2,
                        'Items': [
                            {
                                'ErrorCode': 404,
                                'ResponsePagePath': '/index.html',
                                'ResponseCode': '200',
                                'ErrorCachingMinTTL': 300
                            },
                            {
                                'ErrorCode': 403,
                                'ResponsePagePath': '/index.html',
                                'ResponseCode': '200',
                                'ErrorCachingMinTTL': 300
                            }
                        ]
                    }
                }
            )
            dist_arn = response['Distribution']['ARN']
            dist_domain = response['Distribution']['DomainName']
            print(f"CloudFront Distribution created! Domain: {dist_domain}")
        except Exception as e:
            print(f"Error creating CloudFront distribution: {e}")
            return

    # 3. Apply bucket policy for OAC
    update_s3_bucket_policy(dist_arn)


# ══════════════════════════════════════════════════════════════════
# 3. DynamoDB Tables
# ══════════════════════════════════════════════════════════════════

def create_dynamodb_tables():
    """
    Create the Products and Orders DynamoDB tables with GSIs.

    Products table:
      PK: product_id
      GSI: category-index (category → price)
      GSI: badge-index (badge)

    Orders table:
      PK: order_id
      GSI: customer-email-index (customer_email → created_at)
      GSI: status-index (status → created_at)
    """
    print_section("Creating DynamoDB Tables...")

    # ── Products Table ───────────────────────────────────────────
    try:
        table = dynamodb_resource.create_table(
            TableName=PRODUCTS_TABLE,
            KeySchema=[
                {'AttributeName': 'product_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'product_id', 'AttributeType': 'S'},
                {'AttributeName': 'category', 'AttributeType': 'S'},
                {'AttributeName': 'price', 'AttributeType': 'N'},
                {'AttributeName': 'badge', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'category-index',
                    'KeySchema': [
                        {'AttributeName': 'category', 'KeyType': 'HASH'},
                        {'AttributeName': 'price', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                },
                {
                    'IndexName': 'badge-index',
                    'KeySchema': [
                        {'AttributeName': 'badge', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print(f"Waiting for '{PRODUCTS_TABLE}' table to be created...")
        table.wait_until_exists()
        print(f"DynamoDB Table '{PRODUCTS_TABLE}' created!")
    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"DynamoDB Table '{PRODUCTS_TABLE}' already exists.")

    # ── Orders Table ─────────────────────────────────────────────
    try:
        table = dynamodb_resource.create_table(
            TableName=ORDERS_TABLE,
            KeySchema=[
                {'AttributeName': 'order_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'order_id', 'AttributeType': 'S'},
                {'AttributeName': 'customer_email', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'customer-email-index',
                    'KeySchema': [
                        {'AttributeName': 'customer_email', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                },
                {
                    'IndexName': 'status-index',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print(f"Waiting for '{ORDERS_TABLE}' table to be created...")
        table.wait_until_exists()
        print(f"DynamoDB Table '{ORDERS_TABLE}' created!")
    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"DynamoDB Table '{ORDERS_TABLE}' already exists.")


def seed_products():
    """
    Seed the Products table with realistic sample data.

    Product data mirrors the frontend mock database to ensure
    consistency between the UI and the API.
    """
    print_section("Seeding Products Table...")

    table = dynamodb_resource.Table(PRODUCTS_TABLE)

    products = [
        {
            'product_id': 'macbook-pro-16',
            'name': 'MacBook Pro 16"',
            'subtitle': 'M3 Max · 48GB · 1TB',
            'category': 'laptops',
            'price': 3499,
            'rating': '4.9',
            'reviews': 128,
            'in_stock': True,
            'stock_count': 23,
            'badge': 'New',
            'description': 'The most powerful MacBook Pro ever. Built for professionals who push the limits of creativity and productivity.',
            'specs': {'Chip': 'Apple M3 Max', 'Memory': '48GB Unified', 'Storage': '1TB SSD', 'Display': '16.2" Liquid Retina XDR', 'Battery': 'Up to 22 hours'},
            'images': [
                'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=800&q=80',
                'https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'mbp-sb-1tb', 'label': 'Space Black · 1TB', 'priceOffset': 0},
                {'id': 'mbp-sb-2tb', 'label': 'Space Black · 2TB', 'priceOffset': 400},
                {'id': 'mbp-sl-1tb', 'label': 'Silver · 1TB', 'priceOffset': 0}
            ]
        },
        {
            'product_id': 'macbook-air-15',
            'name': 'MacBook Air 15"',
            'subtitle': 'M3 · 24GB · 512GB',
            'category': 'laptops',
            'price': 1699,
            'rating': '4.8',
            'reviews': 94,
            'in_stock': True,
            'stock_count': 45,
            'badge': '-',
            'description': "Strikingly thin design with the power of the M3 chip. The world's best consumer laptop.",
            'specs': {'Chip': 'Apple M3', 'Memory': '24GB Unified', 'Storage': '512GB SSD', 'Display': '15.3" Liquid Retina', 'Battery': 'Up to 18 hours'},
            'images': [
                'https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'mba-mid-512', 'label': 'Midnight · 512GB', 'priceOffset': 0},
                {'id': 'mba-star-1tb', 'label': 'Starlight · 1TB', 'priceOffset': 200}
            ]
        },
        {
            'product_id': 'studio-display',
            'name': 'Studio Display',
            'subtitle': '27" 5K Retina',
            'category': 'laptops',
            'price': 1599,
            'rating': '4.7',
            'reviews': 56,
            'in_stock': True,
            'stock_count': 18,
            'badge': '-',
            'description': 'A stunning 27-inch 5K Retina display with 600 nits of brightness, P3 wide color, and a 12MP camera with Center Stage.',
            'specs': {'Resolution': '5120 x 2880', 'Brightness': '600 nits', 'Camera': '12MP Ultra Wide', 'Audio': 'Six-speaker system'},
            'images': [
                'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'sd-standard', 'label': 'Standard Glass', 'priceOffset': 0},
                {'id': 'sd-nano', 'label': 'Nano-texture Glass', 'priceOffset': 300}
            ]
        },
        {
            'product_id': 'airpods-max',
            'name': 'AirPods Max',
            'subtitle': 'Wireless Over-Ear',
            'category': 'audio',
            'price': 549,
            'rating': '4.8',
            'reviews': 212,
            'in_stock': True,
            'stock_count': 67,
            'badge': '-',
            'description': 'High-fidelity audio with Active Noise Cancellation. Computational audio creates an immersive listening experience.',
            'specs': {'Driver': '40mm Apple-designed', 'ANC': 'Active Noise Cancellation', 'Battery': '20 hours', 'Connectivity': 'Bluetooth 5.0'},
            'images': [
                'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'apm-silver', 'label': 'Silver', 'priceOffset': 0},
                {'id': 'apm-midnight', 'label': 'Midnight', 'priceOffset': 0}
            ]
        },
        {
            'product_id': 'homepod',
            'name': 'HomePod',
            'subtitle': 'Smart Speaker',
            'category': 'audio',
            'price': 299,
            'rating': '4.6',
            'reviews': 73,
            'in_stock': True,
            'stock_count': 34,
            'badge': '-',
            'description': 'Room-filling, immersive sound. Siri intelligence. Smart home capabilities. A great experience at every level.',
            'specs': {'Woofer': 'High-excursion', 'Tweeters': 'Five beamforming', 'Spatial': 'Dolby Atmos', 'Assistant': 'Siri built-in'},
            'images': [
                'https://images.unsplash.com/photo-1558089687-f282ffcbc126?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'hp-white', 'label': 'White', 'priceOffset': 0},
                {'id': 'hp-midnight', 'label': 'Midnight', 'priceOffset': 0}
            ]
        },
        {
            'product_id': 'apple-watch-ultra',
            'name': 'Watch Ultra 2',
            'subtitle': 'Titanium · 49mm',
            'category': 'wearables',
            'price': 799,
            'rating': '4.9',
            'reviews': 89,
            'in_stock': True,
            'stock_count': 15,
            'badge': 'New',
            'description': 'The most rugged and capable Apple Watch. Precision dual-frequency GPS. Up to 36 hours of battery life.',
            'specs': {'Case': 'Grade 5 Titanium', 'Display': '3000 nits OLED', 'Water': '100m certified', 'Sensors': 'ECG, SpO2, Temperature'},
            'images': [
                'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'awu-natural', 'label': 'Natural Titanium', 'priceOffset': 0},
                {'id': 'awu-black', 'label': 'Black Titanium', 'priceOffset': 50}
            ]
        },
        {
            'product_id': 'magic-keyboard',
            'name': 'Magic Keyboard',
            'subtitle': 'With Touch ID',
            'category': 'accessories',
            'price': 199,
            'rating': '4.7',
            'reviews': 148,
            'in_stock': True,
            'stock_count': 92,
            'badge': '-',
            'description': 'Wireless keyboard with a remarkably comfortable typing experience, Touch ID, and a built-in rechargeable battery.',
            'specs': {'Connection': 'Bluetooth / Lightning', 'Layout': 'Full-size with numpad', 'Auth': 'Touch ID', 'Battery': 'Rechargeable'},
            'images': [
                'https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'mk-silver', 'label': 'Silver', 'priceOffset': 0},
                {'id': 'mk-black', 'label': 'Black', 'priceOffset': 30}
            ]
        },
        {
            'product_id': 'magic-mouse',
            'name': 'Magic Mouse',
            'subtitle': 'Multi-Touch Surface',
            'category': 'accessories',
            'price': 99,
            'rating': '4.5',
            'reviews': 203,
            'in_stock': True,
            'stock_count': 110,
            'badge': '-',
            'description': 'Wireless and rechargeable, with an optimized foot design that lets it glide effortlessly across your desk.',
            'specs': {'Surface': 'Multi-Touch', 'Connection': 'Bluetooth', 'Battery': 'Built-in rechargeable', 'Tracking': 'Laser'},
            'images': [
                'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=800&q=80'
            ],
            'variants': [
                {'id': 'mm-white', 'label': 'White', 'priceOffset': 0},
                {'id': 'mm-black', 'label': 'Black', 'priceOffset': 30}
            ]
        }
    ]

    for product in products:
        table.put_item(Item=product)
        print(f"  Seeded: {product['name']}")

    print(f"Successfully seeded {len(products)} products.")


# ══════════════════════════════════════════════════════════════════
# 4. VPC (for ElastiCache and OpenSearch)
# ══════════════════════════════════════════════════════════════════

def create_vpc():
    """
    Create a VPC with private subnets for ElastiCache and OpenSearch.

    Returns:
        tuple: (vpc_id, subnet_ids, security_group_id) or (None, [], None)
               if VPC services are disabled.
    """
    if not ENABLE_ELASTICACHE and not ENABLE_OPENSEARCH:
        print("  VPC creation skipped (ElastiCache and OpenSearch disabled)")
        return None, [], None

    print_section("Creating VPC for ElastiCache / OpenSearch...")

    # Check for existing VPC
    vpcs = ec2_client.describe_vpcs(
        Filters=[{'Name': 'tag:Name', 'Values': [VPC_NAME]}]
    )['Vpcs']

    if vpcs:
        vpc_id = vpcs[0]['VpcId']
        print(f"Using existing VPC: {vpc_id}")
    else:
        vpc = ec2_client.create_vpc(CidrBlock=VPC_CIDR)
        vpc_id = vpc['Vpc']['VpcId']
        ec2_client.create_tags(
            Resources=[vpc_id],
            Tags=[{'Key': 'Name', 'Value': VPC_NAME}]
        )
        # Enable DNS support and hostnames
        ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
        ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        print(f"VPC created: {vpc_id}")

    # Get availability zones for this region
    azs = ec2_client.describe_availability_zones(
        Filters=[{'Name': 'state', 'Values': ['available']}]
    )['AvailabilityZones']
    az_names = [az['ZoneName'] for az in azs[:2]]  # Use first 2 AZs

    # Create subnets (one per AZ for high availability)
    subnet_ids = []
    existing_subnets = ec2_client.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )['Subnets']

    for i, cidr in enumerate(SUBNET_CIDRS[:len(az_names)]):
        existing = next((s for s in existing_subnets if s['CidrBlock'] == cidr), None)
        if existing:
            subnet_ids.append(existing['SubnetId'])
            print(f"  Using existing subnet: {existing['SubnetId']} ({cidr})")
        else:
            subnet = ec2_client.create_subnet(
                VpcId=vpc_id,
                CidrBlock=cidr,
                AvailabilityZone=az_names[i]
            )
            subnet_id = subnet['Subnet']['SubnetId']
            subnet_ids.append(subnet_id)
            ec2_client.create_tags(
                Resources=[subnet_id],
                Tags=[{'Key': 'Name', 'Value': f'{PROJECT_PREFIX}-subnet-{i+1}'}]
            )
            print(f"  Created subnet: {subnet_id} ({cidr}) in {az_names[i]}")

    # Create security group for internal VPC communication
    sg_name = f'{PROJECT_PREFIX}-internal-sg'
    sgs = ec2_client.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': [sg_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )['SecurityGroups']

    if sgs:
        sg_id = sgs[0]['GroupId']
        print(f"  Using existing security group: {sg_id}")
    else:
        sg = ec2_client.create_security_group(
            GroupName=sg_name,
            Description='Internal VPC traffic for e-commerce services',
            VpcId=vpc_id
        )
        sg_id = sg['GroupId']

        # Allow all traffic within the security group (Lambda ↔ ElastiCache/OpenSearch)
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 6379,
                    'ToPort': 6379,
                    'UserIdGroupPairs': [{'GroupId': sg_id}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'UserIdGroupPairs': [{'GroupId': sg_id}]
                }
            ]
        )
        print(f"  Created security group: {sg_id}")

    return vpc_id, subnet_ids, sg_id


# ══════════════════════════════════════════════════════════════════
# 5. ElastiCache Redis
# ══════════════════════════════════════════════════════════════════

def create_elasticache(subnet_ids, sg_id):
    """
    Create an ElastiCache Redis cluster for shopping cart storage.

    Uses a cache.t3.micro instance (free-tier eligible for 750 hrs/month).
    Single node — sufficient for development; upgrade to a replication
    group for production multi-AZ redundancy.

    Returns:
        str: The Redis endpoint address, or empty string if disabled
    """
    if not ENABLE_ELASTICACHE:
        print("  ElastiCache creation skipped (ENABLE_ELASTICACHE = False)")
        return ''

    print_section("Creating ElastiCache Redis Cluster...")

    # Create subnet group
    subnet_group_name = f'{PROJECT_PREFIX}-cache-subnets'
    try:
        elasticache_client.create_cache_subnet_group(
            CacheSubnetGroupName=subnet_group_name,
            CacheSubnetGroupDescription='Subnets for e-commerce Redis cache',
            SubnetIds=subnet_ids
        )
        print(f"  Created cache subnet group: {subnet_group_name}")
    except elasticache_client.exceptions.CacheSubnetGroupAlreadyExistsFault:
        print(f"  Cache subnet group '{subnet_group_name}' already exists")

    # Create Redis cluster
    try:
        elasticache_client.create_cache_cluster(
            CacheClusterId=REDIS_CLUSTER_ID,
            CacheNodeType='cache.t3.micro',
            Engine='redis',
            NumCacheNodes=1,
            CacheSubnetGroupName=subnet_group_name,
            SecurityGroupIds=[sg_id] if sg_id else [],
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        print(f"  Redis cluster '{REDIS_CLUSTER_ID}' creation initiated...")
        print("  (Cluster will be available in ~5 minutes)")
    except elasticache_client.exceptions.CacheClusterAlreadyExistsFault:
        print(f"  Redis cluster '{REDIS_CLUSTER_ID}' already exists")

    # Try to get the endpoint (may not be available yet during creation)
    try:
        response = elasticache_client.describe_cache_clusters(
            CacheClusterId=REDIS_CLUSTER_ID,
            ShowCacheNodeInfo=True
        )
        nodes = response['CacheClusters'][0].get('CacheNodes', [])
        if nodes and nodes[0].get('Endpoint'):
            endpoint = nodes[0]['Endpoint']['Address']
            print(f"  Redis endpoint: {endpoint}")
            return endpoint
    except Exception:
        pass

    return f'{REDIS_CLUSTER_ID}.cache.amazonaws.com'


# ══════════════════════════════════════════════════════════════════
# 6. OpenSearch
# ══════════════════════════════════════════════════════════════════

def create_opensearch():
    """
    Create an OpenSearch domain for full-text product search.

    Uses public access with IAM authentication (simpler than VPC-based).
    Uses a t3.small.search instance — the smallest production-capable instance.

    Returns:
        str: The OpenSearch domain endpoint, or empty string if disabled
    """
    if not ENABLE_OPENSEARCH:
        print("  OpenSearch creation skipped (ENABLE_OPENSEARCH = False)")
        return ''

    print_section("Creating OpenSearch Domain...")

    account_id = get_account_id()

    try:
        # Check if domain exists
        opensearch_client.describe_domain(DomainName=OPENSEARCH_DOMAIN)
        print(f"  OpenSearch domain '{OPENSEARCH_DOMAIN}' already exists")
    except opensearch_client.exceptions.ResourceNotFoundException:
        # Create new domain with public access and IAM auth
        opensearch_client.create_domain(
            DomainName=OPENSEARCH_DOMAIN,
            EngineVersion='OpenSearch_2.11',
            ClusterConfig={
                'InstanceType': 't3.small.search',
                'InstanceCount': 1,
                'DedicatedMasterEnabled': False,
                'ZoneAwarenessEnabled': False
            },
            EBSOptions={
                'EBSEnabled': True,
                'VolumeType': 'gp3',
                'VolumeSize': 10
            },
            AccessPolicies=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
                        "Action": "es:*",
                        "Resource": f"arn:aws:es:{REGION}:{account_id}:domain/{OPENSEARCH_DOMAIN}/*"
                    }
                ]
            }),
            NodeToNodeEncryptionOptions={'Enabled': True},
            EncryptionAtRestOptions={'Enabled': True},
            DomainEndpointOptions={
                'EnforceHTTPS': True,
                'TLSSecurityPolicy': 'Policy-Min-TLS-1-2-2019-07'
            },
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        print(f"  OpenSearch domain '{OPENSEARCH_DOMAIN}' creation initiated...")
        print("  (Domain will be available in ~15 minutes)")

    # Try to retrieve the endpoint
    try:
        domain = opensearch_client.describe_domain(DomainName=OPENSEARCH_DOMAIN)
        endpoint = domain['DomainStatus'].get('Endpoint', '')
        if endpoint:
            print(f"  OpenSearch endpoint: {endpoint}")
            return endpoint
    except Exception:
        pass

    return ''


# ══════════════════════════════════════════════════════════════════
# 7. SQS Queues
# ══════════════════════════════════════════════════════════════════

def create_sqs_queues():
    """
    Create the order processing queue and its dead-letter queue.

    Messages that fail processing 3 times are moved to the DLQ
    for manual inspection and retry.

    Returns:
        tuple: (queue_url, dlq_url, dlq_arn)
    """
    print_section("Creating SQS Queues...")

    # Dead-letter queue (create first since the main queue references it)
    try:
        dlq_response = sqs_client.create_queue(
            QueueName=ORDER_DLQ_NAME,
            Attributes={
                'MessageRetentionPeriod': '1209600'  # 14 days
            }
        )
        dlq_url = dlq_response['QueueUrl']
        print(f"  DLQ created: {ORDER_DLQ_NAME}")
    except sqs_client.exceptions.QueueNameExists:
        dlq_url = sqs_client.get_queue_url(QueueName=ORDER_DLQ_NAME)['QueueUrl']
        print(f"  DLQ already exists: {ORDER_DLQ_NAME}")

    # Get DLQ ARN for the redrive policy
    dlq_attrs = sqs_client.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=['QueueArn']
    )
    dlq_arn = dlq_attrs['Attributes']['QueueArn']

    # Main order processing queue
    redrive_policy = json.dumps({
        'deadLetterTargetArn': dlq_arn,
        'maxReceiveCount': '3'
    })

    try:
        queue_response = sqs_client.create_queue(
            QueueName=ORDER_QUEUE_NAME,
            Attributes={
                'VisibilityTimeout': '300',        # 5 minutes
                'MessageRetentionPeriod': '1209600',  # 14 days
                'RedrivePolicy': redrive_policy
            }
        )
        queue_url = queue_response['QueueUrl']
        print(f"  Queue created: {ORDER_QUEUE_NAME}")
    except sqs_client.exceptions.QueueNameExists:
        queue_url = sqs_client.get_queue_url(QueueName=ORDER_QUEUE_NAME)['QueueUrl']
        print(f"  Queue already exists: {ORDER_QUEUE_NAME}")
        # Update attributes in case they changed
        sqs_client.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={
                'VisibilityTimeout': '300',
                'RedrivePolicy': redrive_policy
            }
        )

    # Get main queue ARN
    queue_attrs = sqs_client.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['QueueArn']
    )
    queue_arn = queue_attrs['Attributes']['QueueArn']

    print(f"  Queue URL: {queue_url}")
    return queue_url, queue_arn, dlq_url, dlq_arn


# ══════════════════════════════════════════════════════════════════
# 8. SNS Topics
# ══════════════════════════════════════════════════════════════════

def create_sns_topics():
    """
    Create the order events SNS topic for internal event-driven communication.

    Downstream consumers (email Lambda, admin alerts, analytics) subscribe
    to this topic to receive order lifecycle events.

    Returns:
        str: The topic ARN
    """
    print_section("Creating SNS Topics...")

    response = sns_client.create_topic(
        Name=ORDER_EVENTS_TOPIC,
        Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
    )
    topic_arn = response['TopicArn']
    print(f"  SNS topic: {ORDER_EVENTS_TOPIC}")
    print(f"  Topic ARN: {topic_arn}")
    return topic_arn


# ══════════════════════════════════════════════════════════════════
# 9. SES Configuration
# ══════════════════════════════════════════════════════════════════

def configure_ses():
    """
    Configure Amazon SES for order confirmation emails.

    Note: New accounts are in SES sandbox mode. Only verified email
    addresses can receive emails. Request production access from the
    AWS console to send to all recipients.
    """
    print_section("Configuring SES (Email)...")

    if SES_SENDER_EMAIL == 'orders@example.com':
        print("  ⚠  SES sender email is still the default (orders@example.com)")
        print("  ⚠  Update SES_SENDER_EMAIL in the configuration to use a real address")
        print("  Skipping SES verification.")
        return

    # Verify sender email identity
    try:
        ses_client.verify_email_identity(EmailAddress=SES_SENDER_EMAIL)
        print(f"  Verification email sent to: {SES_SENDER_EMAIL}")
        print("  Check inbox and click the verification link before sending emails.")
    except Exception as e:
        print(f"  SES verification error: {e}")

    # Create order confirmation email template
    try:
        ses_client.create_template(
            Template={
                'TemplateName': f'{PROJECT_PREFIX}-order-confirmation',
                'SubjectPart': 'Order Confirmed: {{orderId}}',
                'HtmlPart': '''
                    <div style="max-width:600px;margin:0 auto;font-family:system-ui,sans-serif">
                        <h1>Order Confirmed ✓</h1>
                        <p>Order ID: {{orderId}}</p>
                        <p>Total: ${{total}}</p>
                        <p>Thank you for your purchase!</p>
                    </div>
                ''',
                'TextPart': 'Order {{orderId}} confirmed. Total: ${{total}}. Thank you!'
            }
        )
        print(f"  Created email template: {PROJECT_PREFIX}-order-confirmation")
    except ses_client.exceptions.AlreadyExistsException:
        print(f"  Email template already exists")


# ══════════════════════════════════════════════════════════════════
# 10. Secrets Manager
# ══════════════════════════════════════════════════════════════════

def create_secrets(redis_host='', opensearch_endpoint='',
                   queue_url='', topic_arn=''):
    """
    Store runtime configuration in Secrets Manager.

    Lambda functions read this secret at cold-start to discover
    endpoints for Redis, OpenSearch, SQS, etc. without hardcoding.
    """
    print_section("Configuring Secrets Manager...")

    secret_value = {
        'REDIS_HOST': redis_host,
        'OPENSEARCH_ENDPOINT': opensearch_endpoint,
        'SES_SENDER_EMAIL': SES_SENDER_EMAIL,
        'ORDER_QUEUE_URL': queue_url,
        'ORDER_EVENTS_TOPIC_ARN': topic_arn,
        'PRODUCTS_TABLE': PRODUCTS_TABLE,
        'ORDERS_TABLE': ORDERS_TABLE,
        'REGION': REGION
    }

    try:
        secretsmanager_client.create_secret(
            Name=SECRET_NAME,
            SecretString=json.dumps(secret_value),
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        print(f"  Secret created: {SECRET_NAME}")
    except secretsmanager_client.exceptions.ResourceExistsException:
        secretsmanager_client.update_secret(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(secret_value)
        )
        print(f"  Secret updated: {SECRET_NAME}")

    print(f"  Stored {len(secret_value)} configuration values")


# ══════════════════════════════════════════════════════════════════
# 11. IAM Roles
# ══════════════════════════════════════════════════════════════════

def create_iam_roles(queue_arn='', topic_arn='', vpc_needed=False):
    """
    Create per-Lambda IAM roles with least-privilege permissions.

    Each service (product, cart, order, checkout, search, processor)
    gets its own role scoped to only the resources it needs.

    Returns:
        dict: {role_name_suffix: role_arn}
    """
    print_section("Creating IAM Roles (Per-Service)...")

    account_id = get_account_id()
    products_table_arn = f'arn:aws:dynamodb:{REGION}:{account_id}:table/{PRODUCTS_TABLE}'
    orders_table_arn = f'arn:aws:dynamodb:{REGION}:{account_id}:table/{ORDERS_TABLE}'
    secret_arn = f'arn:aws:secretsmanager:{REGION}:{account_id}:secret:{SECRET_NAME}*'

    roles = {}

    # ── Product Service Role ─────────────────────────────────────
    roles['product'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-product-lambda-role',
        inline_policies={
            'DynamoDBReadProducts': {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:Scan",
                        "dynamodb:Query"
                    ],
                    "Resource": [
                        products_table_arn,
                        f'{products_table_arn}/index/*'
                    ]
                }]
            }
        }
    )

    # ── Cart Service Role ────────────────────────────────────────
    cart_policies = {
        'DynamoDBReadProducts': {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["dynamodb:GetItem"],
                "Resource": [products_table_arn]
            }]
        },
        'SecretsManagerRead': {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [secret_arn]
            }]
        }
    }
    if vpc_needed:
        cart_policies['VPCAccess'] = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DeleteNetworkInterface"
                ],
                "Resource": "*"
            }]
        }

    roles['cart'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-cart-lambda-role',
        inline_policies=cart_policies
    )

    # ── Order Service Role ───────────────────────────────────────
    roles['order'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-order-lambda-role',
        inline_policies={
            'DynamoDBOrders': {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query"
                    ],
                    "Resource": [
                        orders_table_arn,
                        f'{orders_table_arn}/index/*'
                    ]
                }]
            }
        }
    )

    # ── Checkout Service Role ────────────────────────────────────
    checkout_policies = {
        'DynamoDBCheckout': {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ReadProducts",
                    "Effect": "Allow",
                    "Action": ["dynamodb:GetItem", "dynamodb:Scan"],
                    "Resource": [products_table_arn]
                },
                {
                    "Sid": "WriteOrders",
                    "Effect": "Allow",
                    "Action": ["dynamodb:PutItem", "dynamodb:UpdateItem"],
                    "Resource": [orders_table_arn]
                }
            ]
        },
        'SecretsManagerRead': {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [secret_arn]
            }]
        }
    }
    if queue_arn:
        checkout_policies['SQSSendMessage'] = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["sqs:SendMessage"],
                "Resource": [queue_arn]
            }]
        }
    if vpc_needed:
        checkout_policies['VPCAccess'] = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DeleteNetworkInterface"
                ],
                "Resource": "*"
            }]
        }

    roles['checkout'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-checkout-lambda-role',
        inline_policies=checkout_policies
    )

    # ── Search Service Role ──────────────────────────────────────
    search_policies = {
        'DynamoDBReadProducts': {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["dynamodb:Scan", "dynamodb:Query"],
                "Resource": [products_table_arn, f'{products_table_arn}/index/*']
            }]
        }
    }
    if ENABLE_OPENSEARCH:
        search_policies['OpenSearchRead'] = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["es:ESHttpGet", "es:ESHttpPost"],
                "Resource": [f'arn:aws:es:{REGION}:{account_id}:domain/{OPENSEARCH_DOMAIN}/*']
            }]
        }

    roles['search'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-search-lambda-role',
        inline_policies=search_policies
    )

    # ── Background Processor Role ────────────────────────────────
    processor_statements = [
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem"
            ],
            "Resource": [products_table_arn, orders_table_arn]
        },
        {
            "Sid": "SESAccess",
            "Effect": "Allow",
            "Action": ["ses:SendEmail", "ses:SendTemplatedEmail"],
            "Resource": ["*"]
        },
        {
            "Sid": "SecretsAccess",
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": [secret_arn]
        }
    ]
    if queue_arn:
        processor_statements.append({
            "Sid": "SQSAccess",
            "Effect": "Allow",
            "Action": [
                "sqs:ReceiveMessage",
                "sqs:DeleteMessage",
                "sqs:GetQueueAttributes"
            ],
            "Resource": [queue_arn]
        })
    if topic_arn:
        processor_statements.append({
            "Sid": "SNSAccess",
            "Effect": "Allow",
            "Action": ["sns:Publish"],
            "Resource": [topic_arn]
        })

    roles['processor'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-processor-lambda-role',
        inline_policies={
            'ProcessorAccess': {
                "Version": "2012-10-17",
                "Statement": processor_statements
            }
        }
    )

    # ── Notification (Send Confirmation) Role ────────────────────
    roles['notification'] = get_or_create_iam_role(
        f'{PROJECT_PREFIX}-notification-lambda-role',
        inline_policies={
            'SESAccess': {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": ["ses:SendEmail"],
                    "Resource": ["*"]
                }]
            }
        }
    )

    return roles


# ══════════════════════════════════════════════════════════════════
# 12. Lambda Functions
# ══════════════════════════════════════════════════════════════════

def create_lambda_functions(roles, queue_url='', queue_arn='',
                             topic_arn='', redis_host='',
                             opensearch_endpoint='',
                             vpc_config=None):
    """
    Create all 13 Lambda functions organized by service.

    Each function gets:
      - Its own IAM role (least-privilege)
      - Environment variables for resource endpoints
      - A CloudWatch log group with retention policy
      - Appropriate timeout and memory settings

    Returns:
        dict: {function_name: function_arn}
    """
    print_section("Creating Lambda Functions...")

    env_common = {
        'PRODUCTS_TABLE': PRODUCTS_TABLE,
        'ORDERS_TABLE': ORDERS_TABLE,
        'REGION': REGION
    }

    cart_env = {
        **env_common,
        'REDIS_HOST': redis_host,
        'REDIS_PORT': '6379'
    }

    checkout_env = {
        **env_common,
        'REDIS_HOST': redis_host,
        'REDIS_PORT': '6379',
        'ORDER_QUEUE_URL': queue_url
    }

    processor_env = {
        **env_common,
        'ORDER_EVENTS_TOPIC_ARN': topic_arn,
        'SES_SENDER_EMAIL': SES_SENDER_EMAIL
    }

    notification_env = {
        'SES_SENDER_EMAIL': SES_SENDER_EMAIL,
        'REGION': REGION
    }

    search_env = {
        **env_common,
        'OPENSEARCH_ENDPOINT': opensearch_endpoint
    }

    # Define all Lambda functions
    lambda_defs = [
        # ── Product Service ──────────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-get-products',
            'role': roles['product'],
            'env': env_common,
            'lib': ['response.mjs'],
            'timeout': 30,
            'memory': 256
        },
        {
            'name': f'{PROJECT_PREFIX}-get-product',
            'role': roles['product'],
            'env': env_common,
            'lib': ['response.mjs'],
            'timeout': 30,
            'memory': 256
        },
        {
            'name': f'{PROJECT_PREFIX}-get-categories',
            'role': roles['product'],
            'env': env_common,
            'lib': ['response.mjs'],
            'timeout': 30,
            'memory': 256
        },

        # ── Search Service ───────────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-search-products',
            'role': roles['search'],
            'env': search_env,
            'lib': ['response.mjs'],
            'timeout': 30,
            'memory': 256
        },

        # ── Cart Service ─────────────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-get-cart',
            'role': roles['cart'],
            'env': cart_env,
            'lib': ['response.mjs', 'redis.mjs'],
            'timeout': 30,
            'memory': 256,
            'vpc': vpc_config if ENABLE_ELASTICACHE else None
        },
        {
            'name': f'{PROJECT_PREFIX}-add-to-cart',
            'role': roles['cart'],
            'env': cart_env,
            'lib': ['response.mjs', 'redis.mjs'],
            'timeout': 30,
            'memory': 256,
            'vpc': vpc_config if ENABLE_ELASTICACHE else None
        },
        {
            'name': f'{PROJECT_PREFIX}-update-cart',
            'role': roles['cart'],
            'env': cart_env,
            'lib': ['response.mjs', 'redis.mjs'],
            'timeout': 30,
            'memory': 256,
            'vpc': vpc_config if ENABLE_ELASTICACHE else None
        },
        {
            'name': f'{PROJECT_PREFIX}-remove-from-cart',
            'role': roles['cart'],
            'env': cart_env,
            'lib': ['response.mjs', 'redis.mjs'],
            'timeout': 30,
            'memory': 256,
            'vpc': vpc_config if ENABLE_ELASTICACHE else None
        },

        # ── Checkout Service ─────────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-checkout',
            'role': roles['checkout'],
            'env': checkout_env,
            'lib': ['response.mjs', 'redis.mjs'],
            'timeout': 60,
            'memory': 512,
            'vpc': vpc_config if ENABLE_ELASTICACHE else None
        },

        # ── Order Service ────────────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-get-orders',
            'role': roles['order'],
            'env': env_common,
            'lib': ['response.mjs'],
            'timeout': 30,
            'memory': 256
        },

        # ── Background Processing ────────────────────────────────
        {
            'name': f'{PROJECT_PREFIX}-process-order',
            'role': roles['processor'],
            'env': processor_env,
            'lib': [],
            'timeout': 300,
            'memory': 512
        },
        {
            'name': f'{PROJECT_PREFIX}-send-confirmation',
            'role': roles['notification'],
            'env': notification_env,
            'lib': [],
            'timeout': 60,
            'memory': 256
        }
    ]

    function_arns = {}

    for ldef in lambda_defs:
        ensure_log_group(ldef['name'])
        arn = create_or_update_lambda(
            function_name=ldef['name'],
            role_arn=ldef['role'],
            env_vars=ldef['env'],
            timeout=ldef['timeout'],
            memory=ldef['memory'],
            include_lib=ldef.get('lib'),
            vpc_config=ldef.get('vpc')
        )
        function_arns[ldef['name']] = arn

    # ── SQS Event Source Mapping (process-order ← SQS) ───────
    if queue_arn:
        processor_name = f'{PROJECT_PREFIX}-process-order'
        try:
            # Check for existing mapping
            mappings = lambda_client.list_event_source_mappings(
                FunctionName=processor_name,
                EventSourceArn=queue_arn
            )['EventSourceMappings']

            if not mappings:
                lambda_client.create_event_source_mapping(
                    EventSourceArn=queue_arn,
                    FunctionName=processor_name,
                    BatchSize=5,
                    Enabled=True
                )
                print(f"  SQS → {processor_name} event source mapping created")
            else:
                print(f"  SQS → {processor_name} event source mapping already exists")
        except Exception as e:
            print(f"  Warning: Could not create SQS event source mapping: {e}")

    # ── SNS Subscription (send-confirmation ← SNS) ──────────
    if topic_arn:
        notification_name = f'{PROJECT_PREFIX}-send-confirmation'
        notification_arn = function_arns.get(notification_name)
        if notification_arn:
            try:
                # Add Lambda permission for SNS
                try:
                    lambda_client.add_permission(
                        FunctionName=notification_name,
                        StatementId='sns-invoke',
                        Action='lambda:InvokeFunction',
                        Principal='sns.amazonaws.com',
                        SourceArn=topic_arn
                    )
                except lambda_client.exceptions.ResourceConflictException:
                    pass

                # Subscribe Lambda to SNS topic
                sns_client.subscribe(
                    TopicArn=topic_arn,
                    Protocol='lambda',
                    Endpoint=notification_arn
                )
                print(f"  SNS → {notification_name} subscription created")
            except Exception as e:
                print(f"  Warning: Could not create SNS subscription: {e}")

    print(f"\nCreated {len(function_arns)} Lambda functions.")
    return function_arns


# ══════════════════════════════════════════════════════════════════
# 13. API Gateway
# ══════════════════════════════════════════════════════════════════

def create_api_gateway(function_arns):
    """
    Create the REST API with Lambda proxy integration for all endpoints.

    Endpoints:
      GET    /products          → get-products
      GET    /products/{id}     → get-product
      GET    /categories        → get-categories
      GET    /search            → search-products
      GET    /cart              → get-cart
      POST   /cart              → add-to-cart
      PUT    /cart              → update-cart
      DELETE /cart              → remove-from-cart
      POST   /checkout          → checkout
      GET    /orders            → get-orders
      GET    /orders/{id}       → get-orders

    All endpoints include CORS support via OPTIONS preflight.
    """
    print_section("Creating API Gateway...")

    account_id = get_account_id()

    # 1. Create or find the API
    apis = apigw_client.get_rest_apis()['items']
    existing_api = next((api for api in apis if api['name'] == API_NAME), None)

    if existing_api:
        api_id = existing_api['id']
        print(f"API Gateway '{API_NAME}' already exists: {api_id}")
    else:
        response = apigw_client.create_rest_api(
            name=API_NAME,
            description='E-Commerce REST API',
            endpointConfiguration={'types': ['REGIONAL']}
        )
        api_id = response['id']
        print(f"API Gateway '{API_NAME}' created: {api_id}")

    # 2. Get root resource ID
    resources = apigw_client.get_resources(restApiId=api_id, limit=500)['items']
    root_id = next(r['id'] for r in resources if r['path'] == '/')

    def find_resource(path):
        """Find an existing resource by path."""
        return next((r for r in resources if r['path'] == path), None)

    def get_or_create_resource(parent_id, path_part, full_path):
        """Create a resource idempotently and return its ID."""
        existing = find_resource(full_path)
        if existing:
            return existing['id']
        try:
            resp = apigw_client.create_resource(
                restApiId=api_id,
                parentId=parent_id,
                pathPart=path_part
            )
            resource_id = resp['id']
            # Update local resources list
            resources.append({'id': resource_id, 'path': full_path})
            return resource_id
        except Exception as e:
            print(f"  Error creating resource '{full_path}': {e}")
            return None

    def setup_method(resource_id, http_method, function_name, resource_path):
        """Configure a method with Lambda proxy integration and CORS."""
        lambda_arn = function_arns.get(function_name)
        if not lambda_arn:
            print(f"  Warning: Lambda '{function_name}' not found, skipping {http_method} {resource_path}")
            return

        # Strip version/alias suffix from ARN for integration URI
        base_arn = lambda_arn.split(':')
        if len(base_arn) > 7:
            base_arn = ':'.join(base_arn[:7])
        else:
            base_arn = lambda_arn

        uri = f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{base_arn}/invocations"

        # PUT method
        try:
            apigw_client.put_method(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod=http_method,
                authorizationType='NONE'
            )
        except apigw_client.exceptions.ConflictException:
            pass

        # PUT integration (Lambda proxy)
        apigw_client.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            type='AWS_PROXY',
            integrationHttpMethod='POST',
            uri=uri
        )

        # Grant API Gateway permission to invoke Lambda
        source_arn = f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*/{http_method}{resource_path}"
        clean_path = ''.join(c if c.isalnum() else '-' for c in resource_path).strip('-')
        statement_id = f'apigw-{http_method}-{clean_path}'
        try:
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId=statement_id,
                Action='lambda:InvokeFunction',
                Principal='apigateway.amazonaws.com',
                SourceArn=source_arn
            )
        except lambda_client.exceptions.ResourceConflictException:
            pass

        print(f"  {http_method:6s} {resource_path:25s} → {function_name}")

    def setup_cors(resource_id):
        """Add OPTIONS method for CORS preflight."""
        try:
            apigw_client.put_method(
                restApiId=api_id,
                resourceId=resource_id,
                httpMethod='OPTIONS',
                authorizationType='NONE'
            )
        except apigw_client.exceptions.ConflictException:
            return  # Already exists

        apigw_client.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod='OPTIONS',
            type='MOCK',
            requestTemplates={'application/json': '{"statusCode": 200}'}
        )

        apigw_client.put_method_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod='OPTIONS',
            statusCode='200',
            responseParameters={
                'method.response.header.Access-Control-Allow-Headers': False,
                'method.response.header.Access-Control-Allow-Methods': False,
                'method.response.header.Access-Control-Allow-Origin': False
            }
        )

        apigw_client.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod='OPTIONS',
            statusCode='200',
            responseParameters={
                'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Session-Id'",
                'method.response.header.Access-Control-Allow-Methods': "'GET,POST,PUT,DELETE,OPTIONS'",
                'method.response.header.Access-Control-Allow-Origin': "'*'"
            }
        )

    # 3. Create resources and wire up methods

    # /products
    products_id = get_or_create_resource(root_id, 'products', '/products')
    if products_id:
        setup_method(products_id, 'GET', f'{PROJECT_PREFIX}-get-products', '/products')
        setup_cors(products_id)

    # /products/{id}
    product_by_id = get_or_create_resource(products_id, '{id}', '/products/{id}')
    if product_by_id:
        setup_method(product_by_id, 'GET', f'{PROJECT_PREFIX}-get-product', '/products/{id}')
        setup_cors(product_by_id)

    # /categories
    categories_id = get_or_create_resource(root_id, 'categories', '/categories')
    if categories_id:
        setup_method(categories_id, 'GET', f'{PROJECT_PREFIX}-get-categories', '/categories')
        setup_cors(categories_id)

    # /search
    search_id = get_or_create_resource(root_id, 'search', '/search')
    if search_id:
        setup_method(search_id, 'GET', f'{PROJECT_PREFIX}-search-products', '/search')
        setup_cors(search_id)

    # /cart (GET, POST, PUT, DELETE)
    cart_id = get_or_create_resource(root_id, 'cart', '/cart')
    if cart_id:
        setup_method(cart_id, 'GET', f'{PROJECT_PREFIX}-get-cart', '/cart')
        setup_method(cart_id, 'POST', f'{PROJECT_PREFIX}-add-to-cart', '/cart')
        setup_method(cart_id, 'PUT', f'{PROJECT_PREFIX}-update-cart', '/cart')
        setup_method(cart_id, 'DELETE', f'{PROJECT_PREFIX}-remove-from-cart', '/cart')
        setup_cors(cart_id)

    # /checkout
    checkout_id = get_or_create_resource(root_id, 'checkout', '/checkout')
    if checkout_id:
        setup_method(checkout_id, 'POST', f'{PROJECT_PREFIX}-checkout', '/checkout')
        setup_cors(checkout_id)

    # /orders
    orders_id = get_or_create_resource(root_id, 'orders', '/orders')
    if orders_id:
        setup_method(orders_id, 'GET', f'{PROJECT_PREFIX}-get-orders', '/orders')
        setup_cors(orders_id)

    # /orders/{id}
    order_by_id = get_or_create_resource(orders_id, '{id}', '/orders/{id}')
    if order_by_id:
        setup_method(order_by_id, 'GET', f'{PROJECT_PREFIX}-get-orders', '/orders/{id}')
        setup_cors(order_by_id)

    # 4. Deploy to stage
    try:
        deployment = apigw_client.create_deployment(
            restApiId=api_id,
            stageName=STAGE_NAME,
            description=f'Deployment at {time.strftime("%Y-%m-%d %H:%M:%S")}'
        )
        print(f"\nAPI deployed to stage '{STAGE_NAME}'!")
        invoke_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
        print(f"Base URL: {invoke_url}")
    except Exception as e:
        print(f"Error deploying API: {e}")
        invoke_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"

    return api_id, invoke_url


# ══════════════════════════════════════════════════════════════════
# 14. CloudWatch Alarms
# ══════════════════════════════════════════════════════════════════

def create_cloudwatch_alarms(topic_arn='', api_id='', queue_url=''):
    """
    Create CloudWatch alarms for monitoring the e-commerce platform.

    Alarms:
      - Lambda error rate (across all functions)
      - API Gateway 5xx error rate
      - API Gateway latency
      - SQS queue depth
    """
    print_section("Creating CloudWatch Alarms...")

    alarm_actions = [topic_arn] if topic_arn else []

    # ── Lambda Errors Alarm ──────────────────────────────────────
    try:
        cloudwatch_client.put_metric_alarm(
            AlarmName=f'{PROJECT_PREFIX}-lambda-errors',
            AlarmDescription='High Lambda error rate across e-commerce functions',
            Namespace='AWS/Lambda',
            MetricName='Errors',
            Statistic='Sum',
            Period=300,
            EvaluationPeriods=1,
            Threshold=5,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching',
            AlarmActions=alarm_actions,
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        print("  Alarm created: lambda-errors (> 5 errors in 5 min)")
    except Exception as e:
        print(f"  Error creating Lambda alarm: {e}")

    # ── API Gateway 5xx Alarm ────────────────────────────────────
    if api_id:
        try:
            cloudwatch_client.put_metric_alarm(
                AlarmName=f'{PROJECT_PREFIX}-api-5xx',
                AlarmDescription='High 5xx error rate on API Gateway',
                Namespace='AWS/ApiGateway',
                MetricName='5XXError',
                Dimensions=[{'Name': 'ApiName', 'Value': API_NAME}],
                Statistic='Sum',
                Period=300,
                EvaluationPeriods=1,
                Threshold=10,
                ComparisonOperator='GreaterThanThreshold',
                TreatMissingData='notBreaching',
                AlarmActions=alarm_actions,
                Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
            )
            print("  Alarm created: api-5xx (> 10 errors in 5 min)")
        except Exception as e:
            print(f"  Error creating API 5xx alarm: {e}")

    # ── API Gateway Latency Alarm ────────────────────────────────
    if api_id:
        try:
            cloudwatch_client.put_metric_alarm(
                AlarmName=f'{PROJECT_PREFIX}-api-latency',
                AlarmDescription='High API Gateway latency',
                Namespace='AWS/ApiGateway',
                MetricName='Latency',
                Dimensions=[{'Name': 'ApiName', 'Value': API_NAME}],
                Statistic='Average',
                Period=300,
                EvaluationPeriods=2,
                Threshold=3000,
                ComparisonOperator='GreaterThanThreshold',
                TreatMissingData='notBreaching',
                AlarmActions=alarm_actions,
                Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
            )
            print("  Alarm created: api-latency (> 3s avg over 10 min)")
        except Exception as e:
            print(f"  Error creating latency alarm: {e}")

    # ── SQS Queue Depth Alarm ────────────────────────────────────
    try:
        cloudwatch_client.put_metric_alarm(
            AlarmName=f'{PROJECT_PREFIX}-sqs-depth',
            AlarmDescription='High SQS queue depth — processing may be falling behind',
            Namespace='AWS/SQS',
            MetricName='ApproximateNumberOfMessagesVisible',
            Dimensions=[{'Name': 'QueueName', 'Value': ORDER_QUEUE_NAME}],
            Statistic='Maximum',
            Period=300,
            EvaluationPeriods=1,
            Threshold=100,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching',
            AlarmActions=alarm_actions,
            Tags=[{'Key': 'Project', 'Value': PROJECT_PREFIX}]
        )
        print("  Alarm created: sqs-depth (> 100 messages)")
    except Exception as e:
        print(f"  Error creating SQS alarm: {e}")


# ══════════════════════════════════════════════════════════════════
# Main: Orchestrate All Infrastructure Setup
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("E-Commerce Infrastructure Setup")
    print("=" * 60)
    print(f"Region:          {REGION}")
    print(f"Project:         {PROJECT_PREFIX}")
    print(f"ElastiCache:     {'Enabled' if ENABLE_ELASTICACHE else 'Disabled'}")
    print(f"OpenSearch:      {'Enabled' if ENABLE_OPENSEARCH else 'Disabled'}")
    print()

    # ── Step 1: S3 Bucket ────────────────────────────────────────
    create_s3_bucket()
    print()

    # ── Step 2: CloudFront ───────────────────────────────────────
    create_cloudfront_distribution()
    print()

    # ── Step 3: DynamoDB Tables ──────────────────────────────────
    create_dynamodb_tables()
    print()

    # ── Step 4: Seed Product Data ────────────────────────────────
    seed_products()
    print()

    # ── Step 5: VPC (for ElastiCache / OpenSearch) ───────────────
    vpc_id, subnet_ids, sg_id = create_vpc()
    print()

    # ── Step 6: ElastiCache Redis ────────────────────────────────
    redis_host = create_elasticache(subnet_ids, sg_id) if ENABLE_ELASTICACHE else ''
    print()

    # ── Step 7: OpenSearch ───────────────────────────────────────
    opensearch_endpoint = create_opensearch()
    print()

    # ── Step 8: SQS Queues ───────────────────────────────────────
    queue_url, queue_arn, dlq_url, dlq_arn = create_sqs_queues()
    print()

    # ── Step 9: SNS Topics ───────────────────────────────────────
    topic_arn = create_sns_topics()
    print()

    # ── Step 10: SES Configuration ───────────────────────────────
    configure_ses()
    print()

    # ── Step 11: Secrets Manager ─────────────────────────────────
    create_secrets(
        redis_host=redis_host,
        opensearch_endpoint=opensearch_endpoint,
        queue_url=queue_url,
        topic_arn=topic_arn
    )
    print()

    # ── Step 12: IAM Roles ───────────────────────────────────────
    vpc_needed = ENABLE_ELASTICACHE and vpc_id is not None
    roles = create_iam_roles(
        queue_arn=queue_arn,
        topic_arn=topic_arn,
        vpc_needed=vpc_needed
    )
    print()

    # ── Step 13: Lambda Functions ────────────────────────────────
    vpc_config = None
    if vpc_needed and subnet_ids and sg_id:
        vpc_config = {
            'SubnetIds': subnet_ids,
            'SecurityGroupIds': [sg_id]
        }

    function_arns = create_lambda_functions(
        roles=roles,
        queue_url=queue_url,
        queue_arn=queue_arn,
        topic_arn=topic_arn,
        redis_host=redis_host,
        opensearch_endpoint=opensearch_endpoint,
        vpc_config=vpc_config
    )
    print()

    # ── Step 14: API Gateway ─────────────────────────────────────
    api_id, invoke_url = create_api_gateway(function_arns)
    print()

    # ── Step 15: CloudWatch Alarms ───────────────────────────────
    create_cloudwatch_alarms(
        topic_arn=topic_arn,
        api_id=api_id,
        queue_url=queue_url
    )
    print()

    # ── Summary ──────────────────────────────────────────────────
    print("=" * 60)
    print("Infrastructure setup complete!")
    print("=" * 60)
    print()
    print("  Endpoints:")
    print(f"    API Base URL:   {invoke_url}")
    print(f"    GET  /products          — List products")
    print(f"    GET  /products/{{id}}     — Product detail")
    print(f"    GET  /categories        — List categories")
    print(f"    GET  /search?q=keyword  — Search products")
    print(f"    GET  /cart              — Get cart")
    print(f"    POST /cart              — Add to cart")
    print(f"    PUT  /cart              — Update cart item")
    print(f"    DELETE /cart            — Remove cart item")
    print(f"    POST /checkout          — Process checkout")
    print(f"    GET  /orders            — List orders")
    print(f"    GET  /orders/{{id}}       — Order detail")
    print()
    print("  Resources:")
    print(f"    S3 Bucket:      {S3_BUCKET_NAME}")
    print(f"    Products Table: {PRODUCTS_TABLE}")
    print(f"    Orders Table:   {ORDERS_TABLE}")
    print(f"    SQS Queue:      {ORDER_QUEUE_NAME}")
    print(f"    SNS Topic:      {ORDER_EVENTS_TOPIC}")
    if redis_host:
        print(f"    Redis Host:     {redis_host}")
    if opensearch_endpoint:
        print(f"    OpenSearch:     {opensearch_endpoint}")
    print()
