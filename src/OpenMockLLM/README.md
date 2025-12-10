[OpenMockLLM](https://github.com/etalab-ia/OpenMockLLM) is a FastAPI-based mock LLM API server that simulates 
several Large Language Model API providers.

This is a simple docker image to run the server for testing and development purposes (E2E tests mainly).

It's a bit overkill to have a dedicated image for that, but it allows simple E2E stack with docker-compose since
our code is also run in Docker containers.

## Build and Run manually

```bash
docker build -t openmockllm .
docker run -p 8000:8000 openmockllm
```

## Next steps

- Add more chat completion behaviors (specific text streaming, function calling, etc.)
- Pin a specific OpenMockLLM version in the Dockerfile
