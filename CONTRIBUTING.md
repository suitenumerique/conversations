# Contributing to the Project

Thank you for taking the time to contribute! Please follow these guidelines to ensure a smooth and productive workflow. 🚀🚀🚀

To get started with the project, please refer to the [README.md](https://github.com/suitenumerique/conversations/blob/main/README.md) for detailed instructions on how to run Conversations locally.

Contributors are required to sign off their commits with `git commit --signoff`: this confirms that they have read and accepted the [Developer's Certificate of Origin 1.1](https://developercertificate.org/). For security reasons we also require [signing your commits with your SSH or GPG key](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) with `git commit -S`.

Please also check out our [dev handbook](https://suitenumerique.gitbook.io/handbook) to learn our best practices.

## Help us with translations

You can help us with translations on [Crowdin](https://crowdin.com/project/lasuite-conversations).
Your language is not there? Request it on our Crowdin page 😊 or ping us on [Matrix](https://matrix.to/#/#docs-official:matrix.org) and let us know if you can help with translations and/or proofreading.

## Creating an Issue

When creating an issue, please provide the following details:

1.  **Title**: A concise and descriptive title for the issue.
2.  **Description**: A detailed explanation of the issue, including relevant context or screenshots if applicable.
3.  **Steps to Reproduce**: If the issue is a bug, include the steps needed to reproduce the problem.
4.  **Expected vs. Actual Behavior**: Describe what you expected to happen and what actually happened.
5.  **Labels**: Add appropriate labels to categorize the issue (e.g., bug, feature request, documentation).

## Selecting an issue

We use a [GitHub Project](https://github.com/orgs/numerique-gouv/projects/13) in order to prioritize our workload. 

Please check in priority the issues that are in the **todo** column and have a higher priority (P0 -> P2). 

## Commit Message Format

All commit messages must adhere to the following format:

`<gitmoji>(type) title description`

*   <**gitmoji**>: Use a gitmoji to represent the purpose of the commit. For example, ✨ for adding a new feature or 🔥 for removing something, see the list [here](https://gitmoji.dev/).
*   **(type)**: Describe the type of change. Common types include `backend`, `frontend`, `CI`, `docker` etc...
*   **title**: A short, descriptive title for the change (*)
*   **blank line after the commit title
*   **description**: Include additional details on why you made the changes (**).
    
    (*) ⚠️ **Make sure you add no space between the emoji and the (type) but add a space after the closing parenthesis of the type and use no caps!**
    (**) ⚠️ **Commit description message is mandatory and shouldn't be too long**

### Example Commit Message

```
✨(frontend) add user authentication logic 

Implemented login and signup features, and integrated OAuth2 for social login.
```

## Changelog Update

Please add a line to the changelog describing your development. The changelog entry should include a brief summary of the changes, this helps in tracking changes effectively and keeping everyone informed. We usually include the title of the pull request, followed by the pull request ID to finish the log entry. The changelog line should be less than 80 characters in total.

### Example Changelog Message
```
## [Unreleased]

## Added

- ✨(frontend) add AI to the project #321
```

## Pull Request Policy

We welcome contributions, but to keep the project focused and maintainable, we review pull requests according to the following guidelines:

- **Bug fixes**: Always welcome. Please describe the issue, how to reproduce it, and how your change fixes it. Link to an existing issue if possible.
- **Security fixes**: You must read and comply with our [security policy](SECURITY.md). Report vulnerabilities privately as described there, not through a public issue or pull request.
- **Deployment and tooling improvements**: Contributions that improve build, CI/CD, packaging, or deployment are welcome.
- **Unsolicited feature PRs**: New features will be declined unless they match an existing issue or have been discussed and agreed upon with the maintainers beforehand.

Want to propose a new feature? Open an issue or start a discussion first. This allows us to check that the idea matches the project's direction before you put time and effort into the implementation.

## Use of AI / LLM Tools

You may use AI assistants (ChatGPT, Claude and others) when contributing, but you remain fully responsible for what you commit:

- **Understand your code.** You must be able to explain and defend every change in your PR. ("Claude wrote it" is not an answer.)
- **Test it.** AI-generated code often looks right but isn't. Make sure your changes build, pass the tests, and actually fix the problem.
- **Keep it focused.** Avoid large, sweeping, or speculative changes produced by an LLM.
- **Be concise.** Write PR descriptions and issue reports in your own words. Long AI-generated summaries make review harder, not easier.

Low-effort, unreviewed AI-generated PRs or issues will be closed.

## Pull Requests

It is nice to add information about the purpose of the pull request to help reviewers understand the context and intent of the changes. If you can, add some pictures or a small video to show the changes.

### Don't forget to: 
- signoff your commits
- sign your commits with your key (SSH, GPG etc.)
- check your commits (see warnings above)
- check the linting: `make lint && make frontend-lint`
- check the tests: `make test`
- add a changelog entry

Once all the required tests have passed, you can request a review from the project maintainers.

## Code Style

Please maintain consistency in code style. Run any linting tools available to make sure the code is clean and follows the project's conventions.

## Tests

Make sure that all new features or fixes have corresponding tests. Run the test suite before pushing your changes to ensure that nothing is broken.

## Asking for Help

If you need any help while contributing, feel free to open a discussion or ask for guidance in the issue tracker. We are more than happy to assist!

Thank you for your contributions! 👍
