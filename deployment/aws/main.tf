# AWS scaffold: ECR + ECS Fargate + ALB + Secrets Manager + CloudWatch.
# Status: written, NOT applied, NOT validated against a real account. Needs cloud credentials.
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {} # configured with -backend-config=backend.hcl (git-ignored)
}

provider "aws" {
  region = var.region
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.name_prefix}-backend"
  image_tag_mutability = "IMMUTABLE" # tags are git SHAs
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.name_prefix}-frontend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "${var.name_prefix}/jwt-secret"
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/clouddesk/${var.environment}"
  retention_in_days = var.environment == "prod" ? 90 : 14
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
}

# Service, task definitions, ALB, networking and Redis are the next increment (see docs).
