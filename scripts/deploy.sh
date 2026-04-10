#!/bin/bash
set -euo pipefail

# Snugd deployment helper
# Usage: ./scripts/deploy.sh <command> [environment]

COMMAND=${1:-help}
ENV=${2:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPO="snugd-backend"

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
  echo "  scrape <env> [city]  Trigger on-demand scrape (all markets or specific city)"
  echo "  tf-plan <env>       Run terraform plan for environment"
  echo "  tf-apply <env>      Run terraform apply for environment"
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
        --cluster snugd-${ENV} \
        --service ${SERVICE} \
        --force-new-deployment \
        --no-cli-pager
      echo "Deployed: ${SERVICE}"
    done
    echo "Waiting for API stability..."
    aws ecs wait services-stable --cluster snugd-${ENV} --services api
    echo "Deploy complete."
    ;;

  migrate)
    echo "Running migrations on ${ENV}..."
    TASK_ARN=$(aws ecs run-task \
      --cluster snugd-${ENV} \
      --task-definition snugd-${ENV}-api \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=snugd-${ENV}-private-*" --query 'Subnets[*].SubnetId' --output text | tr '\t' ','),assignPublicIp=DISABLED}" \
      --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
      --query 'tasks[0].taskArn' \
      --output text)
    echo "Migration task: ${TASK_ARN}"
    aws ecs wait tasks-stopped --cluster snugd-${ENV} --tasks ${TASK_ARN}
    echo "Migrations complete."
    ;;

  status)
    echo "ECS services in snugd-${ENV}:"
    aws ecs describe-services \
      --cluster snugd-${ENV} \
      --services api worker beat \
      --query 'services[].{name:serviceName,status:status,desired:desiredCount,running:runningCount,pending:pendingCount}' \
      --output table
    ;;

  logs)
    echo "Tailing logs for snugd-${ENV}/api..."
    aws logs tail /ecs/snugd-${ENV}/api --follow --since 5m
    ;;

  scrape)
    CITY=${3:-}
    if [ -n "$CITY" ]; then
      echo "Triggering scrape for '${CITY}' on ${ENV}..."
      OVERRIDE_CMD="from app.tasks.scrape_tasks import scrape_city_task; scrape_city_task.delay('${CITY}')"
    else
      echo "Triggering full scrape dispatch on ${ENV}..."
      OVERRIDE_CMD="from app.tasks.dispatcher import dispatch_scrapes; dispatch_scrapes()"
    fi
    SUBNETS=$(aws ec2 describe-subnets \
      --filters "Name=tag:Name,Values=snugd-${ENV}-private-*" \
      --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')
    TASK_ARN=$(aws ecs run-task \
      --cluster snugd-${ENV} \
      --task-definition snugd-${ENV}-worker \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=${SUBNETS},assignPublicIp=DISABLED}" \
      --overrides "{\"containerOverrides\":[{\"name\":\"worker\",\"command\":[\"python\",\"-c\",\"${OVERRIDE_CMD}\"]}]}" \
      --query 'tasks[0].taskArn' \
      --output text)
    echo "Scrape task: ${TASK_ARN}"
    echo "Monitor logs: ./scripts/deploy.sh logs ${ENV}"
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
