#!/bin/bash
set -euo pipefail

# HomeScout deployment helper
# Usage: ./scripts/deploy.sh <command> [environment]

COMMAND=${1:-help}
ENV=${2:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPO="homescout-backend"

usage() {
  echo "Usage: ./scripts/deploy.sh <command> [environment]"
  echo ""
  echo "Commands:"
  echo "  build          Build Docker image locally"
  echo "  push <env>     Push image to ECR for environment"
  echo "  deploy <env>   Deploy to ECS environment"
  echo "  migrate <env>  Run Alembic migrations on environment"
  echo "  status <env>   Check ECS service status"
  echo "  logs <env>     Tail CloudWatch logs for API service"
  echo "  tf-plan <env>  Run terraform plan for environment"
  echo "  tf-apply <env> Run terraform apply for environment"
  echo ""
  echo "Environments: dev, qa, prod"
}

get_ecr_url() {
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  echo "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
}

case "$COMMAND" in
  build)
    echo "Building Docker image..."
    docker build -t ${ECR_REPO}:local ./backend
    echo "Build complete: ${ECR_REPO}:local"
    ;;

  push)
    ECR_URL=$(get_ecr_url)
    SHA=$(git rev-parse --short HEAD)
    TAG="${ENV}-${SHA}"
    echo "Pushing ${ECR_URL}:${TAG}..."
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URL%%/*}
    docker tag ${ECR_REPO}:local ${ECR_URL}:${TAG}
    docker push ${ECR_URL}:${TAG}
    echo "Pushed: ${ECR_URL}:${TAG}"
    ;;

  deploy)
    echo "Deploying to ${ENV}..."
    for SERVICE in api worker beat; do
      aws ecs update-service \
        --cluster homescout-${ENV} \
        --service ${SERVICE} \
        --force-new-deployment \
        --no-cli-pager
      echo "Deployed: ${SERVICE}"
    done
    echo "Waiting for API stability..."
    aws ecs wait services-stable --cluster homescout-${ENV} --services api
    echo "Deploy complete."
    ;;

  migrate)
    echo "Running migrations on ${ENV}..."
    TASK_ARN=$(aws ecs run-task \
      --cluster homescout-${ENV} \
      --task-definition homescout-${ENV}-api \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=homescout-${ENV}-private-*" --query 'Subnets[*].SubnetId' --output text | tr '\t' ','),assignPublicIp=DISABLED}" \
      --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
      --query 'tasks[0].taskArn' \
      --output text)
    echo "Migration task: ${TASK_ARN}"
    aws ecs wait tasks-stopped --cluster homescout-${ENV} --tasks ${TASK_ARN}
    echo "Migrations complete."
    ;;

  status)
    echo "ECS services in homescout-${ENV}:"
    aws ecs describe-services \
      --cluster homescout-${ENV} \
      --services api worker beat \
      --query 'services[].{name:serviceName,status:status,desired:desiredCount,running:runningCount,pending:pendingCount}' \
      --output table
    ;;

  logs)
    echo "Tailing logs for homescout-${ENV}/api..."
    aws logs tail /ecs/homescout-${ENV}/api --follow --since 5m
    ;;

  tf-plan)
    cd infra
    terraform init -backend-config="key=infra/${ENV}/terraform.tfstate"
    terraform plan -var-file=environments/${ENV}.tfvars
    ;;

  tf-apply)
    cd infra
    terraform init -backend-config="key=infra/${ENV}/terraform.tfstate"
    terraform apply -var-file=environments/${ENV}.tfvars
    ;;

  help|*)
    usage
    ;;
esac
