variable "APP_VERSION" {
  default = "development"
}

variable "GIT_REVISION" {
  default = "local"
}

target "_frontend-build" {
  context    = "."
  dockerfile = "frontend/Dockerfile"
  args = {
    APP_VERSION = APP_VERSION
  }
  labels = {
    "org.opencontainers.image.revision" = GIT_REVISION
    "org.opencontainers.image.version"  = APP_VERSION
  }
}

target "frontend" {
  inherits = ["_frontend-build"]
  target   = "frontend"
  tags     = ["wanderbound-frontend:local"]
}

target "sourcemaps" {
  inherits = ["_frontend-build"]
  target   = "sourcemaps"
  tags     = ["wanderbound-sourcemaps:local"]
}

group "frontend-release" {
  targets = ["frontend", "sourcemaps"]
}
