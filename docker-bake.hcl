variable "APP_VERSION" {
  default = "dev"
}

variable "APP_IMAGE" {
  default = "wanderbound"
}

variable "SOURCEMAPS_IMAGE" {
  default = "wanderbound-sourcemaps"
}

variable "TAG" {
  default = "dev"
}

group "default" {
  targets = ["app", "sourcemaps"]
}

target "base" {
  context    = "."
  dockerfile = "Dockerfile"
  args = {
    APP_VERSION = APP_VERSION
  }
}

target "app" {
  inherits = ["base"]
  target   = "app"
  tags     = ["${APP_IMAGE}:${TAG}"]
}

target "sourcemaps" {
  inherits = ["base"]
  target   = "sourcemaps"
  tags     = ["${SOURCEMAPS_IMAGE}:${TAG}"]
}
