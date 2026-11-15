---
name: release
description: Prepares a release the way the repo already does it. Finds the repo's convention (release docs, CI tag patterns, earlier tags and release branches), proposes the next version, lists what goes in and which database migrations the release will run, makes the release branch with the version bump locally, and pushes the branch and tag only after an explicit yes. Use when the user runs /release or asks to cut, tag, publish or deploy a new version.
---

# Release

- `/release`: asks which component, if the repo releases more than one.
- `/release <component> [version]`: for example `/release backend` or `/release backend 1.7.0`.
- `/release <component> staging`: a staging release, when the repo has one.

Pushing a release tag usually deploys and migrates a real database. Everything up to the push is local and can be thrown away; the push itself waits for an explicit yes.

## 1. Find the convention

Read in this order, and let the first source that answers win:

1. The repo's own release docs and skills: `docs/RELEASE.md` or similar, `.claude/skills/*release*`, `.agents/skills/*release*`.
2. CI: the tag patterns it reacts to (`tag 'backend_v*-rc*'`, `on: push: tags:`), what it validates (a `.csproj` version against the tag, the branch name, that the base is merged) and what it does on a tag (build, publish, deploy, database migration, merge back).
3. History: `git tag --sort=-creatordate`, the release branches (`git branch -r | grep release`) and the last release's bump commit (`git show --stat <last tag>`), which shows the files a bump touches, for example `.csproj` files and a changelog.

Report it in a few lines: components, tag pattern with its production and staging variants, release branch pattern, base branch, files to bump, and what CI does when the tag arrives.

If the repo has no release process (no tags, no docs, no tag-triggered CI), say so and stop. Do not invent one.

## 2. Version

- The last final tag of the component (without the `-rc` / `-dev` suffix) is the current version.
- Propose the next one from what goes in (step 3): only fixes, the patch number; new features, the minor; breaking changes, the major. The user confirms.
- The tag, the branch and every version field must match exactly; CI usually checks this.

## 3. What goes in

- `git fetch`, then the base branch's commits since the last release of the component was cut: `git log --first-parent <last -rc0 / -dev0 tag>..origin/<base>`, leaving out the merge-back commits of earlier releases. Do not count from the final tag: it usually sits on `master`, and a range from it pulls in old history of the base branch.
- From that list: the merged PRs and the ticket keys in their titles.
- Check that the base branch's last CI run passed. If not, say so before anything else.
- Draft release notes from that list, grouped as features and fixes, in the language and format of the repo's changelog if it keeps one.

## 4. Database

- Migrations added since the last release: `git diff --name-only <last -rc0 tag>..origin/<base> -- <migrations folders>` (the `ef-migration` skill finds the folders).
- For each one, say what it does and call out drops, renames and data changes, as the `ef-migration` skill reviews them.
- Produce the SQL with `ef-migration script` from the last tag's migration, so the user can read exactly what CI will run against the database.
- No migrations: say so in one line.

## 5. Prepare locally

1. The base branch, up to date, then the release branch named exactly as the convention says.
2. Set every version field the last release bumped (`<Version>`, `<AssemblyVersion>`, `<FileVersion>`) in the same files to the new version, whatever number is there now: on some repos the base branch keeps an old number and only release branches carry the real one. Add the changelog entry if the repo keeps one.
3. Commit with the message style of the last bump commit.
4. Build the projects whose version CI validates.

The user's working tree is not touched for this: if it has uncommitted changes or is on another branch, say so and ask whether to switch, or prepare the release in a clean clone (`git -c core.longpaths=true clone`, as Windows paths in a temp folder get too long).

## 6. Stop and confirm

Show, in one short block:

- component, version, environment (production or staging);
- the branch and the exact annotated tag (`git tag -a <tag> -m "<message in the repo's style>"`);
- what CI will do with that tag, including which database it migrates;
- the migrations from step 4 and the release notes from step 3.

Then wait for an explicit yes for this push. A yes for staging is not a yes for production.

## 7. Push

- Push the branch, then create and push the annotated tag.
- Hand over to `watch-release` with the tag: it follows the pipeline until it finishes, checks that CI made the final tag and merged the release branch back, and watches the deployed app afterwards.
- On failure: fix on the same release branch, commit, push, and tag again with the next suffix (`-rc1`, `-rc2`, `-dev1`). Never move, delete or reuse a tag.

## Never

- Lightweight tags. CI often reads the tagger from the annotation.
- Push a branch or tag, or run a database migration, without the explicit yes from step 6.
- Release from a base branch whose CI is red without the user saying so.
