# Tests

All project test files should live in this directory.

Run Python tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -p "test*.py" -t .
```

Run the frontend helper test from the project root:

```powershell
node .\test\test_frontend_archive_review.js
```
