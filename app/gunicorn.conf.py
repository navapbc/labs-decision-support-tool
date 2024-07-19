"""
Configuration file for the Gunicorn server used to run the application in production environments.

Attributes:
    bind(str): The socket to bind. Formatted as '0.0.0.0:$PORT'.
    threads(int): The number of threads per worker for handling requests.

For more information, see https://docs.gunicorn.org/en/stable/configure.html
"""

from src import shared

app_config = shared.get_app_config()

# Since the `-b 0.0.0.0:8000` argument is used when running in the Docker environment,
# this bind variable is only used when not using Docker
bind = app_config.host + ':' + str(app_config.port)
workers = 1
threads = 4
