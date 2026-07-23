output "app_public_ip" {
  description = "Public (Elastic) IP of the app instance."
  value       = aws_eip.app.public_ip
}

output "app_url" {
  description = "Direct URL to the app (before any domain/HTTPS is added)."
  value       = "http://${aws_eip.app.public_ip}:8000"
}

output "ecr_repository_url" {
  description = "ECR repo to push the app image to."
  value       = aws_ecr_repository.app.repository_url
}

output "instance_id" {
  description = "EC2 instance id (used by CI for SSM deploys)."
  value       = aws_instance.app.id
}

output "backups_bucket" {
  description = "S3 bucket holding database backups."
  value       = aws_s3_bucket.backups.bucket
}

output "log_group" {
  description = "CloudWatch log group for container logs."
  value       = aws_cloudwatch_log_group.app.name
}
