# Testing Guidelines

> 📖 **For a comprehensive overview of our revolutionary testing infrastructure, see [Testing Excellence Documentation](docs/TESTING_EXCELLENCE.md)**

## Database Testing Architecture

This project uses a **dual conftest approach** for optimal test performance and isolation:

### Main Conftest (`/tests/conftest.py`)
- **Purpose**: Integration tests with full database schema
- **Method**: Uses Alembic migrations for automatic PostgreSQL ↔ SQLite sync
- **When to use**: Multi-model tests, complex integration scenarios

### API Conftest (`/tests/api/conftest.py`)
- **Purpose**: Fast, focused API tests with minimal dependencies
- **Method**: Manual SQLite-optimized model definitions
- **When to use**: Single-feature API endpoint tests

## ⚠️ CRITICAL: Adding New Models

When adding a new database model, you MUST update BOTH conftest files:

### Step 1: Add to Main Conftest (Automatic)
```bash
# Create new Alembic migration
alembic revision --autogenerate -m "Add YourNewModel"
# This automatically updates the main conftest schema
```

### Step 2: Add to API Conftest (Manual)
If API tests need the new model, add it to `/tests/api/conftest.py`:

```python
# 1. Define SQLite-compatible model in TestBase
class YourNewModel(TestBase):
    __tablename__ = "your_table_name"
    id = Column(Integer, primary_key=True, autoincrement=True)  # Use Integer, not BigInteger!
    # ... other columns with SQLite-compatible types

# 2. Add to monkey patching section
original_your_new_model = models.YourNewModel
models.YourNewModel = YourNewModel

# 3. Add to cleanup section
models.YourNewModel = original_your_new_model
```

### SQLite Compatibility Rules
- ✅ `Integer` primary keys (auto-increment works)
- ❌ `BigInteger` primary keys (no auto-increment)
- ✅ `String` instead of `Text` for better performance
- ✅ `DateTime` without timezone info
- ✅ Simple foreign key relationships

## Testing Commands

```bash
# Test all packages (should be 100% pass rate)
make test

# Test specific API suite
python -m pytest tests/api/test_your_feature.py -v

# Quick API test health check
python -m pytest tests/api/ -x --tb=no -q
```

## Debugging Database Issues

If tests fail with "no such table" errors:
1. Check if model exists in both conftest files
2. Verify SQLite compatibility (Integer vs BigInteger)
3. Ensure proper monkey patching in api/conftest.py
4. Run single test to isolate the issue

## Current Test Status
- **Total Tests**: ~1465
- **API Tests**: 273 (should be 100% pass rate)
- **Success Rate Target**: 99.8%+