import re
import json
import csv

def normalize_name(name):
    """Normalize names to handle different cases and formats."""
    # Convert to lowercase for case-insensitive matching
    name = name.lower().strip()
    # Convert genitive case to nominative for comparison
    # This is a simplification - in reality, Ukrainian grammar rules for case conversion are more complex
    if name.endswith('а') or name.endswith('я'):
        name = name[:-1]
    return name

# Read results.json
with open('results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
# Extract and normalize names from results.json
results_names = set()
results_details = {}

for item in data:
    normalized_name = item.get('name_normal', '').lower().strip()
    results_names.add(normalized_name)
    results_details[normalized_name] = item

# Read tst.txt
with open('tst.txt', 'r', encoding='utf-8') as f:
    txt = f.read()

# Function to extract name from genitive case format
def extract_name_from_genitive(text, pattern):
    names = []
    for match in re.finditer(pattern, text):
        try:
            surname = match.group(1)
            # Handle surnames in genitive case (ending with 'А' or 'Я')
            if surname.endswith('А') or surname.endswith('Я'):
                surname = surname[:-1]  # Convert to nominative case
            
            name = match.group(2)
            patronymic = match.group(3)
            
            full_name = f"{surname} {name} {patronymic}"
            names.append(full_name.lower())
        except:
            continue
    return names

# Different patterns to match names in various formats
patterns = [
    # "Солдата ... ПРІЗВИЩЕ Ім'я По-батькові"
    r'(?:Солдата|Старшого солдата|[А-ЯІЇЄҐ][а-яіїєґ]+ сержанта|[А-ЯІЇЄҐ][а-яіїєґ]+ лейтенанта|капітана|майора)[^"]+"([А-ЯІЇЄҐ]+[АЯ]?)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+[ау]?)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+[ау]?)"',
    
    # Specific pattern for the numbered list items
    r'(\d+)\.(?:\d+)?(?:\.\d+)?\s+([А-ЯІЇЄҐ]+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)',
    
    # Pattern for names in paragraph 11
    r'солдат за призовом[^"]+\s([А-ЯІЇЄҐ]+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)'
]

# Extract names using regex patterns
names_in_doc = []

# Apply the first pattern
names_in_doc.extend(extract_name_from_genitive(txt, patterns[0]))

# Apply additional patterns
for match in re.finditer(patterns[1], txt):
    try:
        # The surname is in group 2 for this pattern
        surname = match.group(2)
        name = match.group(3)
        patronymic = match.group(4)
        full_name = f"{surname} {name} {patronymic}"
        names_in_doc.append(full_name.lower())
    except:
        continue

# Apply pattern for paragraph 11
for match in re.finditer(patterns[2], txt):
    try:
        surname = match.group(1)
        name = match.group(2)
        patronymic = match.group(3)
        full_name = f"{surname} {name} {patronymic}"
        names_in_doc.append(full_name.lower())
    except:
        continue

# Find unique names in the document
unique_names = set(names_in_doc)

# Find names that are in tst.txt but not in results.json
missing_names = []

for name in unique_names:
    # Check if the name is already in results.json (exact match)
    if name in results_names:
        continue
        
    # Try fuzzy matching for cases where cases or minor spelling differences occur
    found = False
    for result_name in results_names:
        # Split both names into parts
        name_parts = name.split()
        result_parts = result_name.split()
        
        # Names must have the same number of parts
        if len(name_parts) != len(result_parts):
            continue
            
        # Check if each part is similar enough (starts with the same characters)
        match_count = 0
        for i in range(len(name_parts)):
            min_len = min(len(name_parts[i]), len(result_parts[i]))
            # Compare at least 4 characters or the full length if shorter
            compare_len = min(4, min_len)
            if name_parts[i][:compare_len] == result_parts[i][:compare_len]:
                match_count += 1
        
        # If most parts match, consider it a match
        if match_count >= len(name_parts) - 1:
            found = True
            break
    
    if not found:
        missing_names.append(name)

# Print results
print(f"Total names in document: {len(unique_names)}")
print(f"Total names in results.json: {len(results_names)}")
print(f"Names missing from results.json: {len(missing_names)}")
print("\nMissing names:")
for name in sorted(missing_names):
    print(name.title()) 