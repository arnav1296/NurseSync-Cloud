variable "region" {
  description = "AWS region (Mumbai keeps latency low for Indian wards)."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Prefix for every resource name."
  type        = string
  default     = "nursesync"
}

variable "notification_email" {
  description = "Inbox that receives every SNS alert/handoff email and CloudWatch alarm (confirm the subscription email once). Leave empty to skip."
  type        = string
  default     = ""
}

variable "budget_email" {
  description = "Where AWS Budgets warns you if anything starts to cost money."
  type        = string
}

variable "groq_api_key" {
  description = "Groq key for English transcription and AI summaries (optional)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "sarvam_api_key" {
  description = "Sarvam key for Hindi transcription (optional)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "instance_type" {
  description = "EC2 instance type for the API (free-tier eligible)."
  type        = string
  default     = "t3.micro"
}

variable "db_instance_class" {
  description = "RDS instance class (free-tier eligible)."
  type        = string
  default     = "db.t3.micro"
}

variable "asg_max_size" {
  description = "Most API instances the Auto Scaling Group may run."
  type        = number
  default     = 2
}

variable "shift_change_times" {
  description = "Shift changes in Asia/Kolkata time, as cron hour lists for the scheduler."
  type        = string
  default     = "7,19"
}
