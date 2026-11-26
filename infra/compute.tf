# API: Docker image in ECR -> EC2 instances in an Auto Scaling Group -> Application Load Balancer

resource "aws_ecr_repository" "api" {
  name                 = "${local.name}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# keep the registry inside the 500 MB free tier
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 3 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${local.name}/api"
  retention_in_days = 14
}

# ------------------------------------------------------------------ IAM for the instances

resource "aws_iam_role" "app" {
  name = "${local.name}-app"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "app_ecr" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# lets you open a shell on an instance from the console (Session Manager), no SSH keys
resource "aws_iam_role_policy_attachment" "app_ssm_core" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParametersByPath", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/*"
      },
      {
        Sid      = "Attachments"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.files.arn}/*"
      },
      {
        Sid      = "Notifications"
        Effect   = "Allow"
        Action   = ["sns:Publish", "sns:Subscribe"]
        Resource = aws_sns_topic.alerts.arn
      },
      {
        Sid    = "StaffLogins"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:AdminAddUserToGroup",
          "cognito-idp:AdminDeleteUser",
        ]
        Resource = aws_cognito_user_pool.main.arn
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}

# ------------------------------------------------------------------ launch template

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_launch_template" "app" {
  name_prefix   = "${local.name}-app-"
  image_id      = data.aws_ssm_parameter.al2023.value
  instance_type = var.instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.app.arn
  }

  vpc_security_group_ids = [aws_security_group.app.id]

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    region    = var.region
    registry  = split("/", aws_ecr_repository.api.repository_url)[0]
    image     = "${aws_ecr_repository.api.repository_url}:latest"
    ssm_path  = "/${local.name}/"
    log_group = aws_cloudwatch_log_group.api.name
  }))

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${local.name}-api" }
  }
}

# ------------------------------------------------------------------ load balancer

resource "random_password" "origin_secret" {
  length  = 32
  special = false
}

resource "aws_lb" "api" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  idle_timeout       = 90 # voice transcription + AI correction can take a while
}

resource "aws_lb_target_group" "api" {
  name                 = "${local.name}-api"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 20
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# requests that didn't come through our CloudFront distribution get a 403
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}

resource "aws_lb_listener_rule" "from_cloudfront" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_secret.result]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ------------------------------------------------------------------ auto scaling

resource "aws_autoscaling_group" "api" {
  name                      = "${local.name}-api"
  min_size                  = 1
  max_size                  = var.asg_max_size
  desired_capacity          = 1
  vpc_zone_identifier       = aws_subnet.public[*].id
  target_group_arns         = [aws_lb_target_group.api.arn]
  health_check_type         = "ELB"
  health_check_grace_period = 300

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0 # one instance on the free tier: replace it in place
    }
  }

  tag {
    key                 = "Name"
    value               = "${local.name}-api"
    propagate_at_launch = true
  }

  lifecycle {
    ignore_changes = [desired_capacity] # moved by the scaling policy and schedules
  }
}

# scale out when the API is busy
resource "aws_autoscaling_policy" "cpu" {
  name                   = "${local.name}-cpu-target"
  autoscaling_group_name = aws_autoscaling_group.api.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 60
  }
}

# shift changes are predictable spikes: add capacity 15 minutes before, remove it after
resource "aws_autoscaling_schedule" "shift_start" {
  for_each               = { morning = "45 6 * * *", evening = "45 18 * * *" }
  scheduled_action_name  = "${local.name}-before-${each.key}-shift"
  autoscaling_group_name = aws_autoscaling_group.api.name
  recurrence             = each.value
  time_zone              = "Asia/Kolkata"
  min_size               = 1
  max_size               = var.asg_max_size
  desired_capacity       = var.asg_max_size
}

resource "aws_autoscaling_schedule" "shift_end" {
  for_each               = { morning = "0 8 * * *", evening = "0 20 * * *" }
  scheduled_action_name  = "${local.name}-after-${each.key}-shift"
  autoscaling_group_name = aws_autoscaling_group.api.name
  recurrence             = each.value
  time_zone              = "Asia/Kolkata"
  min_size               = 1
  max_size               = var.asg_max_size
  desired_capacity       = 1
}
