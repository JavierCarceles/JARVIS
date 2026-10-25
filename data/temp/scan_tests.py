import os
for root, dirs, files in os.walk('tests'):
    for f in sorted(files):
        if f.endswith('.py') or f.endswith('.txt'):
            fpath = os.path.join(root, f)
            with open(fpath) as fh:
                content = fh.read().strip()
            size = len(content)
            lines = len(content.split('\n')) if content else 0
            has_tests = 'def test' in content
            if size < 200 or not has_tests or lines < 10:
                print(f"{fpath}: {size} bytes, {lines} lines, has_tests={has_tests}")
