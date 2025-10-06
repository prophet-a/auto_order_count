import re
import json

# Read results.json
with open('results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
# Extract and normalize names from results.json
results_names = []
for item in data:
    normalized_name = item.get('name_normal', '').lower().strip()
    results_names.append(normalized_name)

# Read tst.txt
with open('tst.txt', 'r', encoding='utf-8') as f:
    txt = f.read()

# Extract names using regex for various formats
names_in_doc = []

# Look for pattern: "Солдата ... ПРІЗВИЩЕ Ім'я По-батькові"
pattern1 = r'(?:Солдата|Старшого солдата|[а-яіїєґА-ЯІЇЄҐ]+ сержанта|[а-яіїєґА-ЯІЇЄҐ]+ лейтенанта|[а-яіїєґА-ЯІЇЄҐ]+ капітана|майора|капітана)(?:[^"]*?)([А-ЯІЇЄҐ]+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)'

for match in re.finditer(pattern1, txt):
    surname = match.group(1)
    name = match.group(2)
    patronymic = match.group(3)
    full_name = f"{surname} {name} {patronymic}"
    names_in_doc.append(full_name.lower())

# Look for pattern in paragraph 11: "солдат за призовом ... ПРІЗВИЩЕ Ім'я По-батькові"
pattern2 = r'солдат за призовом[^"]+"([А-ЯІЇЄҐ]+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)'

for match in re.finditer(pattern2, txt):
    surname = match.group(1)
    name = match.group(2)
    patronymic = match.group(3)
    full_name = f"{surname} {name} {patronymic}"
    names_in_doc.append(full_name.lower())

# Add additional pattern for "прізвище ім'я по-батькові" format
pattern3 = r'(\d+\.\d+\.\d+)\s+([А-ЯІЇЄҐ]+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)\s+([А-ЯІЇЄҐ][а-яіїєґ\']+)'

for match in re.finditer(pattern3, txt):
    surname = match.group(2)
    name = match.group(3)
    patronymic = match.group(4)
    full_name = f"{surname} {name} {patronymic}"
    names_in_doc.append(full_name.lower())

# Add pattern for names in genitive case (ending with 'а/я') - convert to nominative
def to_nominative(surname):
    if surname.endswith('А') or surname.endswith('Я'):
        return surname[:-1] # Remove last letter to get nominative case
    return surname

pattern4 = r'(?:Солдата|Старшого солдата|[а-яіїєґА-ЯІЇЄҐ]+ сержанта|капітана)[^"]+"([А-ЯІЇЄҐ]+[АЯ])\s+([А-ЯІЇЄҐ][а-яіїєґ\']+[ау])\s+([А-ЯІЇЄҐ][а-яіїєґ\']+[ау])"'

for match in re.finditer(pattern4, txt):
    surname = to_nominative(match.group(1))
    name = match.group(2)
    if name.endswith('а') or name.endswith('я') or name.endswith('у'):
        name = name[:-1] # Remove ending to approximate nominative
    patronymic = match.group(3)
    if patronymic.endswith('а') or patronymic.endswith('я') or patronymic.endswith('у'):
        patronymic = patronymic[:-1] # Remove ending to approximate nominative
    full_name = f"{surname} {name} {patronymic}"
    names_in_doc.append(full_name.lower())

# Find unique names in the document
unique_names = set(names_in_doc)

# Find names that are in tst.txt but not in results.json
missing_names = []
for name in unique_names:
    if name not in results_names:
        # Double check with a more flexible match (to handle case differences)
        found = False
        for result_name in results_names:
            # Check if all words in the name are present in the result_name
            name_parts = name.split()
            result_parts = result_name.split()
            
            if len(name_parts) != len(result_parts):
                continue
                
            match_count = 0
            for i in range(len(name_parts)):
                # Allow partial match (first few characters)
                if name_parts[i][:4] == result_parts[i][:4]:
                    match_count += 1
            
            if match_count >= len(name_parts) - 1:  # Allow one part to be different
                found = True
                break
                
        if not found:
            missing_names.append(name)

print(f"Total names in document: {len(unique_names)}")
print(f"Total names in results.json: {len(results_names)}")
print(f"Names missing from results.json: {len(missing_names)}")
print("\nMissing names (normalized to nominative case):")
for name in sorted(missing_names):
    print(name.title()) 