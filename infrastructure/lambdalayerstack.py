from infrastructure.util import Util
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    BundlingOptions,
    Tags as Tags
)
from constructs import Construct
from config import EnvSettings
application_name = EnvSettings.PROJ_NAME

class  LambdaLayerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lambdalayer = self.BuildLambdaLayer()
        Util.store_in_parameter_store(self,'lambdalayerArn', self.lambdalayer.layer_version_arn, 'lambdalayerArn','Lambda Layer Arn')

    #   
   
    def BuildLambdaLayer(self):
        lambdalayer =  lambda_.LayerVersion(
            scope=self,
            id="LayerVersion_opensearch-py_latest",
            layer_version_name=f"{application_name}-lambda-layer",
            description="opensearch-py-python-layer",
            compatible_architectures=[lambda_.Architecture.X86_64],
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
            code=lambda_.Code.from_asset(
                path="./src",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_13.bundling_image,
                    command=self.getBundlingCommand(),
                       ),
            ),
        )
        return lambdalayer
            
    def getBundlingCommand(self):
        return [
                "bash","-c"," && ".join(
                    [
                        "mkdir /asset-output/python",
                        (f'pip3 install --no-cache -t /asset-output/python -r requirements.txt'),
                        "cp -au . /asset-output/python",
                    ]
                ),
            ]

 
   
     