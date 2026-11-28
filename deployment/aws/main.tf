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

data "aws_caller_identity" "current" {}

# One customer-managed key for ECR, Secrets Manager and CloudWatch Logs.
resource "aws_kms_key" "main" {
  description         = "${var.name_prefix} ${var.environment} encryption key"
  enable_key_rotation = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.region}.amazonaws.com" }
        Action    = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
        Resource  = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/clouddesk/*"
          }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.name_prefix}-${var.environment}"
  target_key_id = aws_kms_key.main.key_id
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.name_prefix}-backend"
  image_tag_mutability = "IMMUTABLE" # tags are git SHAs
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${var.name_prefix}-frontend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_secretsmanager_secret" "jwt" {
  # checkov:skip=CKV2_AWS_57: JWT signing secret is rotated by a planned deploy (invalidates sessions); an automatic rotation Lambda is the next increment.
  name       = "${var.name_prefix}/jwt-secret"
  kms_key_id = aws_kms_key.main.arn
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/clouddesk/${var.environment}"
  retention_in_days = 365 # CKV_AWS_338 requires >= 1 year
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Service, task definitions, ALB, networking and Redis are the next increment (see docs).
