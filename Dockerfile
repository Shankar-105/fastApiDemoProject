FROM python:3.12-slim

# Install system deps for PostgreSQL drivers and client libraries
WORKDIR /code

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copying and installing Python deps
# first copy and then install so that docker doesnt reinstall everything if
# nothing has changed from the previous requirements.txt to the current requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir psycopg[binary]==3.3.4

# copying the whole code
COPY . .

# Expose port
EXPOSE 8000

# Make all startup scripts and entrypoint executable
RUN chmod +x /code/startup_dev.sh /code/startup_benchmark.sh /code/startup_prod.sh /code/docker_entrypoint.sh

# Entrypoint: conditionally choose startup script based on BENCHMARK_MODE_ENABLED config
ENTRYPOINT ["/bin/bash", "/code/docker_entrypoint.sh"]