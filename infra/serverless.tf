# Shift-change job: EventBridge Scheduler -> Lambda -> API /api/internal/shift-change

data "archive_file" "shift_change" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/shift_change"
  output_path = "${path.module}/build/shift_change.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-shift-change"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "shift_change" {
  name              = "/aws/lambda/${local.name}-shift-change"
  retention_in_days = 14
}

resource "aws_lambda_function" "shift_change" {
  function_name    = "${local.name}-shift-change"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.shift_change.output_path
  source_code_hash = data.archive_file.shift_change.output_base64sha256
  timeout          = 60
  memory_size      = 128

  environment {
    variables = {
      API_URL            = "https://${aws_cloudfront_distribution.main.domain_name}"
      INTERNAL_API_TOKEN = random_password.internal_token.result
    }
  }

  depends_on = [aws_cloudwatch_log_group.shift_change]
}

resource "aws_iam_role" "scheduler" {
  name = "${local.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-shift-change"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.shift_change.arn
    }]
  })
}

resource "aws_scheduler_schedule" "shift_change" {
  name                         = "${local.name}-shift-change"
  schedule_expression          = "cron(0 ${var.shift_change_times} * * ? *)"
  schedule_expression_timezone = "Asia/Kolkata"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.shift_change.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
