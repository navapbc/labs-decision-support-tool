module "dev_config" {
  source                          = "./env-config"
  project_name                    = local.project_name
  app_name                        = local.app_name
  default_region                  = module.project_config.default_region
  environment                     = "dev"
  account_name                    = "dev"
  network_name                    = "dev"
  domain_name                     = "decision-support-tool-dev.navateam.com"
  enable_https                    = true
  has_database                    = true
  has_incident_management_service = local.has_incident_management_service
  service_cpu                     = 2048
  service_memory                  = 8192

  # Enables ECS Exec access for debugging or jump access.
  # See https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html
  # Defaults to `false`. Uncomment the next line to enable.
  enable_command_execution = true
}
