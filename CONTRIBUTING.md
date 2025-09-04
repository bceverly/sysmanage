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

