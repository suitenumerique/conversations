<p align="center">
  <a href="https://github.com/suitenumerique/conversations">
    <img alt="Conversations" src="/docs/assets/banner-conversations.png" width="100%" />
  </a>
</p>
<p align="center">
  <a href="https://github.com/suitenumerique/conversations/stargazers/">
    <img src="https://img.shields.io/github/stars/suitenumerique/conversations" alt="">
  </a>
  <a href='https://github.com/suitenumerique/conversations/blob/main/CONTRIBUTING.md'><img alt='PRs Welcome' src='https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=shields'/></a>
  <img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/suitenumerique/conversations"/>
  <img alt="GitHub closed issues" src="https://img.shields.io/github/issues-closed/suitenumerique/conversations"/>
  <a href="https://github.com/suitenumerique/conversations/blob/main/LICENSE">
    <img alt="GitHub closed issues" src="https://img.shields.io/github/license/suitenumerique/conversations"/>
  </a>    
</p>


**Warning:** This project is in active development and in a very early stage. Breaking changes may occur at any time.


## Yet another AI chatbot

Conversations is an open-source AI chatbot designed to be simple, secure and privacy-friendly.

Why another AI chatbot? Because we want to be able to fully control our data and the way we interact with AI.
We want to have a very friendly end-user interface and code, and we want to be able to easily customize the
chatbot to our needs.

We leverage open-source projects such as [Vercel&lsquo;s AI SDK](https://ai-sdk.dev/) and [Pydantic AI](https://ai.pydantic.dev)
and only assemble them in a way that makes sense for us and allows us to focus on the product.

This assistant's purpose is also to be integrated into the "La Suite numérique" ecosystem of tools for public services.

Any help to improve the project is very welcome!


### Self-host
🚀 Conversations is easy to install on your own servers

Available methods: Helm chart, soon Nix package

In the works: Docker Compose, soon YunoHost

## Getting started 🔧

### Test it

You can test Conversations on your browser by visiting this => TBD

### Run Conversations locally

> ⚠️ The methods described below for running Conversations locally is **for testing purposes only**.

**Prerequisite**

Make sure you have a recent version of Docker and [Docker Compose](https://docs.docker.com/compose/install) installed on your laptop, then type:

```shellscript
$ docker -v

Docker version 20.10.2, build 2291f61

$ docker compose version

Docker Compose version v2.32.4
```

> ⚠️ You may need to run the following commands with `sudo`, but this can be avoided by adding your user to the local `docker` group.

**Project bootstrap**

The easiest way to start working on the project is to use [GNU Make](https://www.gnu.org/software/make/):

```shellscript
$ make bootstrap FLUSH_ARGS='--no-input'
```

This command builds the `app-dev` and `frontend-dev` containers, installs dependencies, performs database migrations and compiles translations. It's a good idea to use this command each time you are pulling code from the project repository to avoid dependency-related or migration-related issues.

Your Docker services should now be up and running 🎉

You can access the project by going to <http://localhost:3000>.

You will be prompted to log in. The default credentials are:

```
username: conversations
password: conversations
```

📝 Note that if you need to run them afterwards, you can use the eponymous Make rule:

```shellscript
$ make run
```

⚠️ For the frontend developer, it is often better to run the frontend in development mode locally.

To do so, install the frontend dependencies with the following command:

```shellscript
$ make frontend-development-install
```

And run the frontend locally in development mode with the following command:

```shellscript
$ make run-frontend-development
```

To start all the services, except the frontend container, you can use the following command:

```shellscript
$ make run-backend
```

**Setup a basic LLM call**

To be able to use Conversations, you need to configure at least one Large Language Model (LLM) provider.
You can do so by setting the appropriate environment variables in the `env.d/development/common` file:

```ini
AI_BASE_URL=http://host.docker.internal:12434/v1/
AI_MODEL=gemma3:4b
AI_API_KEY=XXX
```

for a local ollama, or by running a local LLM with docker-compose:

```shellscript
$ make create-compose-with-models
```

which will create a `compose.override.yml` file to start a local models `ai/smollm2`
which can be changed later by editing the `compose.override.yml` file.

You will need to call `make run` after changing the `env.d/development/common`
or `compose.override.yml` file.

You can find more information about configuring LLM providers in the [LLM Configuration](docs/llm-configuration.md) documentation.

**Adding content**

You can create a basic demo site by running this command:

```shellscript
$ make demo
```

Finally, you can check all available Make rules using this command:

```shellscript
$ make help
```

**Django admin**

You can access the Django admin site at:

<http://localhost:8071/admin>.

You first need to create a superuser account:

```shellscript
$ make superuser
```

## Documentation 📚

Additional documentation is available in the `docs/` directory:

- [LLM Configuration](docs/llm-configuration.md) - Configure Large Language Models and providers
- [Attachments](docs/attachments.md) - How to use attachments in conversations
- [Tools for Agents](docs/tools.md) - Available tools and how to add new ones
- [Environment Variables](docs/env.md) - All available environment variables
- [Installation Guide](docs/installation.md) - Deploy on a Kubernetes cluster
- [Theming](docs/theming.md) - Customize the application appearance
- [Architecture](docs/architecture.md) - Technical architecture overview

## Licence 📝

This work is released under the MIT License (see [LICENSE](https://github.com/suitenumerique/conversations/blob/main/LICENSE)).

While Conversations is a public-driven initiative, our licence choice is an invitation for private sector actors to use, sell and contribute to the project. 

## Contributing 🙌

You can help us with translations on [Crowdin](https://crowdin.com/project/lasuite-conversations).

If you intend to make pull requests, see [CONTRIBUTING](https://github.com/suitenumerique/conversations/blob/main/CONTRIBUTING.md) for guidelines.

## Directory structure:

```markdown
docs
├── bin - executable scripts or binaries that are used for various tasks, such as setup scripts, utility scripts, or custom commands.
├── crowdin - for crowdin translations, a tool or service that helps manage translations for the project.
├── docker - Dockerfiles and related configuration files used to build Docker images for the project. These images can be used for development, testing, or production environments.
├── docs - documentation for the project, including user guides, API documentation, and other helpful resources.
├── env.d/development - environment-specific configuration files for the development environment. These files might include environment variables, configuration settings, or other setup files needed for development.
├── gitlint - configuration files for `gitlint`, a tool that enforces commit message guidelines to ensure consistency and quality in commit messages.
└── src - main source code directory, containing the core application code, libraries, and modules of the project.
```

## Credits ❤️

### Stack

Conversations is built on top of [Django Rest Framework](https://www.django-rest-framework.org/), [Next.js](https://nextjs.org/), [Vercel&lsquo;s AI SDK](https://ai-sdk.dev/) and [Pydantic AI](https://ai.pydantic.dev). We thank the contributors of all these projects for their awesome work!


### Gov ❤️ open source

<p align="center">
  <img src="/docs/assets/europe_opensource.png" width="50%"/>
</p>
