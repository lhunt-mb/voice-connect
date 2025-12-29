# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "voice-openai-connect"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Application = "voice-ai-gateway"
    }
  }
}
