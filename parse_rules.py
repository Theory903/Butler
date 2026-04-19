import glob
import re

rules = []
keywords = r"\b(MUST|NEVER|SHALL|REQUIRED|PROHIBITED|ONLY)\b"

for p in glob.glob("docs/**/*.md", recursive=True):
    try:
        with open(p, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if re.search(keywords, line.upper()) and not line.strip().startswith("#"):
                    rules.append(f"{p}:{i+1}\t{line.strip()}")
    except:
        pass

with open('mandatory_rules.txt', 'w') as f:
    f.write("\n".join(rules))
