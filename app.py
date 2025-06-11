#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Tags
from infrastructure.aossstack import OpensearchVectorDbStack
from infrastructure.knowledgebasestack import KnowledgeBaseStack
from infrastructure.lambdalayerstack import LambdaLayerStack
from infrastructure.apistack import APIStack
from config import EnvSettings
from cdk_nag import AwsSolutionsChecks

app = cdk.App()

def tag_my_stack(stack):
    tags = Tags.of(stack)
    tags.add("project", EnvSettings.PROJ_NAME)

account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
region = os.getenv('CDK_DEFAULT_REGION')
application_name = EnvSettings.PROJ_NAME
env=cdk.Environment(account=account_id, region=region)

dictenv = {
    "region": region,
    "account_id": account_id
}

lambdalayerstack = LambdaLayerStack(app, "lambdalayerstack",
            env=env,description="AWS Lambda Layers",)
tag_my_stack(lambdalayerstack)

aossstack = OpensearchVectorDbStack(app, "aossstack",
            env=env,description="AWS OpenSearch Serverless resources", 
            dictenv=dictenv)
tag_my_stack(aossstack)


kbstack =   KnowledgeBaseStack(app, "knowledgebasestack",
            env=env,description="Knowledgebases for Amazon Bedrock agent resources", 
            dictenv=dictenv)
tag_my_stack(kbstack)

apistack =   APIStack(app, "apistack",
            env=env,description="Api to injest and query from knowledge bases", 
            dictenv=dictenv)
tag_my_stack(apistack)

aossstack.add_dependency(lambdalayerstack)
kbstack.add_dependency(aossstack)
apistack.add_dependency(kbstack)
# applying the cdk-nag AWSSolutions Rule Pack
# cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
