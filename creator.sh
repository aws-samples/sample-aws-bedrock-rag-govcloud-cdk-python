#!/usr/bin/bash 
Green='\033[0;32m'
Red='\033[0;31m'
NC='\033[0m'

echo ' '
echo '*************************************************************'
echo ' '
printf "$Green Press Enter to proceed with deployment else ctrl+c to cancel $NC "
read -p " "

# echo "--- Bootstrapping CDK on account in region $deployment_region ---"
# ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
# cdk bootstrap aws://$ACCOUNT_ID/$deployment_region 

echo "--- pip install requirements ---"
python3 -m pip install -r requirements-dev.txt

echo "--- CDK synthesize ---"
cdk synth lambdalayerstack
cdk synth aossstack
cdk synth knowledgebasestack
cdk synth apistack

echo "--- CDK deploy ---"
cdk deploy lambdalayerstack --require-approval never
cdk deploy aossstack --require-approval never
cdk deploy knowledgebasestack --require-approval never
cdk deploy apistack --require-approval never
echo "Deployment Complete"
