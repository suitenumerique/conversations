# Releasing a new version

Whenever we are cooking a new release (e.g. `4.18.1`), we should follow the standard procedure described below:


1.  First, check in the Crowdin UI that the translations are done.
2.  Create a new branch named: `release/4.18.1`.
3.  Bump the release number for the backend project, the frontend projects, and the Helm files:

    - for the backend, update the version number by hand in `pyproject.toml` and run `uv lock`,
    - for the frontend, mail, and others, run `make bump-packages-version VERSION_TYPE=patch`,
    - for Helm, update the Docker image tag in the files located at `src/helm/env.d` for different` 
      environments:

      ```yaml
      image:
        repository: lasuite/conversations-backend
        pullPolicy: Always
        tag: "v4.18.1" # Replace with your new version number, without forgetting the "v" prefix
      
      ...
      
      frontend:
        image:
          repository: lasuite/conversations-frontend
          pullPolicy: Always
          tag: "v4.18.1"
      ```

      The new images don't exist _yet_: they will be created automatically later in the process.

4.  Update the project's `Changelog` following the [keepachangelog](https://keepachangelog.com/en/0.3.0/) recommendations.
    You'll have to edit the bottom of the file following this model:
    ```[unreleased]: https://github.com/suitenumerique/conversations/compare/v0.0.21...main
       [0.0.21]: https://github.com/suitenumerique/conversations/compare/v0.0.21```

5.  Commit your changes with the following format: the 🔖 release emoji, the type of release (patch/minor/major) and the release version:

    ```text
    🔖(minor) bump release to 4.18.0
    ```

6.  Open a pull request.
7.  Wait for the Crowdin (langs) PR to appear (automatic), review it and merge it into the release branch.
8.  you may have to re-sign the release branch
8.  Wait for an approval from your peers.
9.  Merge your pull or merge request.
10. Checkout and pull changes from the `main` branch to ensure you have the latest updates.
11. Tag and push your commit:

    ```bash
    git tag v4.18.1 && git push origin tag v4.18.1
    ```

     Doing this triggers the CI and tells it to build the new Docker image versions that you 
    targeted earlier in the Helm files.
12.  Manually release your version on GitHub (Draft a new release, select tag, fill the 
     title generate release notes.)
13. Ensure the new [backend](https://hub.docker.com/r/lasuite/conversations-backend/tags) and 
    [frontend](https://hub.docker.com/r/lasuite/conversations-frontend/tags) image tags are on Docker Hub.
14. The release is now done!

## Troubleshooting

### The translations need a fix after the Crowdin PR was opened

Never edit the translation files by hand: the next download would overwrite them.
Fix the strings in the Crowdin UI, then re-run the download:

1.  Go to the repository's **Actions** tab and select the **Download translations from Crowdin** workflow.
2.  Click **Run workflow** and pick your `release/4.18.1` branch as the ref (not `main`, or the
    pull request would target the wrong branch).
3.  The workflow pushes to the `i18n/update-translations` branch and opens (or updates, if it is
    still open) the "🌐(i18n) update translated strings" pull request. Review and merge it into
    the release branch as in step 7.

# Deploying

Making a new release doesn't publish it automatically in production.

Deployment is done by ArgoCD.

You need to open a PR on the deployment repo (private) and bump the 2 tags values (back and front), 
plus some env
variables if needed. 