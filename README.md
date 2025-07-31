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



### Self-host
🚀 Conversations is easy to install on your own servers

Available methods: Helm chart, soon Nix package

In the works: Docker Compose, soon YunoHost

## Getting started 🔧

### Test it

You can test Conversations on your browser by visiting this => TBD

### Run Conversations locally

> ⚠️ The methods described below for running Conversations locally is **for testing purposes only**. 
> It is based on building Conversations using [Minio](https://min.io/) as an S3-compatible storage solution. 
> Of course you can choose any S3-compatible storage solution.

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

Conversations is built on top of [Django Rest Framework](https://www.django-rest-framework.org/), [Next.js](https://nextjs.org/), [Vercel&lsquo;s AI SDK](https://ai-sdk.dev/) and [OpenAI Agents SDK](https://github.com/openai/openai-agents-python). We thank the contributors of all these projects for their awesome work!




### Gov ❤️ open source

<p align="center">
  <img src="/docs/assets/europe_opensource.png" width="50%"/>
</p>
