# Making a release

1. Bump `version` in `addon.xml` (for example `1.0.1`) and commit.
2. Tag and push:
   ```
   git tag v1.0.1
   git push origin main v1.0.1
   ```

The Release workflow (`.github/workflows/release.yml`) then:

- builds `service.moodycam.zip` (with the `service.moodycam/` folder Kodi
  expects) and publishes it as a GitHub release, which is where the README's
  download link points;
- rebuilds the Kodi repository site at https://moodyjim.github.io/moodycam/
  (`addons.xml`, its checksum, the zips and folder listings), so Kodi boxes
  using the repository pick up the new version.

The tag must match the version in `addon.xml`, or the build stops. To try the
site build locally: `python .github/build_site.py` (output in `_site/`).

The repository add-on lives in `repository.moodycam/`. Only bump its version
if you change its `addon.xml`.

Pushing to `main` without a tag (for example a README change) doesn't build
anything.

## One-time GitHub settings (already done)

- Settings → Pages → Source: **GitHub Actions**.
- Settings → Environments → github-pages → Deployment branches and tags:
  allow tag pattern `v*`.
