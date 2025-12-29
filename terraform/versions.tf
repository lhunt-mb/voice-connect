terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Backend configuration should be provided via backend config file or CLI
    # Example: terraform init -backend-config=backend.hcl
    # bucket         = "your-terraform-state-bucket"
    # key            = "voice-openai-connect/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "terraform-state-locking"
    # encrypt        = true
  }
}
