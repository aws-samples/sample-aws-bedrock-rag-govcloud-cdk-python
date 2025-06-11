EMBEDDING_MODEL_IDs = ["amazon.titan-embed-text-v2:0"]
CHUNKING_STRATEGIES = {0:"Default",1:"Fixed-size", 2:"No"}
QUERY_MODEL_IDs = ["amazon.nova-micro-v1:0","amazon.titan-text-express-v1"]

class EnvSettings:
    # General params
    PROJ_NAME = "chatbotdemo" # TODO: Change this to any name of your choice ***Max Lenght = 12 Char
    VPC_CIDR = "10.1.1.0/26"

class KbConfig:
    KB_NAME = f"{EnvSettings.PROJ_NAME}-kb"
    KB_ROLE_NAME = f"{EnvSettings.PROJ_NAME}-kb-role"
    EMBEDDING_MODEL_ID = EMBEDDING_MODEL_IDs[0]
    CHUNKING_STRATEGY = CHUNKING_STRATEGIES[1] # TODO: Choose the Chunking option 0,1,2
    MAX_TOKENS = 8000 # TODO: Change this value accordingly if you choose "FIXED_SIZE" chunk strategy
    OVERLAP_PERCENTAGE = 20 # TODO: Change this value accordingly
    QUERY_MODEL_ID = QUERY_MODEL_IDs[0]

class DsConfig:
    S3_BUCKET_NAME = f"" # TODO: Change this to the S3 bucket where your data is stored.New bucket will be created if you leave this field empty

class OpenSearchServerlessConfig:
    COLLECTION_NAME = f"{EnvSettings.PROJ_NAME}-collection"
    INDEX_NAME = f"{EnvSettings.PROJ_NAME}-kb-index"
    LAMBDA_ROLE_NAME = f"{EnvSettings.PROJ_NAME}_lambda_role"
    KMS_KEY = f"{EnvSettings.PROJ_NAME}_kms_key"
    AWS_MANAGED_KEY = True  
    ALLOW_FROM_PUBLIC = True  # This is for dashboards. Still needs SAML or IAM integration to access
    VPC_ENDPOINT = "" # VPC Endpoint ID. Currently can only be created from AWS console
    VECTOR_FIELD_NAME = "vector-field"

class APIConfig:
    API_NAME=f"{EnvSettings.PROJ_NAME}-api"
    STAGE_NAME="dev"
    API_THROTTLE_RATE_LIMIT=100
    API_THROTTLE_BURST_LIMIT=100
    API_QUOTA_LIMIT=1000
    API_QUOTA_PERIOD="DAY"  # DAY WEEK MONTH
    API_KEY_NAME=f"{EnvSettings.PROJ_NAME}-api-key"

