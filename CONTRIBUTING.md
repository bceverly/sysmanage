# Contributing to SysManage Server

First off, thank you for your interest in contributing! SysManage is a complex, multi-component project, and community contributions—big or small—help make it better for everyone.

---

##  Licensing & Contributor Agreement

SysManage Server is licensed under the AGPLv3 for the Community Edition. By contributing, you agree that:
- Your contributions will be licensed under AGPLv3.
- Your work may also be included in our proprietary Enterprise Edition.
- You retain your contributions' copyright, while granting necessary redistribution rights.

This model ensures improvements benefit the community while preserving commercial viability.

---

## How to Contribute

### 1. Create an Issue
Start by opening an issue for bug reports or feature ideas. Provide:
- A clear overview of the problem or enhancement.
- Steps to reproduce (for bugs).
- Expected vs. actual behavior.

Label with `bug`, `enhancement`, or `help wanted`.

### 2. Work on It
Clone the repo and create a feature branch:
```bash
git checkout -b feature/meaningful-name
```

After cloning, run **`make install-dev`** to install Python/Node
dependencies AND activate the in-repo git hooks (see
`.githooks/README.md`).  The `pre-push` hook runs `make lint`
before allowing pushes; this catches the same things CI catches
without burning a cycle to find out.  Skip the hook in genuine
emergencies with `git push --no-verify`.

### 3. Development Notes
- **Alembic migrations**: For database schema changes, run:
  ```bash
  alembic revision --autogenerate -m "Describe changes"
  alembic upgrade head
  ```
- **Tests**: Add tests in `tests/`. Run all tests with:
  ```bash
  make test
  ```

### 4. Formatting & Linting
- Python: `black` + `pylint`
  ```bash
  black backend/
  python -m pylint backend/
  ```
- Frontend (React/Vite): `prettier` + `eslint`
  ```bash
  cd frontend && npm run lint
  ```

### 5. Submit a Pull Request (PR)
- Use a concise, descriptive commit message.
- PR template includes description, resolution steps, testing notes, and migration needs.
- Ensure PR title and description are clear for reviewers.

---

## What Happens Next

- Maintainers review your PR for correctness, style, and tests.
- You may be asked for revisions—this helps improve quality.
- Once approved and merged, your contribution becomes part of SysManage!

---

## Internationalization (i18n) Contributions

SysManage supports 14 languages. To add or update translations:

- **Frontend**: update `frontend/public/locales/{lang}/translation.json`
- **Backend**: edit `backend/i18n/locales/{lang}/LC_MESSAGES/messages.po`, then compile with:
  ```bash
  msgfmt messages.po -o messages.mo
  ```

Include a short note describing the translation changes in your PR.

### Translation tooling (local-model assisted)

Frontend strings are referenced in code as `t('key', 'English fallback')`.
The tooling keeps every locale in sync:

- `make i18n-seed` — copy any new keys into all 14 locales, prefixing the
  non-English ones with `[TODO] ` so they're easy to find.
- `make i18n-translate` — fill the `[TODO]` strings via a **local**
  OpenAI-compatible endpoint (vLLM / Ollama / llama.cpp). Runs entirely on
  your own hardware — no external API. Configure with `I18N_LLM_BASE_URL`,
  `I18N_LLM_MODEL`, `I18N_LLM_API_KEY`; scope with `LANG=de` (default `all`).
- `make i18n-backtranslate` — local round-trip QA: samples translated
  strings, back-translates them, and flags semantic drift for human review.

CI enforces two deterministic, network-free gates (no model needed):

- `make i18n-validate` — every code-referenced key exists in every locale.
- `make i18n-placeholders` — every translated value preserves the exact
  interpolation tokens (`{{var}}`, `%s`, `<tags>`, …) of its English source.
  This is part of `make lint`.

Once a locale is fully translated, `make i18n-check` adds a completeness
gate (no `[TODO]` strings remain); flip `lint` from `i18n-placeholders` to
`i18n-check` to make untranslated strings a hard failure.

---

## Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/). Be respectful, constructive, and inclusive in all communications.

---

## Tips for a Great Contribution

- Open an issue before starting large work.
- Keep PRs focused to speed reviews.
- Update documentation alongside your changes.
- Add or update i18n support if changes affect text or UI.

Thanks again for helping make SysManage better!

