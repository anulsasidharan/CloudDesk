variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}
variable "name_prefix" { type = string }
variable "region" { type = string }
variable "project_id" { type = string }
variable "backend_count" { type = number }
variable "image_tag" {
  type    = string
  default = "unset"
}
