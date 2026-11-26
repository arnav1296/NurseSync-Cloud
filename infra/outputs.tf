output "app_url" {
  description = "Open this in a browser."
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "region" {
  value = var.region
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "files_bucket" {
  value = aws_s3_bucket.files.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "asg_name" {
  value = aws_autoscaling_group.api.name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "shift_change_lambda" {
  value = aws_lambda_function.shift_change.function_name
}

output "internal_api_token" {
  description = "Needed once, to seed the demo data."
  value       = random_password.internal_token.result
  sensitive   = true
}
