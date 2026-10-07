# Releasing a new version

Whenever we are cooking a new release (e.g. `4.18.1`), we should follow the standard procedure described below:


1.  First, check in the Crowdin UI that the translations are done. If not done you must translate and/or review them.
2.  Create a new branch named: `release/4.18.1`.
3.  Bump the release number for the backend project, the frontend projects, and the Helm files:

    - for the backend, update the `version` line by hand in `src/backend/pyproject.toml` and run `uv lock`,
    - for the frontend, mail, and others, run `make bump-packages-version VERSION_TYPE=patch`
      (use `minor` or `major` depending on the release type),
    - for Helm, update the Docker image tag in the files located at `src/helm/env.d` for different
      environments. Only bump files pinned to a version: leave `tag: "latest"` untouched.

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
    Move the `[unreleased]` items under a new `[4.18.1]` heading, then edit the bottom of the file
    following this model:
    ```text
    [unreleased]: https://github.com/suitenumerique/conversations/compare/v4.18.1...main
    [4.18.1]: https://github.com/suitenumerique/conversations/compare/v4.18.0...v4.18.1
    ```

5.  Commit your changes, signed off and signed (`git commit --signoff -S`), with the following format:
    the 🔖 release emoji, the type of release (patch/minor/major) and the release version:

    ```text
    🔖(minor) bump release to 4.18.0
    ```

6.  Open a pull request targeting `main`.
7.  Wait for the Crowdin (langs) PR to appear (automatic), review it and merge it into the release branch.
8.  Re-sign the release branch if the Crowdin merge added unsigned commits.
9.  Wait for an approval from your peers.
10.  Merge your pull or merge request.
11. Checkout and pull changes from the `main` branch to ensure you have the latest updates.
12. Tag and push your commit:

    ```bash
    git tag v4.18.1 && git push origin tag v4.18.1
    ```

     Doing this triggers the CI and tells it to build the new Docker image versions that you 
    targeted earlier in the Helm files.
13.  Manually release your version on [GitHub](https://github.com/suitenumerique/conversations/releases) (Draft a new release, select tag, then
     click **Generate release notes**: it automatically fills the title and the release notes from the tag.)
14. Ensure the new [backend](https://hub.docker.com/r/lasuite/conversations-backend/tags) and 
    [frontend](https://hub.docker.com/r/lasuite/conversations-frontend/tags) image tags are on Docker Hub.
15. The release is now done!

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

Once the release is done and the images are on Docker Hub:

1.  On the deployment repo (private), create a branch and edit the production values file
    (`production/values.assistant.yaml.gotmpl`):

    - bump the backend image tag (`image.tag`) and the frontend image tag (`frontend.image.tag`)
      to the new version, with the `v` prefix:

      ```yaml
      image:
        repository: lasuite/conversations-backend
        pullPolicy: Always
        tag: "v4.18.1"

      ...

      frontend:
        image:
          repository: lasuite/conversations-frontend
          pullPolicy: Always
          tag: "v4.18.1"
      ```

    - if the release needs it, add or update the environment variables under `backend.envVars`
      (new settings, feature flags, ...). A secret value goes in the SOPS-encrypted
      `secrets.enc.yaml` of the environment and is referenced with a `secretKeyRef`, never in
      clear text in the values file,
    - if the release changes the LLM configuration (models, tools, web search backend, ...),
      update `configuration/llm/production.json`.

2.  Commit with the following format, and describe the notable changes in the body:

    ```text
    🔖(prod) bump version to 4.18.1
    ```

3.  Open a pull request, get it approved and merge it.
4.  In ArgoCD, open the production application:

    - click **Refresh** if the application doesn't show the new commit yet (OutOfSync),
    - click **Sync** to deploy it,
    - wait until the application is back to **Synced** and **Healthy**.

    If you add or edit a secret, the deployment may fail, especially the Django jobs (migrate,
    createsuperuser, ...). These jobs run as ArgoCD PreSync hooks, so they start before the new
    Secret is applied. To avoid this, sync in two steps:

    1. Sync the Secret only (in the Sync dialog, select just the Secret resource).
    2. Sync the rest of the app.

5.  Check the new version is live in production.

Staging follows the `main` image tag, so it doesn't need this procedure.