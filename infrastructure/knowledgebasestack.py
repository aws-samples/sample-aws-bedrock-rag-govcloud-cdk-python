import json
from infrastructure.util import Util
import hashlib
from typing import Any, Dict
from aws_cdk import (
    Stack,
    aws_iam as iam_,
    aws_bedrock as bedrock,
    Fn as Fn,
    aws_s3 as s3,
    RemovalPolicy
)
from aws_cdk.aws_bedrock import (
  CfnKnowledgeBase,
  CfnDataSource,
)
from aws_cdk.aws_opensearchserverless import (
  CfnAccessPolicy,
)
from constructs import Construct
import cdk_nag as _cdk_nag
from config import EnvSettings, KbConfig,DsConfig,OpenSearchServerlessConfig

application_name = EnvSettings.PROJ_NAME
kb_name = KbConfig.KB_NAME
text_field = "AOSS_KB_TEXT_CHUNK"
metadata_field = "AOSS_KB_METADATA"

class  KnowledgeBaseStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, dictenv,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        region = dictenv['region']
        account_id = dictenv['account_id']
        self.collectionArn = Util.get_from_parameter_store(self,"collectionArn")
        self.collectionName = Util.get_from_parameter_store(self,"collectionName")
        self.arn_partition='aws-us-gov' if('gov' in region) else 'aws'  
        self.embedding_model_arn = f"arn:{self.arn_partition}:bedrock:{region}::foundation-model/{KbConfig.EMBEDDING_MODEL_ID}"
        self.data_bucket_arn=self.get_bucket_arn(DsConfig.S3_BUCKET_NAME)
       
        # Create an execution role for the knowledge base
        self.kbRole = self.create_kb_execution_role()
        self.dataccesspolicy = self. create_data_access_policy_aoss(self.collectionName,self.kbRole)
        self.knowledge_base = self.create_knowledge_base(self.kbRole)
        self.data_source = self.create_data_source(self.knowledge_base)
        # create an SSM parameters which store export values
        Util.store_in_parameter_store(self, "knowledgebaseId", self.knowledge_base.attr_knowledge_base_id, "knowledgebaseId", "Knowledge Base Id")
        Util.store_in_parameter_store(self, "knowledgebaseArn", self.knowledge_base.attr_knowledge_base_arn, "knowledgebaseArn", "Knowledge Base Arn")
        Util.store_in_parameter_store(self, "datasourceId", self.data_source.attr_data_source_id, "datasourceId", "Data Source Id")
        Util.store_in_parameter_store(self, "databucketArn", self.data_bucket_arn, "databucketArn", "S3 Bucket Arn")
    
    def get_bucket_arn(self,bucket:str):
        if bucket is None or bucket == "":
              # Create S3 bucket for the knowledgebase assets
               # Create a unique string to create unique resource names
            hash_base_string = (self.account + self.region)
            hash_base_string = hash_base_string.encode("utf8")
            # Create a logs bucket first
            logs_bucket = s3.Bucket(self, "KnowledgebaseLogs",
                bucket_name=(f"{application_name}-logs-" + str(hashlib.sha384(hash_base_string).hexdigest())[:10]).lower(),
                auto_delete_objects=True,
                versioned=False,
                removal_policy=RemovalPolicy.DESTROY,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
                encryption=s3.BucketEncryption.S3_MANAGED)
        
            kb_bucket = s3.Bucket(self, "Knowledgebase",
                bucket_name=(f"{application_name}" + str(hashlib.sha384(hash_base_string).hexdigest())[:15]).lower(),
                auto_delete_objects=True,
                versioned=False,
                removal_policy=RemovalPolicy.DESTROY,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
                encryption=s3.BucketEncryption.S3_MANAGED,
                server_access_logs_bucket=logs_bucket,
                server_access_logs_prefix="kb-bucket-logs/")
      
            return kb_bucket.bucket_arn
        else:
            return f"arn:{self.arn_partition}:s3:::{bucket}"

    def create_kb_execution_role(self) -> iam_.Role:
            model_policy = iam_.Policy(
                self,f"AmazonBedrockFoundationModelPolicyForKB_{kb_name}",
                statements=[
                    iam_.PolicyStatement(effect=iam_.Effect.ALLOW,actions=["bedrock:InvokeModel"],
                                         resources=[self.embedding_model_arn],)
                ],
            )
            aoss_policy = iam_.Policy(
                self,f"AmazonBedrockOSSPolicyForKnowledgeBase_{kb_name}",
                statements=[
                    iam_.PolicyStatement(effect=iam_.Effect.ALLOW,actions=["aoss:APIAccessAll"],
                        resources=[self.collectionArn],
                    )
                ],
            )
            s3_policy = iam_.Policy(
                self,f"S3PolicyForKnowledgeBase_{kb_name}",
                statements=[
                    iam_.PolicyStatement(effect=iam_.Effect.ALLOW,actions=[ "s3:GetObject","s3:ListBucket"],
                        resources=[ self.data_bucket_arn,f"{self.data_bucket_arn}/*", self.data_bucket_arn,f"{self.data_bucket_arn}*"],
                    )
                ],
            )
            return iam_.Role(self,"KnowledgeBaseRole",role_name=f'{KbConfig.KB_NAME}_role',
                assumed_by=iam_.ServicePrincipal("bedrock.amazonaws.com"),
                managed_policies=[model_policy, aoss_policy,s3_policy,],
            )

                   
    def create_data_access_policy_aoss(self,collectionName: str,kb_role: iam_.Role) -> CfnAccessPolicy:
        principal_arns = [kb_role.role_arn]
       
        accesspolicy: Dict[str, Any] =  [{ 
                     "Rules": [{"ResourceType": "index","Resource": [f"index/{collectionName}/*",],
                    "Permission": ["aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument","aoss:CreateIndex","aoss:DeleteIndex",],},
                    {"ResourceType": "collection","Resource": [f"collection/{collectionName}",],
                    "Permission": ["aoss:DescribeCollectionItems","aoss:CreateCollectionItems","aoss:UpdateCollectionItems",],},],
                    "Principal": principal_arns,
                    } ]
                 
        return CfnAccessPolicy(self,"DataAccessPolicy",name=f"{application_name}-kbaccess",type="data",policy=json.dumps(accesspolicy),)
   
       
    def create_knowledge_base(self, kb_role: iam_.Role) -> CfnKnowledgeBase:  
            knowledgebase =  bedrock.CfnKnowledgeBase(
            self,"aossKB",
            role_arn=kb_role.role_arn,
            name=kb_name,
            description=f'Managed by CDK - {application_name}',
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=self.embedding_model_arn
                ),
            ),
            storage_configuration=CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=self.collectionArn,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        metadata_field=metadata_field,
                        text_field=text_field,
                        vector_field=OpenSearchServerlessConfig.VECTOR_FIELD_NAME
                    ),
                    vector_index_name=OpenSearchServerlessConfig.INDEX_NAME
                ),
            ),
        )
            return knowledgebase
    
       

    def create_data_source(self, knowledge_base) -> CfnDataSource:
        chunk_strategy = KbConfig.CHUNKING_STRATEGY
        kbid = knowledge_base.attr_knowledge_base_id
        if chunk_strategy == "Fixed-size":
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=KbConfig.MAX_TOKENS,
                        overlap_percentage=KbConfig.OVERLAP_PERCENTAGE
                    )
                )
            )  
        elif chunk_strategy == "Default":
            vector_ingestion_configuration = bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=300,
                        overlap_percentage=20
                    )
                )
            )      
        else:
            vector_ingestion_configuration = bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="NONE"
                )
            )
        return bedrock.CfnDataSource(
            self,
            "RagDataSource",
            knowledge_base_id=kbid,
            name=f"{application_name}_s3_source",
            description= f'Managed by CDK - {application_name}',
            data_deletion_policy="RETAIN",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.data_bucket_arn,
                ),
                type="S3",
            ),
            vector_ingestion_configuration=vector_ingestion_configuration
        )
      
    