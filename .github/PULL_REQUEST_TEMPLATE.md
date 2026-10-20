<!--
PR title must follow Conventional Commits, e.g.
  fix(install): retire the legacy Card (Custom) module
  feat(reports): add supplier ageing columns
-->

### What does this PR do?

<!-- Explain the change and the problem it solves. -->

### Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / tech debt
- [ ] Docs / CI only

### Checklist

- [ ] PR title follows Conventional Commits
- [ ] Business logic and validation are server-side
- [ ] Tests added/updated and `bench --site <site> run-tests --app card` passes
- [ ] `pre-commit` passes (ruff, ruff-format, prettier)
- [ ] No real company, supplier, operator or financial data in code, tests, screenshots or fixtures
- [ ] CHANGELOG.md updated under [Unreleased] (reason, impact on permissions/accounting/data/API, rollback limits)
- [ ] Feature Registry updated when a feature is added, fixed, changed, disabled or removed
- [ ] Target version stated (see docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md)

<!-- Put "closes #XXXX" to auto-close the related issue. -->
