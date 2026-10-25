import os, glob

# Find all empty test files
empty_tests = []
for root, dirs, files in os.walk('tests'):
    for f in sorted(files):
        if f.endswith('.py'):
            fpath = os.path.join(root, f)
            size = os.path.getsize(fpath)
            if size == 0:
                empty_tests.append(fpath)

print("=== EMPTY TEST FILES ===")
for t in empty_tests:
    # Map test path to source path
    rel = os.path.relpath(t, 'tests')
    # Replace test_ prefix
    src_name = rel.replace('test_', '')
    # Try different source locations
    possible_srcs = [
        os.path.join('src', src_name.replace('.py', '')),
        os.path.join('src', src_name),
    ]
    # Also try without the .py extension as a module
    src_module = src_name.replace(os.sep, '.').replace('.py', '')
    print(f"\n{t}")
    print(f"  source module: {src_module}")

# Find all source files (non-test)
print("\n\n=== ALL SOURCE FILES ===")
for root, dirs, files in os.walk('src'):
    for f in sorted(files):
        if f.endswith('.py') and not f.startswith('__'):
            rel = os.path.relpath(os.path.join(root, f), 'src')
            print(f"  src/{rel}")
