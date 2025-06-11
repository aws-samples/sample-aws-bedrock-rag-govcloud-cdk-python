from infrastructure.util import Util
import aws_cdk as _cdk
from aws_cdk import (
    Stack,
    Fn as Fn,
    aws_lambda as lambda_,
    aws_apigateway as apigw_,
    aws_logs,
    aws_iam as iam_,
    aws_ec2 as ec2,
    Tags as Tags,
    RemovalPolicy
)
from constructs import Construct
from config import EnvSettings, APIConfig,KbConfig

application_name = EnvSettings.PROJ_NAME
api_name = APIConfig.API_NAME
stage_name=APIConfig.STAGE_NAME


class  APIStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, dictenv,**kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
       
        self.regn = dictenv['region']
        self.acct = dictenv['account_id']
        self.lambdaLayer = lambda_.LayerVersion.from_layer_version_arn(self,"lambda_layer",layer_version_arn=Util.get_from_parameter_store(self,"lambdalayerArn"))
        self.knowledgebaseId = Util.get_from_parameter_store(self,"knowledgebaseId")
        self.knowledgebaseArn = Util.get_from_parameter_store(self,"knowledgebaseArn")
        self.datasourceId = Util.get_from_parameter_store(self,"datasourceId")

        self.arn_partition='aws-us-gov' if('gov' in self.regn) else 'aws'  

        self.vpc = self.CreatePrivateVPC()
        Util.store_in_parameter_store(self,'vpcid', self.vpc.vpc_id, 'vpcid','VPC ID')
        self.security_group = self.CreateSecurityGroup()
         
        self.query_lambda = self. create_query_lambda(self.knowledgebaseId,self.arn_partition,self.lambdaLayer,self.vpc,self.security_group)
        Util.store_in_parameter_store(self,"querylambdaArn",self.query_lambda.function_arn,"querylambdaArn","Query Lambda Arn")

        # Create API Gateway
        self.api_throttle_rate_limit = APIConfig.API_THROTTLE_RATE_LIMIT
        self.api_throttle_burst_limit = APIConfig.API_THROTTLE_BURST_LIMIT
        self.api_throttle_settings = {
                     "rate_limit": int(self.api_throttle_rate_limit),
                     "burst_limit": int(self.api_throttle_burst_limit),
                    }
        self.api_quota_limit = APIConfig.API_QUOTA_LIMIT
        self.api_quota_period = APIConfig.API_QUOTA_PERIOD
        self.api_quota_settings = {"limit": int(self.api_quota_limit), "period": self.api_quota_period}
        self.api_key_name = APIConfig.API_KEY_NAME

        self.api_gw = self.create_api_gw(self.query_lambda)
        self.create_api_resources(self.query_lambda,self.api_gw)
        Util.store_in_parameter_store(self,"apigateway", self.api_gw.rest_api_id, "apigateway", "API Gateway ID")
        self.api_usage_plan = self.create_usage_plan(self.api_gw,
            self.create_throttle_constructor(self.api_throttle_settings), self.create_quota_constructor(self.api_quota_settings)
        )
        Util.store_in_parameter_store(self,"APIUsagePlanID", self.api_usage_plan.usage_plan_id, "APIUsagePlanID", "API Usage Plan ID")

    def CreatePrivateVPC(self):
        # Create a VPC with private subnets
        vpc = ec2.Vpc(self, vpc_name = f"{application_name}-vpc", id = f"{application_name}-vpc",
            max_azs=2,
            nat_gateways=0,
            ip_addresses=ec2.IpAddresses.cidr(EnvSettings.VPC_CIDR),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name= f"private-subnet",
                    cidr_mask=28,
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                )
            ],
        )
        Tags.of(vpc).add("Name", f"{application_name}-vpc")
        for i, subnet in enumerate(vpc.isolated_subnets):
            Tags.of(subnet).add("Name", f"{application_name}-private-subnet-{i+1}")
        vpc.add_flow_log(f"{application_name}-vpc")
        return vpc
    
    def CreateSecurityGroup(self):
        security_group = ec2.SecurityGroup(self,f"{application_name}-sg",vpc=self.vpc,
                     allow_all_outbound = True,
                    security_group_name = f"{application_name}-sg",
                    description = "Allow traffic with in the VPC")
        security_group.add_ingress_rule(security_group, ec2.Port.HTTP, "Allow HTTP inbound traffic from VPC CIDR")
        security_group.add_ingress_rule(security_group, ec2.Port.HTTPS, "Allow HTTPS inbound traffic from VPC CIDR")
        return security_group
     
    # { "body": "{\"question\":\"<Question>\"}" }
    # Lambda to query from knowledgebases
    def create_query_lambda(self, knowledgebaseId,partition,lambdalayer,vpc,securitygroup) -> lambda_:
        ModelArn = f"arn:{partition}:bedrock:{self.regn}::foundation-model/{KbConfig.QUERY_MODEL_ID}"
        lambdavpce = ec2.InterfaceVpcEndpoint(self,f"{application_name}-bdvpce",   
            vpc=self.vpc,                                     
            service=ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENT_RUNTIME,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )
        Tags.of(lambdavpce).add("Name", f"{application_name}-bdvpce")

        function_name = f"{application_name}-QueryKb"
        role = Util.create_lambda_execution_role(self,function_name)  
                
        query_lambda = Util.create_lambda_function(self, function_name,
                function_name=function_name,
                description="Lambda to query from knowledgebases",
                handler="kbquery_handler.handler",
                code= lambda_.Code.from_asset("src"),
                layers=[lambdalayer],
                role=role,
                vpc=vpc,
                security_groups=[securitygroup],
                timeout=_cdk.Duration.minutes(5),
                environment={"KNOWLEDGE_BASE_ID": knowledgebaseId,
                             "MODEL_ARN" : ModelArn})

        # Add permissions for Bedrock Models in GovCloud
        query_lambda.add_to_role_policy(
            iam_.PolicyStatement(
            effect=iam_.Effect.ALLOW,
            actions=["bedrock:RetrieveAndGenerate", "bedrock:Retrieve", "bedrock:InvokeModel"],
            resources=["*"], # Configurable from environment parameters. Need to allow all enabled bedrock models.
            conditions={
                "ForAllValues:StringEquals": {
                "aws:SourceVpce": f"{lambdavpce.vpc_endpoint_id}"
            }}))

        query_lambda.add_to_role_policy(
            iam_.PolicyStatement(
            effect=iam_.Effect.ALLOW,
            actions=[
                 "ec2:CreateNetworkInterface",
                 "ec2:DescribeNetworkInterfaces",
                 "ec2:DeleteNetworkInterface",
                 "ec2:AssignPrivateIpAddresses",
                 "ec2:UnassignPrivateIpAddresses",
                 "ec2:DescribeSubnets"
            ],
            resources=["*"],))
        query_lambda.add_to_role_policy(
            iam_.PolicyStatement(
            effect=iam_.Effect.DENY,
            actions=[
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeSubnets",
                "ec2:DetachNetworkInterface",
                "ec2:AssignPrivateIpAddresses",
                "ec2:UnassignPrivateIpAddresses"
        ],
            resources=["*"],
            conditions={
            "ArnEquals": {
                "lambda:SourceFunctionArn": [
                    f"arn:{partition}:lambda:{self.region}:{self.account}:function:my_function"
                ]}}))                          
        return query_lambda
    
# {"question":"<Question>"}
    # Method to create REST API
    def create_api_gw(self,querylambda):  
        apivpce = ec2.InterfaceVpcEndpoint(self,f"{application_name}-apivpce",   
            vpc=self.vpc,                                     
            service=ec2.InterfaceVpcEndpointAwsService.APIGATEWAY,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )
        Tags.of(apivpce).add("Name", f"{application_name}-apivpce")
        access_log_group = aws_logs.LogGroup(
            self, 
            "ApiAccessLogs",
            log_group_name=f"/aws/apigateway/{api_name}-access-logs",
            retention=aws_logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY)
        
        api = apigw_.LambdaRestApi(
            self,api_name,handler=querylambda,proxy = False,description="Thia API enables you to set up a chatbot using Amazon Bedrock in an AWS GovCloud account.",
            endpoint_configuration=apigw_.EndpointConfiguration(
            types=[apigw_.EndpointType.PRIVATE],
            vpc_endpoints=[apivpce]
            ),
            policy=iam_.PolicyDocument(
            statements=[
                iam_.PolicyStatement(
                    actions=["execute-api:Invoke"],
                    resources=["execute-api:/*/*/*"],
                    effect=iam_.Effect.DENY,
                    conditions={
                            "StringNotEquals": {
                                "aws:SourceVpce": apivpce.vpc_endpoint_id
                            }
                        },
                    principals=[iam_.AnyPrincipal()]
                ),
                iam_.PolicyStatement(
                    actions=["execute-api:Invoke"],
                    resources=["execute-api:/*/*/*"],
                    effect=iam_.Effect.ALLOW,
                    principals=[iam_.AnyPrincipal()]
                )
                ]
        ),
       
            cloud_watch_role=False,
            default_cors_preflight_options={
                "allow_origins": apigw_.Cors.ALL_ORIGINS,
                "allow_methods": apigw_.Cors.ALL_METHODS,
            },
            deploy_options=apigw_.StageOptions(
                logging_level=apigw_.MethodLoggingLevel.INFO,
                stage_name=stage_name,
                access_log_destination=apigw_.LogGroupLogDestination(access_log_group),
                access_log_format=apigw_.AccessLogFormat.clf()
            ))
        # Create a request validator for the API
        request_validator = apigw_.RequestValidator(self, "ApiRequestValidator",rest_api=api,validate_request_body=True,validate_request_parameters=True)

        # Create a health model for the health endpoint
        health_model = api.add_model("HealthModel",content_type="application/json",model_name="HealthModel",
            schema=apigw_.JsonSchema(schema=apigw_.JsonSchemaVersion.DRAFT4,title="healthCheckModel",
            type=apigw_.JsonSchemaType.OBJECT,
            properties={"status": apigw_.JsonSchema(type=apigw_.JsonSchemaType.STRING)}))

        # Add the health endpoint with validation
        health = api.root.add_resource("health")
        health.add_method("GET", request_validator=request_validator,
        request_parameters={
        'method.request.header.Content-Type': False,
        'method.request.header.Accept': False})
        return api
    
    
   # Method to create API resources
    def create_api_resources(self,querylambda,apigw):
        # Create request validator for the API Gateway endpoint
        request_model = apigw.add_model("BrRequestValidatorModel",
            content_type="application/json",
            model_name="BrRequestValidatorModel",
            description="This is the request validator model for the Bedrock API Gateway endpoint.",
            schema=apigw_.JsonSchema(
                schema=apigw_.JsonSchemaVersion.DRAFT4,
                title="postRequestValidatorModel",
                type=apigw_.JsonSchemaType.OBJECT,
                required=["question"],
                properties={
                    "question": apigw_.JsonSchema(type=apigw_.JsonSchemaType.STRING, min_length=1, max_length=500),
                }
            )
        )
        kb = apigw.root.add_resource("question")
        kb.add_method("POST",apigw_.LambdaIntegration(querylambda),api_key_required=True,request_models={"application/json": request_model})
        
    # Method to create API throttle settings
    def create_throttle_constructor(self, config: dict):
        return apigw_.ThrottleSettings(
            rate_limit=config.get("rate_limit"),
            burst_limit=config.get("burst_limit"),
        )

    # Method to create API quota settings
    def create_quota_constructor(self, config: dict):
        period = config.get("period").upper()
        if period == "DAY":
            period = apigw_.Period.DAY
        elif period == "WEEK":
            period = apigw_.Period.WEEK
        else:
            period = apigw_.Period.MONTH

        return apigw_.QuotaSettings(
            limit=config.get("limit"),
            period=period,
        )

    # Method to create API usage plan
    def create_usage_plan(
        self,api_gw,
        throttle_settings: apigw_.ThrottleSettings = None,
        quota_settings: apigw_.QuotaSettings = None,
    ):
        plan =  api_gw.add_usage_plan(
                "APIUsagePlan",
                api_stages=[
                    apigw_.UsagePlanPerApiStage(stage=api_gw.deployment_stage)
                ],
                throttle=throttle_settings,
                quota=quota_settings,
        )
        key = apigw_.ApiKey(self, "BedrockAPIKey", api_key_name=self.api_key_name,enabled=True,description="This is the API key for the Bedrock API Gateway endpoint.")
        plan.add_api_key(key)
        return plan