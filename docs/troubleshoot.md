# Troubleshooting Guide

## Line Ending Issues on Windows (LF/CRLF)

### Problem Description

This project uses **LF (Line Feed: `\n`) line endings** exclusively. Windows users may encounter issues because:

- **Windows** defaults to CRLF (Carriage Return + Line Feed: `\r\n`) for line endings
- **This project** uses LF line endings for consistency across all platforms
- **Git** may automatically convert line endings, causing conflicts or build failures

### Common Symptoms

- Git shows files as modified even when no changes were made
- Error messages like "warning: LF will be replaced by CRLF"
- Build failures or linting errors due to line ending mismatches

### Solutions for Windows Users

#### Configure Git to Preserve LF (Recommended)

Configure Git to NOT convert line endings and preserve LF:

```bash
git config core.autocrlf false
git config core.eol lf
```

This tells Git to:
- Never convert line endings automatically
- Always use LF for line endings in working directory


#### Fix Existing Repository with Wrong Line Endings

If you already have CRLF line endings in your local repository, the **best approach** is to configure Git properly and clone the project again:

1. **Configure Git first**:
   ```bash
   git config --global core.autocrlf false
   git config --global core.eol lf
   ```

2. **Clone the project fresh** (recommended):
   ```bash
   # Navigate to parent directory
   cd ..
   
   # Remove current repository (backup your changes first!)
   rm -rf docs
   
   # Clone again with correct line endings
   git clone git@github.com:suitenumerique/conversations.git
   ```

**Alternative**: If you have uncommitted changes and cannot re-clone:

1. **Backup your changes**:
   ```bash
   git add .
   git commit -m "Save changes before fixing line endings"
   ```

2. **Remove all files from Git's index**:
   ```bash
   git rm --cached -r .
   ```

3. **Reset Git configuration** (if not done globally):
   ```bash
   git config core.autocrlf false
   git config core.eol lf
   ```

4. **Re-add all files** (Git will use LF line endings):
   ```bash
   git add .
   ```

5. **Commit the changes**:
   ```bash
   git commit -m "✏️(project) Fix line endings to LF"
   ```

## Minio Permission Issues on Windows

### Problem Description

On Windows, you may encounter permission-related errors when running Minio in development mode with Docker Compose. This typically happens because:

- **Windows file permissions** don't map well to Unix-style user IDs used in Docker containers
- **Docker Desktop** may have issues with user mapping when using the `DOCKER_USER` environment variable
- **Minio container** fails to start or access volumes due to permission conflicts

### Common Symptoms

- Minio container fails to start with permission denied errors
- Error messages related to file system permissions in Minio logs
- Unable to create or access buckets in the development environment
- Docker Compose showing Minio service as unhealthy or exited

### Solution for Windows Users

If you encounter Minio permission issues on Windows, you can temporarily disable user mapping for the Minio service:

1. **Open the `compose.yml` file**

2. **Comment out the user directive** in the `minio` service section:
   ```yaml
   minio:
     # user: ${DOCKER_USER:-1000}  # Comment this line on Windows if permission issues occur
     image: minio/minio
     environment:
       - MINIO_ROOT_USER=conversations
       - MINIO_ROOT_PASSWORD=password
     # ... rest of the configuration
   ```

3. **Restart the services**:
   ```bash
   make run
   ```

### Why This Works

- Commenting out the `user` directive allows the Minio container to run with its default user
- This bypasses Windows-specific permission mapping issues
- The container will have the necessary permissions to access and manage the mounted volumes

### Note

This is a **development-only workaround**. In production environments, proper user mapping and security considerations should be maintained according to your deployment requirements.

## Frontend File Watching Issues on Windows

### Problem Description

Windows users may experience issues with file watching in the frontend-development container. This typically happens because:

- **Docker on Windows** has known limitations with file change detection
- **Node.js file watchers** may not detect changes properly on Windows filesystem
- **Hot reloading** fails to trigger when files are modified

### Common Symptoms

- Changes to frontend code aren't detected automatically
- Hot module replacement doesn't work as expected
- Need to manually restart the frontend container after code changes
- Console shows no reaction when saving files

### Solution: Enable WATCHPACK_POLLING

Add the `WATCHPACK_POLLING=true` environment variable to the frontend-development service in your local environment:

1. **Modify the `compose.yml` file** by adding the environment variable to the frontend-development service:

   ```yaml
   frontend-development:
     user: "${DOCKER_USER:-1000}"
     build: 
       context: .
       dockerfile: ./src/frontend/Dockerfile
       target: conversations-dev
       args:
         API_ORIGIN: "http://localhost:8071"
     image: conversations:frontend-development
     environment:
       - WATCHPACK_POLLING=true  # Add this line for Windows users
     volumes:
       - ./src/frontend:/home/frontend
       - /home/frontend/node_modules
       - /home/frontend/apps/conversations/node_modules
     ports:
       - "3000:3000"
   ```

2. **Restart your containers**:
   ```bash
   make run
   ```

### Why This Works

- `WATCHPACK_POLLING=true` forces the file watcher to use polling instead of filesystem events
- Polling periodically checks for file changes rather than relying on OS-level file events
- This is more reliable on Windows but slightly increases CPU usage
- Changes to your frontend code should now be detected properly, enabling hot reloading

### Note

This setting is primarily needed for Windows users. Linux and macOS users typically don't need this setting as file watching works correctly by default on those platforms.