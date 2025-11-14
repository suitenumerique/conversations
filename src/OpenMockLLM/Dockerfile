FROM python:3.13.3-alpine

# Upgrade pip to its latest release to speed up dependencies installation
RUN python -m pip install --upgrade pip setuptools lorem-text

# Upgrade system packages to install security updates
RUN apk update && \
  apk upgrade

RUN apk add --no-cache git

# Install the package
RUN pip install git+https://github.com/etalab-ia/openmockllm.git

# Expose the default port
EXPOSE 8000

# Set default command
CMD ["openmockllm", "--host", "0.0.0.0", "--port", "8000"]
