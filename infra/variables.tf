variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name, used to name/tag resources."
  type        = string
  default     = "readmark"
}

variable "instance_type" {
  description = "EC2 instance type (t3.micro is free-tier eligible)."
  type        = string
  default     = "t3.micro"
}

variable "ssh_ingress_cidr" {
  description = "CIDR allowed to SSH (port 22). Restrict to your IP for safety."
  type        = string
  default     = "0.0.0.0/0"
}

variable "key_name" {
  description = "Optional existing EC2 key pair name for SSH. Empty = no SSH key (use SSM)."
  type        = string
  default     = ""
}

variable "app_secret_key" {
  description = "JWT signing secret for the app (SecureString in SSM)."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for AI summarization. Empty disables the feature."
  type        = string
  sensitive   = true
  default     = ""
}

variable "allowed_origins" {
  description = "CORS allowed origins for the API."
  type        = string
  default     = "*"
}

variable "ai_model" {
  description = "Claude model id for summarization."
  type        = string
  default     = "claude-haiku-4-5-20251001"
}

variable "domain" {
  description = "Optional domain for HTTPS via Caddy (e.g. aws.getreadmark.com). Empty = HTTP only on :8000."
  type        = string
  default     = ""
}
