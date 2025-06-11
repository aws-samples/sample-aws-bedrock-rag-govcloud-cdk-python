import os
from boto3 import client
import json

bedrock_agent_runtime_client = client("bedrock-agent-runtime", region_name=os.environ["AWS_REGION"])

def return_message(statuscode,message):
     return {
            "isBase64Encoded": False,
            "statusCode": statuscode,
            "headers": {"Content-Type": "application/json"},
            "body": message
        }
     
def handler(event, context):
    print(event)
    request_context = event.get('requestContext', {})
    if request_context.get('http', {}).get('method') == 'OPTIONS':
        return return_message(200,'OK')
    if request_context.get('resourcePath') == '/health':
        return return_message(200,'Looks Good!')
    try:
    # parse the input for the question
        question = json.loads(event["body"])["question"]
        response = retrieve_and_generate(question)
    
        response_body = {"answer": response['output']['text']}
        return return_message(200,json.dumps(response_body))
    except Exception as e:
        return return_message(500, json.dumps({"error": str(e)}))
    
#  { "body": "{\"question\":\"What are the best practices with building a RAG sulution using Amazon Bedrock?\"}" }
def retrieve_and_generate(input):
        return bedrock_agent_runtime_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': os.environ["KNOWLEDGE_BASE_ID"],
                    'modelArn': os.environ["MODEL_ARN"]
                }
            }
        )

    