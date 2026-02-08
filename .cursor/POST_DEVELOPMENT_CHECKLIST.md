# Post-Development Checklist

Use this checklist after EVERY development session to ensure documentation stays current.

## 📝 Documentation Updates

### README.md
- [ ] Updated API endpoints section (if endpoints added/modified)
- [ ] Updated frontend pages section (if pages added/modified)
- [ ] Updated environment variables table (if env vars added/changed)
- [ ] Updated technology stack (if dependencies added)
- [ ] Updated installation steps (if setup process changed)
- [ ] Updated project structure (if folders/files reorganized)
- [ ] Updated "Recent Changes" section
- [ ] Updated "Last Updated" date at bottom

### DEVELOPMENT.md
- [ ] Added new entry with current date/time
- [ ] Specified entry type (FEATURE/BUGFIX/REFACTOR/etc.)
- [ ] Listed all changes made
- [ ] Listed all files modified/created
- [ ] Explained rationale for changes
- [ ] Documented any dependencies added/removed
- [ ] Noted any breaking changes
- [ ] Included migration steps (if applicable)
- [ ] Listed next steps or known issues

### .env.example
- [ ] Added any new environment variables
- [ ] Updated descriptions if needed
- [ ] Removed deprecated variables
- [ ] Verified format matches actual .env

### requirements.txt
- [ ] Added new dependencies (backend and/or frontend)
- [ ] Updated version pins if needed
- [ ] Removed unused dependencies
- [ ] Organized by category (if using comments)

## 🧪 Code Quality

### Testing
- [ ] Wrote unit tests for new functions
- [ ] Wrote integration tests for new endpoints
- [ ] Updated existing tests if behavior changed
- [ ] All tests passing (`pytest`)
- [ ] Verified test coverage maintained/improved

### Code Style
- [ ] Code follows PEP 8
- [ ] Added type hints to new functions
- [ ] Added docstrings to new functions/classes
- [ ] Removed debug print statements
- [ ] Removed commented-out code
- [ ] Added inline comments for complex logic

### Error Handling
- [ ] Proper try/except blocks added
- [ ] Meaningful error messages
- [ ] Appropriate HTTP status codes (backend)
- [ ] User-friendly error messages (frontend)

## 🔧 Configuration

### Backend
- [ ] CORS settings updated if needed
- [ ] API versioning maintained
- [ ] Logging configured properly
- [ ] Security settings reviewed

### Frontend
- [ ] API base URL configurable
- [ ] Loading states implemented
- [ ] Error handling in place
- [ ] Session state used appropriately

## 🔐 Security

- [ ] No hardcoded credentials
- [ ] No sensitive data in logs
- [ ] Environment variables used for secrets
- [ ] Input validation implemented
- [ ] SQL injection prevention (if using DB)
- [ ] XSS prevention (if rendering user content)

## 📦 Dependencies

- [ ] Only necessary dependencies added
- [ ] Version pins appropriate
- [ ] No security vulnerabilities (check with `pip-audit`)
- [ ] Licenses compatible with project

## 🐛 Bug Fixes

If this was a bug fix:
- [ ] Root cause identified and documented
- [ ] Fix verified to work
- [ ] Added test to prevent regression
- [ ] Related code reviewed for similar issues

## 🚀 Deployment Readiness

- [ ] Feature works in development environment
- [ ] Migrations created (if database changed)
- [ ] No console errors
- [ ] Performance acceptable
- [ ] Backwards compatible (or breaking changes documented)

## 📋 Git

- [ ] Staged only relevant files
- [ ] Meaningful commit message written
- [ ] Commit message references DEVELOPMENT.md entry
- [ ] No sensitive files committed (.env, credentials, etc.)
- [ ] .gitignore updated if needed

### Suggested Commit Message Format

```
[TYPE] Brief description

- Detailed change 1
- Detailed change 2

See DEVELOPMENT.md [YYYY-MM-DD HH:MM] entry for full details

Refs: #issue-number (if applicable)
```

Types: feat, fix, refactor, docs, test, chore, style, perf

## 🤖 AI Assistant Reminder

If you're an AI assistant (Cursor), after completing development work:

1. **Review this checklist** - Go through each item
2. **Update documentation** - README.md and DEVELOPMENT.md are mandatory
3. **Remind the user** - Tell them what documentation was updated
4. **Suggest commit message** - Provide a well-formatted commit message
5. **Highlight any breaking changes** - Make these very clear

## Example Post-Development Summary

```
✅ Development Complete!

📝 Documentation Updated:
- README.md: Added new /api/v1/users endpoint documentation
- README.md: Added Users page to frontend pages section
- README.md: Added AUTH_SECRET environment variable
- DEVELOPMENT.md: Added [2024-01-15 14:30] FEATURE entry
- .env.example: Added AUTH_SECRET with description

📦 Files Modified:
- backend/app/api/v1/endpoints/users.py (created)
- backend/app/schemas/user.py (created)
- frontend/pages/3_Users.py (created)
- backend/requirements.txt (added pyjwt)

🧪 Testing:
- Added 5 new tests for user endpoints
- All tests passing
- Coverage: 85% (+3%)

⚠️ Breaking Changes:
None

🔄 Suggested Commit Message:
---
feat: Add user management functionality

- Implemented CRUD endpoints for users
- Created Users page in Streamlit frontend
- Added JWT authentication
- Added AUTH_SECRET environment variable

See DEVELOPMENT.md [2024-01-15 14:30] entry for full details
---

📋 Next Steps:
- Add email verification for new users
- Implement password reset flow
- Add user role management

Please review the documentation updates and commit when ready!
```

---

## Quick Tips

- **Don't skip documentation** - It saves time in the long run
- **Be specific** - "Updated API" is not helpful; "Added POST /users endpoint" is
- **Think of future you** - You'll forget details in days/weeks
- **Document decisions** - Why is often more important than what
- **Keep it current** - Update docs immediately, not later

---

Last Updated: [Current Date]
