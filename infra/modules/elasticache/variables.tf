variable "environment" {
  type = string
}

variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "num_cache_nodes" {
  type    = number
  default = 1
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}
