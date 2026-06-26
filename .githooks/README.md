# Git hooks

This directory holds the project's shareable git hooks.  They're
activated by pointing `core.hooksPath` at this directory (instead of
the default `.git/hooks/` which is not version-controlled).

## Installation

Run `make install-hooks` from the repo root once after cloning.  It
sets `core.hooksPath = .githooks` for this clone — idempotent, safe to
re-run.  `make install-dev` runs `make install-hooks` automatically as
its last step, so for most contributors there's nothing to do beyond
the normal setup workflow.

## Active hooks

### `pre-commit`

Runs `black --check` against the `.py` files staged for the commit.
If black would reformat any of them, the commit is blocked with a
message telling the dev to run `make format`, `git add` the result,
and re-commit.  This is the upstream-most defense against the
"`make lint` silently rewrote my working tree but I forgot to
`git add`" gap that the lint target's auto-fix behaviour can
otherwise mask.

The hook does **not** auto-fix and stage the result — explicit
`make format` keeps the dev in control of what's in each commit.
Bypass with `git commit --no-verify` in a genuine emergency, but the
`pre-push` hook + CI both run the same check and will reject the
drift later.

### `pre-push`

Runs `make lint` before allowing a push to remote.  If linting fails,
the push is blocked with an error pointing at the failing tool
(Black, pylint, eslint, i18n validator, etc).  In a genuine emergency
the hook can be bypassed with `git push --no-verify`, but the next CI
run will fail the same way so the bypass only delays the fix.

`make lint` itself now also acts as a tripwire: if black reformats
anything, the target exits non-zero even though the fix was applied
locally.  Combined with `pre-push`, that means a "make lint then push"
workflow can't silently ship un-formatted commits.

## Bypassing the install (not recommended)

If for any reason you don't want the hooks active in your clone, run
`git config --unset core.hooksPath` — but please don't push without
running `make lint` first, or CI will reject the change anyway.
