data "aws_caller_identity" "current" {}

# Use the account's default VPC + a subnet in it (keeps the setup simple —
# no custom VPC/NAT/route tables to manage).
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI.
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# ── Container registry ────────────────────────────────────────────────────
resource "aws_ecr_repository" "app" {
  name                 = var.project
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep only the 10 most recent images (cost hygiene).
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# ── Secrets (SSM Parameter Store, SecureString) ───────────────────────────
resource "aws_ssm_parameter" "secret_key" {
  name  = "/${var.project}/SECRET_KEY"
  type  = "SecureString"
  value = var.app_secret_key
}

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/${var.project}/ANTHROPIC_API_KEY"
  type  = "SecureString"
  value = var.anthropic_api_key != "" ? var.anthropic_api_key : "unset"
}

# ── S3 bucket for database backups ────────────────────────────────────────
resource "aws_s3_bucket" "backups" {
  bucket = "${var.project}-backups-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
  }
}

# ── CloudWatch log group for container logs ───────────────────────────────
resource "aws_cloudwatch_log_group" "app" {
  name              = "/${var.project}/app"
  retention_in_days = 14
}

# ── IAM: instance role (ECR pull, SSM params, S3 backups, logs, SSM agent) ─
resource "aws_iam_role" "instance" {
  name = "${var.project}-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# Enables remote management + CI-driven deploys via SSM (no SSH needed).
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "app" {
  name = "${var.project}-app"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrPull"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = "*"
      },
      {
        Sid      = "ReadSecrets"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [aws_ssm_parameter.secret_key.arn, aws_ssm_parameter.anthropic_api_key.arn]
      },
      {
        Sid      = "BackupsBucket"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.backups.arn, "${aws_s3_bucket.backups.arn}/*"]
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.app.arn}:*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project}-instance"
  role = aws_iam_role.instance.name
}

# ── Security group ────────────────────────────────────────────────────────
resource "aws_security_group" "app" {
  name        = "${var.project}-app"
  description = "ReadMark app: HTTP/HTTPS in, SSH from allowed CIDR"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "App (direct, for testing)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_ingress_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── EC2 instance ──────────────────────────────────────────────────────────
resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  key_name               = var.key_name != "" ? var.key_name : null

  user_data = templatefile("${path.module}/user-data.sh", {
    project         = var.project
    region          = var.aws_region
    ecr_repo_url    = aws_ecr_repository.app.repository_url
    log_group       = aws_cloudwatch_log_group.app.name
    backups_bucket  = aws_s3_bucket.backups.bucket
    allowed_origins = var.allowed_origins
    ai_model        = var.ai_model
    domain          = var.domain
  })

  # user-data only runs on first boot; don't replace a running instance when it changes.
  user_data_replace_on_change = false

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  root_block_device {
    volume_size = 30
    encrypted   = true
  }

  tags = { Name = "${var.project}-app" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-app" }
}

# ── CloudWatch alarms ─────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "status_check" {
  alarm_name          = "${var.project}-status-check-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "EC2 instance status check failing"
  dimensions          = { InstanceId = aws_instance.app.id }
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "CPU above 80% for 15 minutes"
  dimensions          = { InstanceId = aws_instance.app.id }
}

# ── CloudWatch dashboard ──────────────────────────────────────────────────
resource "aws_cloudwatch_dashboard" "app" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type       = "text", x = 0, y = 0, width = 24, height = 2,
        properties = { markdown = "# ReadMark — ${var.domain != "" ? var.domain : aws_eip.app.public_ip}\nEC2 `${aws_instance.app.id}` · region `${var.aws_region}`" }
      },
      {
        type = "metric", x = 0, y = 2, width = 12, height = 6,
        properties = {
          title   = "CPU Utilization (%)",
          region  = var.aws_region,
          view    = "timeSeries", stat = "Average", period = 300,
          metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", aws_instance.app.id]],
          yAxis   = { left = { min = 0, max = 100 } }
        }
      },
      {
        type = "metric", x = 12, y = 2, width = 12, height = 6,
        properties = {
          title  = "Status Checks (failed)",
          region = var.aws_region,
          view   = "timeSeries", stat = "Maximum", period = 60,
          metrics = [
            ["AWS/EC2", "StatusCheckFailed", "InstanceId", aws_instance.app.id],
            ["AWS/EC2", "StatusCheckFailed_Instance", "InstanceId", aws_instance.app.id],
            ["AWS/EC2", "StatusCheckFailed_System", "InstanceId", aws_instance.app.id]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 8, width = 12, height = 6,
        properties = {
          title  = "Network (bytes)",
          region = var.aws_region,
          view   = "timeSeries", stat = "Average", period = 300,
          metrics = [
            ["AWS/EC2", "NetworkIn", "InstanceId", aws_instance.app.id],
            ["AWS/EC2", "NetworkOut", "InstanceId", aws_instance.app.id]
          ]
        }
      },
      {
        type = "log", x = 12, y = 8, width = 12, height = 6,
        properties = {
          title  = "Recent errors (app logs)",
          region = var.aws_region,
          view   = "table",
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, level, msg | filter level = \"ERROR\" | sort @timestamp desc | limit 20"
        }
      }
    ]
  })
}
