# Contributing to Butler

> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## Welcome

Butler is a durable, memory-driven, policy-governed personal AI runtime. We welcome contributions that make it better.

This guide covers how to contribute code, documentation, and ideas.

---

## Code of Conduct

### Our Pledge

We are committed to a welcoming environment. Harassment of any kind is not tolerated.

### Standards

- **Be respectful**: Treat others as you want to be treated
- **Be constructive**: Criticism should be actionable, not personal
- **Be inclusive**: Welcome newcomers and different perspectives

### Unacceptable Behavior

- Harassment, discrimination, or intimidation
- Personal attacks or trolling
- Publishing others' private information
- Deliberate intimidation or stalking

---

## How to Contribute

### 1. Report Bugs

**Before creating an issue:**
- Search existing issues
- Verify on latest version
- Collect reproduction steps

**Issue template:**
```markdown
## Bug Description
Clear description of the bug.

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. See error

## Expected Behavior
What should happen.

## Actual Behavior
What actually happens.

## Environment
- OS: 
- Browser:
- Version:
```

### 2. Suggest Features

**Before creating an issue:**
- Search existing proposals
- Understand Butler's architecture
- Check roadmap

**Feature template:**
```markdown
## Problem
What problem does this solve?

## Proposed Solution
How should it work?

## Alternatives
Other solutions considered?

## Impact
Security, performance, or complexity implications?
```

### 3. Pull Requests

#### PR Process

1. **Fork** the repository
2. **Create** a feature branch
3. **Make** your changes
4. **Test** thoroughly
5. **Submit** a PR

#### PR Checklist

- [ ] Tests pass (`pytest`)
- [ ] Lint passes (`ruff check .`)
- [ ] Type check passes (`pyright`)
- [ ] Documentation updated
- [ ] Changelog updated (if applicable)
- [ ] PR description follows template

#### PR Template

```markdown
## Summary
Brief description of changes.

## Type
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Testing
How was this tested?

## Checklist
- [ ] Tests pass locally
- [ ] Docs updated
- [ ] Changelog added
```

---

## Development Workflow

### 1. Setup

```bash
git clone git@github.com:yourorg/Butler.git
cd Butler
docker-compose up -d
```

See [SETUP.md](./05-development/SETUP.md) for details.

### 2. Branch Naming

Use descriptive branch names:

| Type | Example |
|------|---------|
| Feature | `feat/memory-compression` |
| Bug fix | `fix/auth-token-expiry` |
| Documentation | `docs/api-reference` |
| Refactor | `refactor/orchestrator-flow` |

### 3. Commit Messages

Follow Conventional Commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructure
- `test`: Adding tests
- `chore`: Maintenance

**Examples:**
```
feat(auth): add JWT refresh token rotation
fix(memory): handle empty search results
docs(api): update rate limiting docs
```

### 4. Code Standards

#### Python

- **Style**: Ruff + Black (via `ruff format`)
- **Types**: Full type hints required
- **Tests**: pytest with >80% coverage

```python
# Good
async def get_user(user_id: UUID) -> User:
    """Retrieve user by ID."""
    return await db.query(User, id=user_id)

# Bad
async def get_user(id):
    return await db.query(User, id=id)
```

#### JavaScript/TypeScript

- **Style**: Prettier
- **Types**: TypeScript strict mode

### 5. Testing Requirements

**Unit tests:**
- Test one unit of behavior
- Mock external dependencies
- Fast execution (<100ms each)

**Integration tests:**
- Test service interactions
- Use test containers
- Verify real database/cache

**E2E tests:**
- Test full user flows
- Use realistic data
- Run in CI only

---

## Service-Specific Guidelines

### Backend Services

1. **Follow service boundaries**
   - Gateway NEVER calls Memory directly
   - All services through Orchestrator

2. **Use existing patterns**
   - Check similar services for patterns
   - Reuse infrastructure code

3. **Add observability**
   - Add metrics for new endpoints
   - Add tracing for new flows
   - Add logging for errors

### Mobile App

1. **Follow React Native patterns**
   - Use functional components
   - Use Zustand for state
   - Use expo-* packages

2. **Test on both platforms**
   - iOS and Android
   - Different screen sizes

### Documentation

1. **Update relevant docs**
   - API changes → API docs
   - Architecture changes → HLD/LLD
   - Runbooks → Operations docs

2. **Use templates**
   - Service specs → Service template
   - Runbooks → Runbook template

---

## Review Process

### For Reviewers

1. **Review within 48 hours**
2. **Be constructive**
3. **Approve when ready**

**Review checklist:**
- [ ] Code is correct
- [ ] Tests are adequate
- [ ] Documentation updated
- [ ] No security issues
- [ ] Follows style guide

### For Contributors

1. **Respond to feedback**
2. **Make requested changes**
3. **Re-request review**

---

## Common Issues

### "Tests are failing"

```bash
# Run tests locally
cd backend
pytest

# Run with coverage
pytest --cov=Butler --cov-report=term-missing
```

### "Linting errors"

```bash
# Auto-fix
ruff check . --fix

# Format
ruff format .
```

### "Type errors"

```bash
# Type check
pyright Butler
```

---

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md
- Release notes
- Git history

---

## Getting Help

| Channel | Purpose |
|---------|---------|
| #butler-engineering | Development questions |
| #butler-help | General help |
| Discord | Community discussion |

---

## License

By contributing, you agree that your contributions will be licensed under the project's license.

---

*Contributing guide owner: Platform Team*
*Version: 4.0*