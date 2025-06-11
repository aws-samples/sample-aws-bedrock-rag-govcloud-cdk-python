# Method to store values in AWS Systems Manager Parameter Store
import aws_cdk as _cdk
from aws_cdk import (
    aws_ssm as ssm,
    CfnOutput as _output,
    aws_lambda as _lambda,
    Duration,
    aws_iam as _iam,
    aws_ec2 as ec2,
    Tags as Tags
)

from aws_cdk.aws_logs import RetentionDays, LogGroup

class Util:
    
    @staticmethod
    def store_in_parameter_store(self,name, value, id,description):
        _output(self,f"cfn_{id}",value=value,
                description=description,export_name=name)
        return ssm.StringParameter(self,id, parameter_name=f"/serverlessrag/{name}", string_value=value,description=description)

# Method to get a parameter from AWS Systems Manager Parameter Store

    @staticmethod
    def get_from_parameter_store(self,key):
        return ssm.StringParameter.from_string_parameter_attributes(self,id=key,parameter_name=f"/serverlessrag/{key}").string_value

    def create_lambda_function(self, func_id: str, **kwargs):
        # Set default values if not provided in kwargs
        if "runtime" not in kwargs:
            kwargs["runtime"] = _lambda.Runtime.PYTHON_3_13
        if "code" not in kwargs:
            kwargs["code"] = _lambda.Code.from_asset("src")
        if "environment" not in kwargs:
            kwargs["environment"] = {}
        if "timeout" not in kwargs:
            kwargs["timeout"] = Duration.seconds(29)
            
        # Handle VPC configuration if provided
        if "vpc" in kwargs:
            vpc = kwargs.get("vpc")
            if vpc is not None:
                if "vpc_subnets" not in kwargs:
                    kwargs["vpc_subnets"] = ec2.SubnetSelection(
                        subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                    )
                
        return _lambda.Function(
            self,
            func_id,
            **kwargs
        )

    def add_permissions_to_lambda(self, lambda_function, effect,actions, resources, conditions=None):
        policy_statement_props = {
            "effect": _iam.Effect.ALLOW if effect else _iam.Effect.DENY,
            "actions": actions,
            "resources": resources
        }
        
        if conditions is not None:
            policy_statement_props["conditions"] = conditions
            
        lambda_function.add_to_role_policy(
            _iam.PolicyStatement(**policy_statement_props)
        )


    def create_lambda_execution_role(self,function_name) -> _iam.Role:
        role = _iam.Role(self, f"{function_name}-CreateIndexExecutionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f'Managed by CDK - {function_name}',
        )
        
        # Create the log group explicitly
        log_group = LogGroup(self, "LambdaLogGroup",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=RetentionDays.ONE_WEEK,
            removal_policy=_cdk.RemovalPolicy.DESTROY
        )
         # Add CloudWatch Logs permissions with specific resources
        role.add_to_policy(_iam.PolicyStatement(
        effect=_iam.Effect.ALLOW,
        actions=[
            "logs:CreateLogStream",
            "logs:PutLogEvents"
        ],
        resources=[log_group.log_group_arn]))
        return role
 