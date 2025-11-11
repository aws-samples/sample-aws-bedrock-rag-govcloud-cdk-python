from opensearchpy import OpenSearch, RequestsHttpConnection
import os
import boto3
import json
import logging
import time
from requests_aws4auth import AWS4Auth
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

HOST = os.environ.get("COLLECTION_HOST")
VECTOR_INDEX_NAME = os.environ.get("VECTOR_INDEX_NAME")
VECTOR_FIELD_NAME = os.environ.get("VECTOR_FIELD_NAME")
REGION_NAME = os.environ.get("REGION_NAME")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log(message):
    logger.info(message)

def handler(event, context):
    """
    Lambda handler to create OpenSearch Index
    """
    log(f"Event: {json.dumps(event)}")

    session = boto3.Session()
    region = REGION_NAME
    service = "aoss"
    response = {}
    credentials = session.get_credentials()
    log(f"HOST: {HOST}")
    host = HOST.split("//")[1]
    try:
        auth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

        client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20,
        )
        index_name = VECTOR_INDEX_NAME

        
        if client.indices.exists(index=index_name):
                log(f"Index {index_name} already exists.")
                return {
                    "statusCode": 200,
                    "body": json.dumps("Index already exists."),
                }
        else:
            log(f"Creating index: {index_name}")

            index_body = {
                "settings": {
                    "index.knn": True,
                    "index.knn.algo_param.ef_search": 512,
                },
                "mappings": {
                    "properties": {  
                        VECTOR_FIELD_NAME: {  
                            "type": "knn_vector",
                            "dimension": 1024,
                            "method": {  
                                "space_type": "innerproduct",
                                "engine": "FAISS",
                                "name": "hnsw",
                                "parameters": {
                                    "m": 16,
                                    "ef_construction": 512,
                                },
                            },
                        },
                        "AOSS_KB_METADATA": {"type": "text", "index": False},
                        "AOSS_KB_TEXT_CHUNK": {"type": "text"},
                        "id": {"type": "text"},
                    }
                },
            }

            response = client.indices.create(index=index_name, body=index_body)

            log(f"Response: {response}")
            log("Sleeping for 1 minutes to let index create.")
            time.sleep(60) 
    except Exception as e:
        logging.error("Exception: %s" % e, exc_info=True)
    finally:
        LOG.debug(f'method=create_index, index_creation_response={response}')
    return {
        "statusCode": 200,
        "body": json.dumps("Create index lambda ran successfully."),
    }
