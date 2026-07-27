# infrastructure.py
# Creates ALL foundational AWS resources for the QuickRide pipeline.
# Resources created:
#   1. Kinesis Data Stream (ride-events) — central event bus
#   2. DynamoDB Tables (driver-locations, zone-demand) — real-time state
#   3. S3 Bucket (quickride-data-lake) — archival storage for Firehose
#   4. SNS Topic (operations-alerts) — desert zone alerts
#   5. IAM Role (FirehoseS3Role) — permissions for Firehose to read Kinesis and write S3
#
# Run: python infrastructure.py

import botocore
import boto3
import json
import time

REGION = 'us-west-1'
S3_BUCKET_NAME = 'network-three-teir-jaidev-1'
SNS_TOPIC_NAME = 'operations-alerts'
KINESIS_STREAM_NAME = 'ride-events'
FIREHOSE_ROLE_NAME = 'FirehoseS3Role'
LAMBDA_ROLE_NAME = 'QuickRideLambdaRole'

kinesis_client = boto3.client('kinesis', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
s3_client = boto3.client('s3', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)
iam_client = boto3.client('iam', region_name=REGION)
sts_client = boto3.client('sts', region_name=REGION)

# Get AWS Account ID dynamically
ACCOUNT_ID = sts_client.get_caller_identity()['Account']



# ──────────────────────────────────────────────────────────────────
# 2. DynamoDB Tables
# ──────────────────────────────────────────────────────────────────
# def create_dynamodb_tables():
#     """Create DynamoDB tables for real-time data storage"""

#     # Table 1: Driver current location (updated every 10 seconds)
#     try:
#         table = dynamodb.create_table(
#             TableName='driver-locations',
#             KeySchema=[
#                 {'AttributeName': 'driver_id', 'KeyType': 'HASH'}
#             ],
#             AttributeDefinitions=[
#                 {'AttributeName': 'driver_id', 'AttributeType': 'S'}
#             ],
#             BillingMode='PAY_PER_REQUEST'  # On-demand pricing
#         )

#         # Wait for table to become ACTIVE before enabling TTL
#         print("Waiting for driver-locations table to become ACTIVE...")
#         table.wait_until_exists()

#         # Enable TTL separately after table is ACTIVE
#         dynamodb.meta.client.update_time_to_live(
#             TableName='driver-locations',
#             TimeToLiveSpecification={
#                 'Enabled': True,
#                 'AttributeName': 'ttl'  # Auto-delete old locations after 5 minutes
#             }
#         )
#         print("driver-locations table created!")
#     except dynamodb.meta.client.exceptions.ResourceInUseException:
#         print("driver-locations table already exists")

#     # Table 2: Zone demand tracking (requests per zone per minute)
#     try:
#         table = dynamodb.create_table(
#             TableName='zone-demand',
#             KeySchema=[
#                 {'AttributeName': 'zone_id', 'KeyType': 'HASH'},
#                 {'AttributeName': 'timestamp_minute', 'KeyType': 'RANGE'}
#             ],
#             AttributeDefinitions=[
#                 {'AttributeName': 'zone_id', 'AttributeType': 'S'},
#                 {'AttributeName': 'timestamp_minute', 'AttributeType': 'S'}
#             ],
#             BillingMode='PAY_PER_REQUEST'
#         )
#         print("zone-demand table created!")
#     except dynamodb.meta.client.exceptions.ResourceInUseException:
#         print("zone-demand table already exists")


# ──────────────────────────────────────────────────────────────────
# 3. S3 Bucket (Data Lake — Firehose writes here)
# ──────────────────────────────────────────────────────────────────
def create_s3_bucket():
    """
    Create the S3 bucket that Firehose writes archived ride events to.
    Firehose delivers data as:
      s3://quickride-data-lake/raw/rides/year=YYYY/month=MM/day=DD/hour=HH/
    """
    try:
        # AWS quirk: only us-west-1 omits LocationConstraint. All other regions (including us-west-1) require it!
        if REGION == 'us-west-1':
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


# ──────────────────────────────────────────────────────────────────
# 6. IAM Role for Lambda (QuickRideLambdaRole)
# ──────────────────────────────────────────────────────────────────
# def create_lambda_iam_role():
#     """
#     Create the IAM role that the Lambda consumer assumes to:
#       - Read from the Kinesis Data Stream (ride-events)
#       - Write to the DynamoDB tables (driver-locations, zone-demand)
#       - Publish to the SNS topic (operations-alerts)
#       - Write logs to CloudWatch Logs
    
#     Use this role's ARN when deploying consumer.py to Lambda.
#     """

#     # Trust policy: allow Lambda service to assume this role
#     trust_policy = {
#         "Version": "2012-10-17",
#         "Statement": [
#             {
#                 "Effect": "Allow",
#                 "Principal": {"Service": "lambda.amazonaws.com"},
#                 "Action": "sts:AssumeRole"
#             }
#         ]
#     }

#     # Permissions policy: what Lambda can do with this role
#     permissions_policy = {
#         "Version": "2012-10-17",
#         "Statement": [
#             {
#                 "Sid": "KinesisReadAccess",
#                 "Effect": "Allow",
#                 "Action": [
#                     "kinesis:DescribeStream",
#                     "kinesis:DescribeStreamSummary",
#                     "kinesis:GetRecords",
#                     "kinesis:GetShardIterator",
#                     "kinesis:ListShards"
#                 ],
#                 "Resource": f"arn:aws:kinesis:{REGION}:{ACCOUNT_ID}:stream/{KINESIS_STREAM_NAME}"
#             },
#             {
#                 "Sid": "DynamoDBAccess",
#                 "Effect": "Allow",
#                 "Action": [
#                     "dynamodb:BatchWriteItem",
#                     "dynamodb:PutItem",
#                     "dynamodb:UpdateItem",
#                     "dynamodb:Scan",
#                     "dynamodb:GetItem"
#                 ],
#                 "Resource": [
#                     f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/driver-locations",
#                     f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/zone-demand"
#                 ]
#             },
#             {
#                 "Sid": "SNSPublishAccess",
#                 "Effect": "Allow",
#                 "Action": [
#                     "sns:Publish"
#                 ],
#                 "Resource": f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{SNS_TOPIC_NAME}"
#             },
#             {
#                 "Sid": "CloudWatchLogsAccess",
#                 "Effect": "Allow",
#                 "Action": [
#                     "logs:CreateLogGroup",
#                     "logs:CreateLogStream",
#                     "logs:PutLogEvents"
#                 ],
#                 "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/aws/lambda/*"
#             }
#         ]
#     }

#     try:
#         # Create the IAM role
#         iam_client.create_role(
#             RoleName=LAMBDA_ROLE_NAME,
#             AssumeRolePolicyDocument=json.dumps(trust_policy),
#             Description='Allows Lambda to read Kinesis, write to DynamoDB, and publish to SNS for the QuickRide pipeline',
#             Tags=[
#                 {'Key': 'Project', 'Value': 'QuickRide'}
#             ]
#         )
#         print(f"IAM role '{LAMBDA_ROLE_NAME}' created!")

#         # Attach the inline permissions policy
#         iam_client.put_role_policy(
#             RoleName=LAMBDA_ROLE_NAME,
#             PolicyName='LambdaExecutionPolicy',
#             PolicyDocument=json.dumps(permissions_policy)
#         )
#         print(f"  Permissions policy attached to '{LAMBDA_ROLE_NAME}'")
#         lambda_role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{LAMBDA_ROLE_NAME}"
#         print(f"  Role ARN: {lambda_role_arn}")

#         # Wait for propagation
#         print("  Waiting 10 seconds for IAM role propagation...")
#         time.sleep(10)
#         return lambda_role_arn

#     except iam_client.exceptions.EntityAlreadyExistsException:
#         print(f"IAM role '{LAMBDA_ROLE_NAME}' already exists")
#         return f"arn:aws:iam::{ACCOUNT_ID}:role/{LAMBDA_ROLE_NAME}"


# ──────────────────────────────────────────────────────────────────
# Main: Run all setup steps in order
# ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("QuickRide Infrastructure Setup")
    print("=" * 60)
    print(f"Account ID: {ACCOUNT_ID}")
    print(f"Region:     {REGION}")
    print()

    

    # print("─" * 60)
    # print("Step 2/6: Creating DynamoDB Tables...")
    # print("─" * 60)
    # create_dynamodb_tables()
    # print()

    print("─" * 60)
    print("Step 3/6: Creating S3 Bucket (Data Lake)...")
    print("─" * 60)
    create_s3_bucket()
    print()

    

    # print("─" * 60)
    # print("Step 6/6: Creating IAM Role for Lambda Consumer...")
    # print("─" * 60)
    # lambda_role_arn = create_lambda_iam_role()
    # print()

    print("=" * 60)
    print("Infrastructure setup complete!")
    print("=" * 60)
    # if lambda_role_arn:
    #     print(f"\n⚠️  IMPORTANT: Save this Lambda Execution Role ARN for Lambda deployment:")
    #     print(f"   {lambda_role_arn}")
    #     print(f"   Use this role when deploying your Lambda function.")
