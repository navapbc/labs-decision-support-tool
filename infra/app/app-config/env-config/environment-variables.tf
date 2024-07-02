locals {
  # Map from environment variable name to environment variable value
  # This is a map rather than a list so that variables can be easily
  # overridden per environment using terraform's `merge` function
  default_extra_environment_variables = {
    # Example environment variables
    # WORKER_THREADS_COUNT    = 4
    # LOG_LEVEL               = "info"
    # DB_CONNECTION_POOL_SIZE = 5
  }

  # Configuration for secrets
  # List of configurations for defining environment variables that pull from SSM parameter
  # store. Configurations are of the format
  # {
  #   ENV_VAR_NAME = {
  #     manage_method     = "generated" # or "manual" for a secret that was created and stored in SSM manually
  #     secret_store_name = "/ssm/param/name"
  #   }
  # }
  secrets = {
    CHAINLIT_AUTH_SECRET = {
      manage_method     = "generated"
      secret_store_name = "/${var.app_name}-${var.environment}/CHAINLIT_AUTH_SECRET"
    }

    GLOBAL_PASSWORD = {
      manage_method     = "manual"
      secret_store_name = "/${var.app_name}-${var.environment}/GLOBAL_PASSWORD"
    }

    OPENAI_API_KEY = {
      manage_method     = "manual"
      secret_store_name = "/${var.app_name}-${var.environment}/OPENAI_API_KEY"
    }
    LITERAL_API_KEY = {
      manage_method     = "manual"
      secret_store_name = "/${var.app_name}-${var.environment}/LITERAL_API_KEY"
    }

    # Example secret that references a manually created secret
    # SECRET_SAUCE = {
    #   manage_method     = "manual"
    #   secret_store_name = "/${var.app_name}-${var.environment}/secret-sauce"
    # }
  }
}
