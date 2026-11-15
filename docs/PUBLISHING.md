# Publishing aka3 to PyPI

Package: `aka3`. Repository: `ytbryan/aka.py`.

The release workflow is manual and runs from `main`. It builds the wheel and source
archive, checks their metadata, installs the wheel, and runs the tests before uploading.
Only the publishing job has permission to request an OIDC token. No long-lived PyPI
token is stored in this repository.

## First release

1. Sign in to the intended PyPI account and enable two-factor authentication.
   Complete the recovery-code check and authenticator/security-key setup yourself.
   Keep recovery codes, setup QR codes, and authentication codes private.
2. In PyPI **Your account → Publishing**, configure a pending GitHub publisher:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `aka3` |
   | GitHub owner | `ytbryan` |
   | Repository | `aka.py` |
   | Workflow filename | `publish.yml` |
   | Environment | `pypi` |

   Registering this publisher authorizes that repository workflow/environment to
   publish future versions of `aka3`. A pending publisher does not reserve the name.
3. Push the reviewed source and `.github/workflows/publish.yml` to `main`.
4. On GitHub, open **Actions → Publish to PyPI → Run workflow**. Select `main` and
   enter the exact package version (initial release: `0.1.0`).
5. Wait for both jobs to succeed. Check the PyPI project page and install from PyPI
   in a fresh virtual environment:

   ```sh
   python3 -m venv /tmp/aka3-pypi-check
   /tmp/aka3-pypi-check/bin/python -m pip install --index-url https://pypi.org/simple aka3==0.1.0
   /tmp/aka3-pypi-check/bin/aka --version
   ```

The workflow references the GitHub environment `pypi`. GitHub creates an absent
environment when a workflow first references it; configure protection rules if
additional release approval is desired. Only repository users with the required
GitHub access should be able to edit or dispatch the publishing workflow.

## Later releases

Update both `project.version` in `pyproject.toml` and `__version__` in
`src/aka3/__init__.py`. Review, test, and push the change, then dispatch the workflow
with the new version. PyPI does not allow replacing files from an existing release.

If a version is already published, inspect it before doing anything else; do not
retry an upload with different contents under the same version. Use a new version
for corrected artifacts.

## References

- [PyPI: creating a project through Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPI: using a Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
