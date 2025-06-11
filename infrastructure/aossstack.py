
import json
import aws_cdk as _cdk
from infrastructure.util import Util
from typing import Any, Dict, List
from aws_cdk import (
    Stack,
    aws_kms as kms,
    aws_iam as iam_,
    aws_lambda as lambda_,
    custom_resources as cr,
    RemovalPolicy,
    Fn as Fn,
    Duration,
    Tags as Tags
)
from constructs import Construct
from aws_cdk.aws_opensearchserverless import (
  CfnAccessPolicy,
  CfnCollection,
  CfnSecurityPolicy,
)
from config import EnvSettings, OpenSearchServerlessConfig


application_name = EnvSettings.PROJ_NAME
collection_name = OpenSearchServerlessConfig.COLLECTION_NAME


class SecurityPolicyType(str):
  ENCRYPTION = "encryption"
  NETWORK = "network"

class StandByReplicas(str):
  ENABLED = "ENABLED"
  DISABLED = "DISABLED"

class CollectionType(str):
  VECTORSEARCH = "VECTORSEARCH"
  SEARCH = "SEARCH"
  TIMESERIES = "TIMESERIES"

class AccessPolicyType(str):
  DATA = "data"
     
class  OpensearchVectorDbStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, dictenv,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.regn = dictenv['region']
        self.account_id=dictenv['account_id']
        self.arn_partition='aws-us-gov' if('gov' in self.regn) else 'aws'  
        self.lambdaLayer = lambda_.LayerVersion.from_layer_version_arn(self,"lambda_layer",layer_version_arn=Util.get_from_parameter_store(self,"lambdalayerArn"))
      
        self.encryptionPolicy = self.create_encryption_policy(collection_name)
        self.networkPolicy = self.create_network_policy(collection_name)
        self.lambdaExecutionRole = self.create_lambda_execution_role()
        self.dataAccessPolicy = self.create_data_access_policy(collection_name,self.lambdaExecutionRole.role_arn)
        self.collection = self.create_collection(collection_name,self.lambdaExecutionRole)
        # Create collecction after all the policies are created
        self.collection.add_dependency(self.encryptionPolicy)
        self.collection.add_dependency(self.networkPolicy)
        self.collection.add_dependency(self.dataAccessPolicy)


        # create an SSM parameters which store export values

        Util.store_in_parameter_store(self,'collectionArn', self.collection.attr_arn, 'collectionArn','Collection Arn')
        Util.store_in_parameter_store(self, 'collectionId', self.collection.attr_id, 'collectionId', 'Collection Id')
        Util.store_in_parameter_store(self, 'collectionName', self.collection.name, 'collectionName', 'Collection Name')
        
        self.create_oss_index(self.lambdaExecutionRole)

    def create_encryption_policy(self,collectionName: str) -> CfnSecurityPolicy:
        kms_key_arn = kms.Key(self,"OpenSearchKMSKey",alias=OpenSearchServerlessConfig.KMS_KEY,enable_key_rotation=True,).key_arn if not OpenSearchServerlessConfig.AWS_MANAGED_KEY else None
        encpolicy: Dict[str, Any] = {
             "Rules": [{"ResourceType": "collection","Resource": [f"collection/{collection_name}",],},
                      ],} 
        if kms_key_arn:
            encpolicy["KmsARN"] = kms_key_arn
        else:
            encpolicy["AWSOwnedKey"] = True
        return CfnSecurityPolicy(self, "EncryptionPolicy",name=f"{collectionName}-enc",type=SecurityPolicyType.ENCRYPTION,policy=json.dumps(encpolicy),)

    def create_network_policy(self,collectionName: str) -> CfnSecurityPolicy:
        vpc_endpoint = OpenSearchServerlessConfig.VPC_ENDPOINT if not OpenSearchServerlessConfig.ALLOW_FROM_PUBLIC else OpenSearchServerlessConfig.VPC_ENDPOINT
        netpolicy: List[Dict[str, Any]] = [{
            "Rules": [
                {"ResourceType": "dashboard", "Resource": [f"collection/{collectionName}",],},
                {"ResourceType": "collection","Resource": [f"collection/{collectionName}",],},
            ],} ]
        if vpc_endpoint:
            netpolicy[0]["SourceVPCEs"] = vpc_endpoint
        else:
            netpolicy[0]["AllowFromPublic"] = True
        return CfnSecurityPolicy(self,"NetworkPolicy",name=f"{collectionName}-net",type=SecurityPolicyType.NETWORK,policy=json.dumps(netpolicy),)

    def create_lambda_execution_role(self) -> iam_.Role:
        function_name = f"{OpenSearchServerlessConfig.INDEX_NAME}-Lambda"
        role = Util.create_lambda_execution_role(self,function_name)  
        return role
  
    def create_data_access_policy(self,collectionName: str,lambdaindexExecutionroleArn: str) -> CfnAccessPolicy:

        principal_arns = [iam_.AccountPrincipal(Stack.of(self).account).arn,lambdaindexExecutionroleArn]
        accesspolicy: Dict[str, Any] =  [{ 
                     "Rules": [{"ResourceType": "index","Resource": [f"index/{collection_name}/*",],
                    "Permission": ["aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument","aoss:CreateIndex","aoss:DeleteIndex",],},
                    {"ResourceType": "collection","Resource": [f"collection/{collection_name}",],
                    "Permission": ["aoss:DescribeCollectionItems","aoss:CreateCollectionItems","aoss:UpdateCollectionItems",],},],
                    "Principal": principal_arns,
                    } ]
        return CfnAccessPolicy(self,"DataAccessPolicy",name=f"{collectionName}-access",type=AccessPolicyType.DATA,policy=json.dumps(accesspolicy),)

    
    def create_collection(self,collectionName: str,lambdaExecutionRole: iam_.Role) -> CfnCollection:
    
        open_search_collection = CfnCollection(self,"Collection",name=collectionName,description= f'Managed by CDK - {application_name}', 
                                 #   standbyReplicas=StandByReplicas.DISABLED,
                                 type= CollectionType.VECTORSEARCH,)
        lambdaExecutionRole.add_to_policy(
            iam_.PolicyStatement(effect=iam_.Effect.ALLOW,actions=["aoss:APIAccessAll"],
                resources=[f"arn:{self.arn_partition}:aoss:{self.regn}:{self.account_id}:collection/{open_search_collection.attr_id}"],
            )
        )
        return open_search_collection
    
    def create_oss_index(self,lambdaExecutionRole: iam_.Role):
        index_lambda_function = lambda_.Function(self, "create-index-function",
            function_name=f"{OpenSearchServerlessConfig.INDEX_NAME}-Lambda",
                code = lambda_.Code.from_asset("src"),
                runtime=lambda_.Runtime.PYTHON_3_13,
                handler="ossindex.handler",
                role=lambdaExecutionRole,
                layers=[self.lambdaLayer],
                memory_size=1024,
                timeout=_cdk.Duration.minutes(15),
                description=f'Managed by CDK - {application_name}',
                environment={ "REGION_NAME": self.region,
                                        "COLLECTION_HOST": self.collection.attr_collection_endpoint,
                                        "VECTOR_INDEX_NAME": OpenSearchServerlessConfig.INDEX_NAME,
                                        "VECTOR_FIELD_NAME": OpenSearchServerlessConfig.VECTOR_FIELD_NAME,})

        oss_provider_role = iam_.Role(
                self,
                "OSSProviderRole",
                assumed_by=iam_.ServicePrincipal("lambda.amazonaws.com"),
            )
        oss_provider_role.add_to_policy(iam_.PolicyStatement(actions=[
                "aoss:CreateIndex",
                "aoss:DeleteIndex",
                "aoss:UpdateIndex",
                "aoss:DescribeIndex",
                "aoss:ListIndices",
                "aoss:BatchGetIndex",
                "aoss:APIAccessAll",
        ],
        resources=[f"arn:{self.arn_partition}:aoss:{self.regn}:{self.account_id}:collection/{self.collection.attr_id}"]))

    # Define the request body for the lambda invoke api call that the custom resource will use
        aossLambdaParams = {
                    "FunctionName": index_lambda_function.function_name,
                    "InvocationType": "RequestResponse"
                }
        
        # On creation of the stack, trigger the Lambda function we just defined 
        trigger_lambda_cr = cr.AwsCustomResource(self, "IndexCreateCustomResource",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters=aossLambdaParams,
                physical_resource_id=cr.PhysicalResourceId.of("Parameter.ARN")
                ),
                role=oss_provider_role,
            removal_policy = RemovalPolicy.DESTROY,
            timeout=Duration.seconds(120)
            )
                # Define IAM permission policy for the custom resource    
        trigger_lambda_cr.grant_principal.add_to_principal_policy(iam_.PolicyStatement(
            effect=iam_.Effect.ALLOW,
            actions=["lambda:InvokeFunction", "iam:CreateServiceLinkedRole", "iam:PassRole"],
            resources=[index_lambda_function.function_arn],
            ))
        trigger_lambda_cr.node.add_dependency(self.collection)