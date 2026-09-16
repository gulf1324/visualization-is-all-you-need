# Contributing

## Commit messages

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>)!: <subject>

<optional body>

<optional footer: BREAKING CHANGE: ... | Refs: #123>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, `revert`. Subject is imperative, <= 72 chars, no
trailing period.

`.gitmessage` is preloaded as the commit template, and `.githooks/commit-msg`
rejects non-conforming subjects.

## Versioning

[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The current
version lives in `VERSION` (single source of truth).

| Commit                     | Bump  |
| -------------------------- | ----- |
| `fix:`                     | PATCH |
| `feat:`                    | MINOR |
| `!` or `BREAKING CHANGE:`  | MAJOR |

Releasing: move entries from `## [Unreleased]` in `CHANGELOG.md` into a new
`## [x.y.z] - YYYY-MM-DD` section, update `VERSION`, then tag `vx.y.z`.

## Local setup after cloning

```sh
git config --local core.hooksPath .githooks
git config --local commit.template .gitmessage
git config --local core.autocrlf false
```
