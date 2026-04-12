# Local Development

## Debug Mode

Run the Django backend with [debugpy](https://github.com/microsoft/debugpy) so you can attach a
  remote debugger from your IDE.

> **Note:** With `--wait-for-client`, the server **will not start** until a debugger is
attached. Attach your IDE before expecting the app to respond.

### 1. Create `compose.override.yml` at the project root

```yaml
name: conversations

services:
  app-dev:
    ports:
      - "8071:8000"  # App accessible at http://localhost:8071
      - "5678:5678"  # Debugger port
    command: >
      python -m debugpy --listen 0.0.0.0:5678 --wait-for-client
      manage.py runserver 0.0.0.0:8000 --nothreading --noreload
```

### 2. Start the stack

```shell
make run
```

The server will block until a debugger connects on port 5678.

### 3. Attach your debugger

#### VS Code

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Django Docker",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/src/backend",
          "remoteRoot": "/app"
        }
      ]
    }
  ]
}
```

Then run the **Python: Django Docker** launch configuration (`F5`).

#### PyCharm

> **Note:** debugpy support and Attach to DAP are available since PyCharm 2026.1.

1. Go to **Settings > Python > Debugger** and set **Debugger mode** to `debugpy`
2. Go to **Run > Edit Configurations...**
3. Click **+** and select **Attach to DAP**
4. Configure the following:
   - **Remote address**: `localhost:5678`
   - **Local project path**: `<project root>/src/backend`
   - **Remote project path**: `/app`
5. Click **OK**, then start the debug configuration (**Debug** button or `Shift+F9`)

### Debug controls

- `F8` - Step Over
- `F7` - Step Into
- `Shift+F8` - Step Out
- `F9` - Resume