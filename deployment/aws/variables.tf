variable "environment" {
  type        = string
  description = "dev, staging or prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}
variable "name_prefix" { type = string }
variable "region" { type = string }
variable "backend_count" { type = number }
variable "image_tag" {
  type        = string
  description = "Git SHA of the tested build"
  default     = "unset"
}
