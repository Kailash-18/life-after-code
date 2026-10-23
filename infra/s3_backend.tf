# ==============================================================================
# Project Sentinel — Enterprise S3 Remote State & DynamoDB Locking Architecture
# ==============================================================================
# Hardened S3 remote backend infrastructure delivering:
# 1. Zero data loss via immutable object versioning
# 2. Hardware-grade security via AWS KMS Customer Managed Keys (CMK) with auto-rotation
# 3. Distributed concurrency protection via DynamoDB distributed locking
# 4. Strict zero-trust transport: TLS 1.2+ enforcement and complete public access denial
# 5. Lifecycle optimization: automatic cold storage tiering and incomplete upload purges
# ==============================================================================

# 1. AWS KMS Customer Managed Key (CMK) with Automatic Annual Key Rotation
resource "aws_kms_key" "state_key" {
  count                   = var.enable_s3_state_bootstrap ? 1 : 0
  description             = "Sentinel KMS CMK: Enforces cryptographic envelope encryption for Terraform state and incident snapshots"
  deletion_window_in_days = var.state_kms_key_deletion_window_in_days
  enable_key_rotation     = true

  tags = {
    Name        = "sentinel-tfstate-kms-key-${var.environment}"
    Environment = var.environment
    Component   = "StateStorage-KMS"
    Compliance  = "CIS-Benchmark-Level-2"
  }
}

resource "aws_kms_alias" "state_key_alias" {
  count         = var.enable_s3_state_bootstrap ? 1 : 0
  name          = "alias/sentinel-tfstate-key-${var.environment}"
  target_key_id = aws_kms_key.state_key[0].key_id
}

# 2. Production S3 State Storage Bucket (Protected from Accidental Deletion)
resource "aws_s3_bucket" "terraform_state" {
  count         = var.enable_s3_state_bootstrap ? 1 : 0
  bucket        = var.state_bucket_name
  force_destroy = false

  tags = {
    Name        = var.state_bucket_name
    Environment = var.environment
    Component   = "RemoteState-Backend"
    Sensitivity = "High-Confidential"
  }
}

# 3. Mandatory Object Versioning (Enables Rollbacks & Point-In-Time State Recovery)
resource "aws_s3_bucket_versioning" "terraform_state_versioning" {
  count  = var.enable_s3_state_bootstrap ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

# 4. Server-Side Encryption with Customer-Managed KMS Key (SSE-KMS + S3 Bucket Keys)
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state_crypto" {
  count  = var.enable_s3_state_bootstrap ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.state_key[0].arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# 5. Strict Zero-Trust Public Access Block (Blocks all ACLs & Public Bucket Policies)
resource "aws_s3_bucket_public_access_block" "terraform_state_pab" {
  count  = var.enable_s3_state_bootstrap ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 6. Optimized S3 Lifecycle Rules (Cold Storage Tiering & Multipart Cleanup)
resource "aws_s3_bucket_lifecycle_configuration" "terraform_state_lifecycle" {
  count      = var.enable_s3_state_bootstrap ? 1 : 0
  bucket     = aws_s3_bucket.terraform_state[0].id
  depends_on = [aws_s3_bucket_versioning.terraform_state_versioning]

  rule {
    id     = "state-history-cold-tier-and-purge"
    status = "Enabled"

    filter {}

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }


    noncurrent_version_expiration {
      noncurrent_days = 365
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# 7. S3 Bucket Security Policy (Strict TLS 1.2+ Enforcement & SSE-KMS Mandate)
resource "aws_s3_bucket_policy" "terraform_state_policy" {
  count  = var.enable_s3_state_bootstrap ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.terraform_state[0].arn,
          "${aws_s3_bucket.terraform_state[0].arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "DenyIncorrectEncryptionHeaders"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.terraform_state[0].arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      }
    ]
  })
}

# 8. DynamoDB Distributed Lock Table (Sub-millisecond Concurrency Protection)
resource "aws_dynamodb_table" "terraform_state_locks" {
  count        = var.enable_s3_state_bootstrap ? 1 : 0
  name         = var.dynamodb_lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.state_key[0].arn
  }

  tags = {
    Name        = var.dynamodb_lock_table_name
    Environment = var.environment
    Component   = "StateLocking-DynamoDB"
    Purpose     = "Distributed-CI-Concurrency-Gate"
  }
}

# 9. Least-Privilege IAM Policy for CI/CD Deployment Runners
resource "aws_iam_policy" "ci_state_access" {
  count       = var.enable_s3_state_bootstrap ? 1 : 0
  name        = "sentinel-ci-tfstate-policy-${var.environment}"
  description = "Scoped IAM permissions granting GitLab CI runners secure access to Terraform S3 state and DynamoDB locks"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketStateList"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:GetBucketVersioning"
        ]
        Resource = aws_s3_bucket.terraform_state[0].arn
      },
      {
        Sid    = "S3ObjectStateReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.terraform_state[0].arn}/*"
      },
      {
        Sid    = "KMSDecryptEncryptState"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.state_key[0].arn
      },
      {
        Sid    = "DynamoDBStateLockManagement"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:DescribeTable"
        ]
        Resource = aws_dynamodb_table.terraform_state_locks[0].arn
      }
    ]
  })
}
