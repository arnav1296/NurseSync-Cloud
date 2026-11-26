# ------------------------------------------------------------------ RDS PostgreSQL

resource "random_password" "db" {
  length  = 32
  special = false # keeps the connection URL free of characters that need escaping
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier              = "${local.name}-db"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  storage_type            = "gp2"
  storage_encrypted       = true
  db_name                 = "nursesync"
  username                = "nursesync"
  password                = random_password.db.result
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  publicly_accessible     = false
  multi_az                = false
  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true
}

locals {
  database_url = "postgresql://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
}

# ------------------------------------------------------------------ Cognito

resource "aws_cognito_user_pool" "main" {
  name                     = "${local.name}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = false
  }

  # staff accounts are created by the administrator, never by self sign-up
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name            = "${local.name}-web"
  user_pool_id    = aws_cognito_user_pool.main.id
  generate_secret = false # a browser app cannot keep a secret

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 7
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_user_group" "role" {
  for_each     = toset(["nurse", "doctor", "admin"])
  name         = each.key
  user_pool_id = aws_cognito_user_pool.main.id
}

# ------------------------------------------------------------------ SNS

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

# one unfiltered inbox that sees every alert, handoff email and alarm (the demo inbox)
resource "aws_sns_topic_subscription" "demo_inbox" {
  count     = var.notification_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# ------------------------------------------------------------------ S3: attachments + reports

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "files" {
  bucket        = "${local.name}-files-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# the browser uploads straight to S3 with a presigned URL, so the bucket must allow
# that request from the app's origin
resource "aws_s3_bucket_cors_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  cors_rule {
    allowed_methods = ["PUT", "GET"]
    allowed_origins = ["https://${aws_cloudfront_distribution.main.domain_name}", "http://localhost:1420"]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

# ------------------------------------------------------------------ SSM Parameter Store
# The API instance reads /nursesync/* at boot and passes them to the container.

resource "random_password" "internal_token" {
  length  = 40
  special = false
}

locals {
  plain_params = {
    AWS_REGION           = var.region
    COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
    COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
    S3_BUCKET            = aws_s3_bucket.files.bucket
    SNS_TOPIC_ARN        = aws_sns_topic.alerts.arn
    ALLOWED_ORIGINS      = "https://${aws_cloudfront_distribution.main.domain_name},http://localhost:1420,tauri://localhost"
  }
  secret_params = merge(
    {
      DATABASE_URL       = local.database_url
      INTERNAL_API_TOKEN = random_password.internal_token.result
    },
    var.groq_api_key == "" ? {} : { GROQ_API_KEY = var.groq_api_key },
    var.sarvam_api_key == "" ? {} : { SARVAM_API_KEY = var.sarvam_api_key },
  )
}

resource "aws_ssm_parameter" "plain" {
  for_each = local.plain_params
  name     = "/${local.name}/${each.key}"
  type     = "String"
  value    = each.value
}

resource "aws_ssm_parameter" "secret" {
  for_each = nonsensitive(toset(keys(local.secret_params)))
  name     = "/${local.name}/${each.key}"
  type     = "SecureString"
  value    = local.secret_params[each.key]
}
