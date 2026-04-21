variable "name_prefix" {
  description = "Resource name prefix (e.g. pgscp-dev). Each repository is named <name_prefix>-<repo_name>."
  type        = string
}

variable "repositories" {
  description = "Short names of repositories to create. Final names are <name_prefix>-<name>."
  type        = list(string)
  default     = ["api", "worker", "investigator"]
}

variable "image_retention_count" {
  description = "Number of tagged images to keep per repo. Older tagged images expire automatically."
  type        = number
  default     = 10
}

variable "untagged_expiry_days" {
  description = "Expire untagged images after this many days."
  type        = number
  default     = 1
}

variable "image_tag_mutability" {
  description = "MUTABLE (latest tag can be re-pushed) or IMMUTABLE (every tag is fixed). MUTABLE is simpler for dev."
  type        = string
  default     = "MUTABLE"
  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}
