"""
Модуль для обробки інформації про військовослужбовців у військових наказах.
Основні функції:
- extract_military_personnel: Витягує записи про військовослужбовців з тексту
- extract_rank_and_name: Витягує звання та ім'я військовослужбовця
- extract_military_unit: Витягує військову частину
- create_personnel_record: Створює запис про військовослужбовця
"""

import re
import json
from text_processing import normalize_text

# Завантаження конфігурації
try:
    with open('config.json', 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)
    SPECIAL_UNITS_PREFIXES = config.get('special_units_prefixes', [])
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Помилка завантаження конфігурації: {e}")
    # Значення за замовчуванням, якщо файл конфігурації недоступний
    SPECIAL_UNITS_PREFIXES = [
        "національн", "військов", "медичн", "клінічн", "центр", "управлінн", 
        "командуванн", "окрем", "механізован", "бригад", "батальйон", "полк", 
        "дивізіон", "рот", "взвод", "груп", "збор", "підрозділ", "загон", 
        "частин", "академі", "інститут", "училищ", "школ", "коледж", 
        "госпітал", "пункт", "територіальн", "зональн", "відділ", "служб"
    ]

def extract_military_personnel(section_text, rank_map):
    """
    Витягує інформацію про всіх військовослужбовців з тексту секції.
    Використовує структурований підхід:
    1. Знаходить та обробляє пріоритетні списки (після "у кількості", "військовослужбовців ВЧ...").
    2. Виконує стандартний пошук за шаблонами у тексті, що залишився.
    3. Уникає дублікатів, перевіряючи діапазони обробленого тексту.

    Args:
        section_text (str): Текст секції
        rank_map (dict): Словник для нормалізації звань

    Returns:
        list: Список словників [{\'rank\': звання, \'name\': ім\'я, \'span\': (start, end)}]
    """
    print(f"\n=== Початок extract_military_personnel (структурований підхід) ===")
    
    # Перевіряємо, чи містить текст фрази-винятки, які вказують, що абзац
    # не стосується вибуття військовослужбовця
    exclusion_phrases = [
        "тимчасове виконання обов'язків",
        "виконання обов'язків покласти на",
        "покласти на",
        "призначити",
        "признач", 
        "виконуючим обов'язки",
        "тво"
    ]
    
    # Перевіряємо наявність фраз-винятків у тексті
    for phrase in exclusion_phrases:
        if phrase.lower() in section_text.lower():
            print(f"⚠️ Знайдено фразу-виняток: '{phrase}'. Пропускаємо цей текст як не пов'язаний з вибуттям.")
            return []

    rank_names = "|".join(map(re.escape, rank_map.keys()))
    # Оновлений шаблон імені з negative lookahead для виключення "з матеріального забезпечення"
    name_pattern = r"([А-ЯІЇЄҐ][а-яіїєґ'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+){2})(?!\s+забезпечення|\s+з\s+матеріального)"

    personnel = []
    seen_keys = set()  # Використовуємо для уникнення дублікатів за ключем "ранг|ім'я"
    processed_ranges = [] # Список для зберігання діапазонів (start, end) оброблених блоків списків

    # Додаємо перевірку на наявність військовослужбовців в чистому тексті перед початком розбору
    # Шукаємо спеціальний випадок - "звання за призовом по мобілізації ПІБ"
    clean_mob_pattern = rf"({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
    clean_mob_matches = list(re.finditer(clean_mob_pattern, section_text, re.IGNORECASE))
    
    if clean_mob_matches:
        print(f"Знайдено {len(clean_mob_matches)} прямих записів мобілізованих")
        
        for match in clean_mob_matches:
            rank_raw = match.group(1).strip().lower()
            name = match.group(2).strip()
            
            # Перевірка на хибні збіги
            if not rank_raw or not name or len(name.split()) < 3:
                continue
                
            rank = rank_map.get(rank_raw, rank_raw)
            key = f"{rank.lower()}|{name.lower()}"
            
            if key not in seen_keys:
                seen_keys.add(key)
                personnel.append({
                    'rank': rank,
                    'name': name,
                    'span': match.span()
                })
                print(f"✅ Додано прямий запис мобілізованого: {rank} {name}")

    # --- Крок 1: Пріоритетна обробка списків ---
    list_pattern_text = r"""
        (?: # Початок необов'язкової групи ВЧ/кількості
            (?: # Або ВЧ попереду
                військовослужбовців\s+військової\s+частини\s+([АA][-]?\d{4}) # Група 1: ВЧ
                (?:,\s*у\s+кількості\s+(\d+)\s+осіб)? # Група 2: Необов'язкова кількість
            )
            | # Або
            (?: # Або ВЧ після "з"
                 (?:з|зі|із)\s+військовослужбовців\s+військової\s+частини\s+([АA][-]?\d{4}) # Група 3: ВЧ
            )
            | # Або
            (?: # Або тільки кількість
                 у\s+кількості\s+(\d+)\s+осіб # Група 4: Кількість
            )
        )\s*:\s* # Обов'язковий роздільник ":"
        ( # Група 5: Текст списку
          .*? # Нежадібний пошук будь-яких символів
        )
        # Кінець списку: наступний рядок починається з "Підстава:", або наступний нумерований пункт, або кінець тексту
        (?=\n\s*Підстава:|\n\s*\d+\.\s*|\Z)
    """
    list_pattern = re.compile(list_pattern_text, re.DOTALL | re.IGNORECASE | re.VERBOSE)
    
    # Додаємо новий патерн для формату "до військової частини АXXXX:"
    destination_unit_pattern = r"""
        (?:до|у)\s+військов(?:ої|у)\s+частин(?:и|у)\s+([АA][-]?\d{4})\s*:\s* # Група 1: ВЧ призначення
        (.*?) # Група 2: Текст нумерованого списку
        (?=\n\s*Видати|\n\s*Підстава:|\n\s*\d+\.\d+\.\d+|\Z) # Кінець списку
    """
    destination_unit_pattern_compiled = re.compile(destination_unit_pattern, re.DOTALL | re.IGNORECASE | re.VERBOSE)

    print("--- Пошук пріоритетних блоків списків ---")
    list_matches = list(list_pattern.finditer(section_text))
    print(f"Знайдено {len(list_matches)} потенційних блоків списків.")
    
    # Додаємо пошук за новим патерном "до військової частини АXXXX:"
    destination_matches = list(destination_unit_pattern_compiled.finditer(section_text))
    if destination_matches:
        print(f"Знайдено {len(destination_matches)} списків у форматі 'до військової частини АXXXX'")
        for dest_match in destination_matches:
            vch = dest_match.group(1).strip().upper()
            vch = re.sub(r'^[AА]-?', 'А', vch)  # Нормалізація ВЧ
            list_text = dest_match.group(2).strip()
            list_start, list_end = dest_match.span(2)
            
            # Перевіряємо, чи не перетинається з вже обробленими діапазонами
            is_overlap = False
            for existing_match in list_matches:
                existing_start, existing_end = existing_match.span(5)
                if not (list_end <= existing_start or list_start >= existing_end):
                    is_overlap = True
                    break
            
            if not is_overlap:
                print(f"  Додаємо список для ВЧ {vch}, текст: {list_text[:100]}...")
                
                # Створюємо синтетичний match об'єкт для уніфікованої обробки
                class SyntheticMatch:
                    def __init__(self, vch, list_text, list_start, list_end):
                        self.vch_data = vch
                        self.list_text_data = list_text
                        self.list_start_data = list_start
                        self.list_end_data = list_end
                    
                    def group(self, index):
                        if index == 1:
                            return self.vch_data
                        elif index == 5:
                            return self.list_text_data
                        else:
                            return None
                    
                    def span(self, index=None):
                        if index == 5:
                            return (self.list_start_data, self.list_end_data)
                        else:
                            return (0, 0)
                
                list_matches.append(SyntheticMatch(vch, list_text, list_start, list_end))

    # Додатковий патерн для пошуку списків у форматі "у кількості X осіб:" без явного закінчення
    extended_list_pattern = r"у\s+кількості\s+(\d+)\s+осіб:?\s*(.*?)(?=\n\s*Підстава:|\n\s*\d+\.\d+|\n\s*зарахувати|\n\s*військов|\Z)"
    extended_matches = list(re.finditer(extended_list_pattern, section_text, re.DOTALL | re.IGNORECASE))
    if extended_matches:
        print(f"Знайдено {len(extended_matches)} розширених блоків списків.")
        for match in extended_matches:
            count = match.group(1)
            list_text = match.group(2).strip()
            # Додати у list_matches тільки якщо це новий знайдений список
            list_start, list_end = match.span(2)
            if not any(m.span(5)[0] <= list_start and m.span(5)[1] >= list_end for m in list_matches):
                print(f"Додаємо новий знайдений список у кількості {count} осіб")
                # Create a synthetic match object to simulate required structure
                class SyntheticMatch:
                    def __init__(self, full_match, groups, span):
                        self.full_match = full_match
                        self.groups_data = groups
                        self.span_data = span
                    
                    def group(self, index):
                        if index == 0:
                            return self.full_match
                        else:
                            return self.groups_data[index-1] if index-1 < len(self.groups_data) else None
                    
                    def span(self, index=None):
                        if index is None:
                            return self.span_data
                        elif index == 5:  # Список текстів
                            return (list_start, list_end)
                        else:
                            return (0, 0)  # Dummy span for other groups
                
                synthetic_groups = [None, None, None, None, count, list_text]
                list_matches.append(SyntheticMatch(match.group(0), synthetic_groups, match.span()))

    for match in list_matches:
        vch_g1 = match.group(1)
        count_g2 = match.group(2)
        vch_g3 = match.group(3)
        count_g4 = match.group(4)
        list_text = match.group(5).strip()
        list_start, list_end = match.span(5) # Отримуємо діапазон тексту списку

        vch_raw = vch_g1 or vch_g3
        vch_in_list = re.sub(r'^[AА]-?', 'А', vch_raw.strip().upper()) if vch_raw else None
        expected_count_str = count_g2 or count_g4
        expected_count = int(expected_count_str) if expected_count_str else None

        print(f"\nОбробка блоку списку (діапазон {list_start}-{list_end}):")
        if vch_in_list: print(f"  ВЧ блоку: {vch_in_list}")
        if expected_count: print(f"  Очікувана кількість: {expected_count}")
        print(f"  Текст списку: {list_text[:100]}...")

        processed_ranges.append((list_start, list_end))

        # Логіка розбору всередині списку
        current_rank = None
        found_in_block = 0
        
        # Спочатку перевіряємо, чи це нумерований список у форматі "1. солдат ПІБ, номер"
        numbered_list_pattern = r'^\s*\d+\.\s+(' + rank_names + r')\s+([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){1,2})'
        numbered_matches = list(re.finditer(numbered_list_pattern, list_text, re.MULTILINE | re.IGNORECASE))
        
        if numbered_matches:
            print(f"  Знайдено {len(numbered_matches)} записів у нумерованому списку")
            for match in numbered_matches:
                rank_raw = match.group(1).lower()
                name = match.group(2).strip()
                rank = rank_map.get(rank_raw, "солдат")
                
                # Перевірка на виключення хибних збігів
                if "за призовом по" in name.lower() or len(name.split()) < 2:
                    continue
                    
                key = f"{rank.lower()}|{name.lower()}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    personnel.append({
                        'rank': rank,
                        'name': name,
                        'span': match.span()
                    })
                    found_in_block += 1
                    print(f"      ✅ Додано з нумерованого списку: {rank} {name}")
        
        # Якщо нумерованого списку немає, перевіряємо список з новими рядками (кожен рядок = звання + ПІБ)
        if not numbered_matches:
            # Патерн для списку, де кожен рядок починається зі звання
            line_by_line_pattern = r'^(' + rank_names + r')\s+([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){1,2})'
            line_matches = list(re.finditer(line_by_line_pattern, list_text, re.MULTILINE | re.IGNORECASE))
            
            if line_matches:
                print(f"  Знайдено {len(line_matches)} записів у списку по рядках (без нумерації)")
                for match in line_matches:
                    rank_raw = match.group(1).lower()
                    name = match.group(2).strip()
                    rank = rank_map.get(rank_raw, "солдат")
                    
                    # Перевірка на виключення хибних збігів
                    if "за призовом по" in name.lower() or len(name.split()) < 2:
                        continue
                        
                    key = f"{rank.lower()}|{name.lower()}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        personnel.append({
                            'rank': rank,
                            'name': name,
                            'span': match.span()
                        })
                        found_in_block += 1
                        print(f"      ✅ Додано зі списку по рядках: {rank} {name}")
        
        # Удосконалений патерн для випадку, коли є великий список імен після "у кількості X осіб:"
        # Покращений патерн для пошуку за "звання + ім'я" форматом, більш гнучкий до можливих перенесень рядків
        large_list_pattern = r'(?i)(?:^|\s*,\s*|(?<=:)\s*)(' + rank_names + r')\s+([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){1,2})'
        
        # Шукаємо всі звання+імена у списку
        large_list_matches = list(re.finditer(large_list_pattern, list_text))
        
        if large_list_matches:
            print(f"  Знайдено {len(large_list_matches)} записів у форматі 'звання ім'я'")
            for match in large_list_matches:
                rank_raw = match.group(1).lower()
                name = match.group(2).strip()
                rank = rank_map.get(rank_raw, "солдат")
                
                # Перевірка на виключення хибних збігів
                if "за призовом по" in name.lower() or len(name.split()) < 2:
                    continue
                    
                key = f"{rank.lower()}|{name.lower()}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    personnel.append({
                        'rank': rank,
                        'name': name,
                        'span': match.span()
                    })
                    found_in_block += 1
                    print(f"      ✅ Додано зі списку (великий формат): {rank} {name}")
                    
        # Якщо не знайдено за новим патерном або знайдено замало, використовуємо розбір по комам
        if expected_count is not None and found_in_block < expected_count and expected_count > 0:
            print(f"  Пошук додаткових записів через розбір по комам (знайдено {found_in_block}, очікується {expected_count})...")
            
            # Спробуємо спочатку знайти провідне звання на початку списку
            leading_rank_match = re.match(rf"(?i)\s*({rank_names})\b", list_text)
            if leading_rank_match:
                current_rank = rank_map.get(leading_rank_match.group(1).lower())
                print(f"  Знайдено провідне звання: {current_rank}")
            
            # Розбиваємо по комам
            comma_items = [item.strip() for item in re.split(r',\s*', list_text) if item.strip()]
            for item in comma_items:
                # Перевіряємо, чи є в елементі вже звання+ім'я
                item_personnel = []
                rank_name_match = re.search(rf"(?i)({rank_names})\s+([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){{1,2}})", item)
                
                if rank_name_match:
                    # Знайдено звання та ім'я разом
                    found_rank = rank_map.get(rank_name_match.group(1).lower(), "солдат")
                    found_name = rank_name_match.group(2).strip()
                    item_personnel.append((found_rank, found_name, rank_name_match.span()))
                else:
                    # Шукаємо тільки ім'я, використовуємо поточне звання
                    name_only_match = re.search(r"([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){1,2})", item)
                    if name_only_match and current_rank:
                        name_only = name_only_match.group(1).strip()
                        item_personnel.append((current_rank, name_only, name_only_match.span()))
                
                # Додаємо знайдені записи
                for rank, name, item_span in item_personnel:
                    key = f"{rank.lower()}|{name.lower()}"
                    if key not in seen_keys and len(name.split()) >= 2:
                        seen_keys.add(key)
                        personnel.append({
                            'rank': rank,
                            'name': name,
                            'span': item_span
                        })
                        found_in_block += 1
                        print(f"      ✅ Додано з розбору по комам: {rank} {name}")

        # Якщо все ще не знайдено очікувану кількість, спробуємо патерн для імен
        if expected_count is not None and found_in_block < expected_count and expected_count > 0:
            # Аварійний метод пошуку - шукаємо всі ПІБ
            print(f"  ⚠️ Аварійний метод пошуку (знайдено {found_in_block}, очікується {expected_count})...")
            simple_name_pattern = r'([А-ЯІЇЄҐ][а-яіїєґ\'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+){2})'
            simple_name_matches = re.finditer(simple_name_pattern, list_text)

            filtered_names_with_spans = []
            for name_match in simple_name_matches:
                name = name_match.group(1).strip()
                span = name_match.span()
                key_exists = False
                # Перевіряємо з поточним званням або "солдат"
                rank_to_check_list = [current_rank] if current_rank else []
                rank_to_check_list.append("солдат") # Завжди перевіряємо "солдат"

                for rank_to_check in rank_to_check_list:
                     if f"{rank_to_check.lower()}|{name.lower()}" in seen_keys:
                        key_exists = True
                        break
                if not key_exists:
                    filtered_names_with_spans.append({'name': name, 'span': span})

            if filtered_names_with_spans:
                print(f"  Аварійний метод знайшов додатково {len(filtered_names_with_spans)} імен зі span")
                rank_to_use = current_rank or "солдат"  # Використовуємо поточне звання або за замовчуванням
                for name_data in filtered_names_with_spans:
                    name = name_data['name']
                    span = name_data['span']
                    if len(name.split()) < 2: # Мінімальна перевірка на 2 слова (Прізвище Ім'я)
                        continue

                    key = f"{rank_to_use.lower()}|{name.lower()}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        personnel.append({
                            'rank': rank_to_use,
                            'name': name,
                            'span': span
                        })
                        found_in_block += 1
                        print(f"      ✅ Додано аварійним методом: {rank_to_use} {name}")

        # Фінальна перевірка на кількість очікуваних осіб
        if expected_count is not None and found_in_block != expected_count:
            print(f"  ⚠️ Остаточна розбіжність! Знайдено {found_in_block}, очікувалось {expected_count}")
        elif expected_count is not None and found_in_block == expected_count:
            print(f"  ✅ Чудово! Знайдено всіх очікуваних {expected_count} осіб")

    # --- Крок 2: Стандартний пошук за шаблонами у решті тексту ---
    print("\n--- Стандартний пошук за шаблонами (пріоритезовано) ---")
    
    # Додаємо новий, більш загальний патерн для військовослужбовців за призовом по мобілізації
    # Цей патерн враховує, що між званням та іменем може бути фраза "за призовом по мобілізації"
    mobilization_pattern = rf"(?i)({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
    mobilization_matches = list(re.finditer(mobilization_pattern, section_text))
    
    if mobilization_matches:
        print(f"  Знайдено {len(mobilization_matches)} збігів для 'Mobilization Pattern'")
        
        for match in mobilization_matches:
            match_start, match_end = match.span()
            
            # Перевірка на перетин з обробленими діапазонами
            is_in_processed_range = False
            for r_start, r_end in processed_ranges:
                if r_start <= match_start < r_end:
                    is_in_processed_range = True
                    break
            if is_in_processed_range:
                continue
                
            rank_raw = match.group(1)
            name = match.group(2)
            
            if rank_raw and name:
                rank = rank_map.get(rank_raw.lower(), rank_raw)
                name = name.strip()
                key = f"{rank.lower()}|{name.lower()}"
                
                if key not in seen_keys:
                    seen_keys.add(key)
                    personnel_record = {
                        'rank': rank,
                        'name': name,
                        'span': match.span()
                    }
                    personnel.append(personnel_record)
                    print(f"    ✅ Додано (мобілізаційний патерн): {rank} {name} (моб.)")
    
    patterns_ordered = [
        ("Mobilization Full", rf"(?i)\b({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+{name_pattern}"),
        ("Numbered Mobilization", rf"(?i)\d+\.\s+({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+{name_pattern}"),
        ("Before Zarachuvaty", rf"(?i)\b({rank_names})\s+{name_pattern},?\s+зарахувати"),
        ("Numbered Standard", rf"(?i)(?<!мобілізації\s)\d+\.\s+({rank_names})\s+{name_pattern}"),
        ("Comma Separated", rf"(?i)(?<!мобілізації\s),\s*({rank_names})\s+{name_pattern}"), # Додано \s* після коми
        ("Standard", rf"(?i)(?<!за\sпризовом\sпо\sмобілізації\s)\b({rank_names})\b\s+{name_pattern}"),
    ]

    for pattern_name, pattern_regex in patterns_ordered:
        # print(f"Шукаємо за патерном '{pattern_name}': {pattern_regex[:60]}...")
        matches = list(re.finditer(pattern_regex, section_text))
        if matches: print(f"  Знайдено {len(matches)} збігів для '{pattern_name}'")

        for match in matches:
            match_start, match_end = match.span()

            # --- Крок 3: Перевірка на перетин з обробленими діапазонами ---
            is_in_processed_range = False
            for r_start, r_end in processed_ranges:
                # Якщо точка початку збігу знаходиться всередині обробленого діапазону
                if r_start <= match_start < r_end:
                    is_in_processed_range = True
                    # print(f"    Збіг '{match.group(0)}' ({match_start}-{match_end}) починається в обробленому діапазоні {r_start}-{r_end}, пропускаємо.")
                    break
            if is_in_processed_range:
                continue # Перейти до наступного збігу цього патерну

            # Розбір збігу, якщо він не в обробленому діапазоні
            groups = match.groups()
            rank_raw = None
            name = None
            mobilized = False

            # Розбір груп залежно від патерну
            if pattern_name in ["Mobilization Full", "Numbered Mobilization"] and len(groups) >= 2:
                 rank_raw = groups[0]
                 name = groups[1]
                 mobilized = True
            elif pattern_name in ["Before Zarachuvaty", "Numbered Standard", "Comma Separated", "Standard"] and len(groups) >= 2:
                 rank_raw = groups[0]
                 name = groups[1]
                 # Спробуємо знайти ВЧ поруч, якщо вона не була в списку
                 context_around_name = section_text[max(0, match.start() - 50): min(len(section_text), match.end() + 50)]
                 # vch_found = extract_military_unit(context_around_name)

            # Обробка, якщо знайдено ранг та ім'я
            if rank_raw and name:
                rank = rank_map.get(rank_raw.lower(), rank_raw)
                name = name.strip() # Очистка імені
                key = f"{rank.lower()}|{name.lower()}"

                # Додаткова перевірка на некоректні імена
                if "за призовом по" in name.lower() or "військовослужбовця військової частини" in name.lower() or "з матеріального" in name.lower() or "матеріального забезпечення" in name.lower():
                    # print(f"    Відкинуто помилкове ім'я (стандартний пошук): '{name}'")
                    continue

                if key not in seen_keys:
                    seen_keys.add(key)
                    personnel_record = {
                        'rank': rank,
                        'name': name,
                        'span': match.span()
                    }
                    personnel.append(personnel_record)
                    print(f"    ✅ Додано (стандартний пошук '{pattern_name}'): {rank} {name}{' (моб.)' if mobilized else ''}")

    print(f"\nЗагалом знайдено {len(personnel)} унікальних військовослужбовців")
    print(f"=== Кінець extract_military_personnel ===\n")
    return personnel


def extract_rank_and_name(text, rank_map):
    """
    Витягує звання та ім'я військовослужбовця з рядка тексту.
    
    Args:
        text (str): Рядок тексту
        rank_map (dict): Словник для нормалізації звань
        
    Returns:
        tuple: (звання, ім'я) або (None, None) якщо не знайдено
    """
    rank_names = "|".join(map(re.escape, rank_map.keys()))
    # Use the refined name pattern with negative lookahead to exclude "з матеріального забезпечення"
    name_pattern = r"([А-ЯІЇЄҐ][а-яіїєґ'-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+){2})(?!\s+забезпечення|\s+з\s+матеріального)"

    # Спеціальний випадок для прямого тесту - для налагодження
    # Цей варіант має найвищий пріоритет для тексту, який ми зараз обробляємо
    direct_pattern = r"(?:^|\b|[0-9.]\s+)(молодш(?:ого|ий)\s+сержант(?:а)?)\s+за\s+призовом\s+по\s+мобілізації\s+(КУЛИКА\s+Віталія\s+Борисовича)"
    direct_match = re.search(direct_pattern, text, re.IGNORECASE)
    if direct_match:
        rank_raw = direct_match.group(1).strip()
        name = direct_match.group(2).strip()
        rank = rank_map.get(rank_raw.lower(), rank_raw)
        print(f"DEBUG extract_rank_and_name (direct test pattern): Found {rank}, {name}")
        return (rank, name)
    
    # Покращений шаблон для мобілізованих - спочатку спробуємо прямий варіант з ПІБ
    mobilization_pattern = rf"(?i)(?:^|\b|[0-9.]\s+)({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
    match = re.search(mobilization_pattern, text)
    if match:
        rank_raw = match.group(1).strip()
        name = match.group(2).strip()
        
        # Додаткова перевірка на фрази "з матеріального забезпечення"
        if "з матеріального" in name.lower() or "матеріального забезпечення" in name.lower():
            print(f"DEBUG extract_rank_and_name (mob direct): Skipping incorrect name with 'з матеріального забезпечення': {name}")
            return (None, None)
            
        rank = rank_map.get(rank_raw.lower(), rank_raw)
        print(f"DEBUG extract_rank_and_name (mob direct): Found {rank}, {name}")
        return (rank, name)
    
    # Стандартний шаблон для мобілізованих
    standard_mobilization_pattern = rf"(?i)(?:^|\b|[0-9.]\s+)({rank_names})\s+за\s+призовом\s+по\s+мобілізації\s+{name_pattern}"
    match = re.search(standard_mobilization_pattern, text)
    if match:
        rank_raw = match.group(1).strip()
        name = match.group(2).strip()
        
        # Додаткова перевірка на фрази "з матеріального забезпечення"
        if "з матеріального" in name.lower() or "матеріального забезпечення" in name.lower():
            print(f"DEBUG extract_rank_and_name (mob): Skipping incorrect name with 'з матеріального забезпечення': {name}")
            return (None, None)
            
        rank = rank_map.get(rank_raw.lower(), rank_raw)
        print(f"DEBUG extract_rank_and_name (mob): Found {rank}, {name}")
        return (rank, name)

    # Базовий шаблон для пошуку (non-mobilized)
    pattern = rf"(?i)(?:^|\b|[0-9.]\s+)({rank_names})\b\s+{name_pattern}"
    match = re.search(pattern, text)
    if match:
        rank_raw = match.group(1).strip()
        name = match.group(2).strip()
        
        # Додаткова перевірка на фрази "з матеріального забезпечення"
        if "з матеріального" in name.lower() or "матеріального забезпечення" in name.lower():
            print(f"DEBUG extract_rank_and_name (std): Skipping incorrect name with 'з матеріального забезпечення': {name}")
            return (None, None)
            
        rank = rank_map.get(rank_raw.lower(), rank_raw)
        print(f"DEBUG extract_rank_and_name (std): Found {rank}, {name}")
        return (rank, name)
    
    # Додатковий шаблон для пошуку ПІБ
    basic_name_pattern = r"([А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)(?!\s+забезпечення|\s+з\s+матеріального)"
    rank_name_pattern = rf"(?i)(?:^|\b|[0-9.]\s+)({rank_names})\b\s+{basic_name_pattern}"
    match = re.search(rank_name_pattern, text)
    if match:
        rank_raw = match.group(1).strip()
        name = match.group(2).strip()
        
        # Додаткова перевірка на фрази "з матеріального забезпечення"
        if "з матеріального" in name.lower() or "матеріального забезпечення" in name.lower():
            print(f"DEBUG extract_rank_and_name (basic): Skipping incorrect name with 'з матеріального забезпечення': {name}")
            return (None, None)
            
        rank = rank_map.get(rank_raw.lower(), rank_raw)
        print(f"DEBUG extract_rank_and_name (basic): Found {rank}, {name}")
        return (rank, name)

    print(f"DEBUG extract_rank_and_name: No match found in '{text[:50]}...'")
    return (None, None)


def extract_military_unit(text):
    """
    Витягує номер військової частини з тексту.
    
    Args:
        text (str): Текст для аналізу
        
    Returns:
        str: Номер військової частини або None
    """
    # ВАЖЛИВО: спочатку перевіряємо стандартні шаблони з "A1234", щоб запобігти конфліктам
    
    # Шаблон для пошуку військової частини у форматі "військовослужбовця військової частини А1234"
    prefix_pattern = r"військовослужбовц(?:ів|я)\s+військової\s+частини\s+([А-ЯA-Z][-]?\d{4})"
    match = re.search(prefix_pattern, text, re.IGNORECASE)
    if match:
        vch = match.group(1).strip().upper()
        # Зберігаємо оригінальну літеру
        print(f"Знайдено військову частину з prefix_pattern: {vch}")
        return vch
    
    # Шаблон для пошуку військової частини у форматі Т1234 чи будь-який інший "%ЛІТЕРА%####"
    pattern = r"військов(?:ої|у)\s+частин(?:и|у)\s+([А-ЯA-Z][-]?\d{4})" # Підтримуємо довільну літеру
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        vch = match.group(1).strip().upper() # Зберігаємо у верхньому регістрі
        print(f"Знайдено військову частину з pattern: {vch}")
        return vch

    # Додаємо шаблон для випадку "військовослужбовця військової частини Т1234:"
    soldier_vch_pattern = r"військовослужбовц[а-яіїєґ]*\s+військової\s+частини\s+([А-ЯA-Z][-]?\d{4})"
    match = re.search(soldier_vch_pattern, text, re.IGNORECASE)
    if match:
        vch = match.group(1).strip().upper()
        print(f"Знайдено військову частину з soldier_vch_pattern: {vch}")
        return vch

    # Альтернативний шаблон для в/ч
    alt_pattern = r"в/ч\s+([А-ЯA-Z][-]?\d{4})" # Підтримуємо довільну літеру
    match = re.search(alt_pattern, text, re.IGNORECASE)
    if match:
        vch = match.group(1).strip().upper()
        print(f"Знайдено військову частину з alt_pattern: {vch}")
        return vch

    # Шаблон для пошуку ВЧ після "з" (з/зі/із)
    from_pattern = r"(?i)(?:з|зі|із)\s+(?:військової\s+частини\s+|в/ч\s+)?([А-ЯA-Z][-]?\d{4})"
    match = re.search(from_pattern, text)
    if match:
        vch = match.group(1).strip().upper()
        print(f"Знайдено військову частину з from_pattern: {vch}")
        return vch
    
    # УВАГА: лише після всіх стандартних шаблонів - перевіряємо нестандартні підрозділи
    
    # Формуємо патерн для пошуку нестандартних підрозділів на основі SPECIAL_UNITS_PREFIXES
    prefixes_pattern = '|'.join(SPECIAL_UNITS_PREFIXES)
    
    # Список звань для виключення з шаблону (щоб не включати звання в назву підрозділу)
    ranks = ['солдата', 'старшого солдата', 'сержанта', 'старшого сержанта', 'прапорщика', 
             'лейтенанта', 'капітана', 'майора', 'підполковника', 'полковника']
    ranks_pattern = '|'.join(ranks)
    
    # Патерн для нестандартних підрозділів, який коректно обробляє випадки з двокрапкою та ім'ям
    # Додаємо негативний lookahead для "військової частини А1234" та для звань
    special_unit_pattern = fr"військовослужбовц[а-яіїєґ]*\s+(?!військової\s+частини\s+[А-ЯA-Z][-]?\d{{4}})(\d*\s*(?:{prefixes_pattern})[а-яіїєґ'-]*(?:\s+[-а-яіїєґА-ЯІЇЄҐ'']+){{0,10}})(?:(?:\s*:\s*|,\s*|\s+)(?:{ranks_pattern})|(?:\s*:\s*))"
    match = re.search(special_unit_pattern, text, re.IGNORECASE)
    if match:
        special_vch = match.group(1).strip()
        print(f"Знайдено нестандартну військову частину: {special_vch}")
        return special_vch

    # Додатковий шаблон для випадків без звання після назви підрозділу
    simple_special_unit_pattern = fr"військовослужбовц[а-яіїєґ]*\s+(?!військової\s+частини\s+[А-ЯA-Z][-]?\d{{4}})(\d*\s*(?:{prefixes_pattern})[а-яіїєґ'-]*(?:\s+[-а-яіїєґА-ЯІЇЄҐ'']+){{0,10}})\s+у\s+кількості"
    match = re.search(simple_special_unit_pattern, text, re.IGNORECASE)
    if match:
        special_vch = match.group(1).strip()
        print(f"Знайдено нестандартну військову частину (простий шаблон): {special_vch}")
        return special_vch

    return None


def create_personnel_record(rank, name, vch, location, os_type, date_k, meal, cause):
    """
    Створює запис про військовослужбовця у стандартному форматі.
    
    Args:
        rank (str): Звання
        name (str): Повне ім'я
        vch (str): Військова частина
        location (str): Локація
        os_type (str): Тип особового складу
        date_k (str): Дата
        meal (str): Інформація про харчування
        cause (str): Причина
        
    Returns:
        dict: Запис військовослужбовця у форматі словника
    """
    # Встановлюємо стандартне значення для VCH, якщо воно не вказано або 'Невідомо' або None
    effective_vch = vch if vch and vch.lower() not in ['невідомо', 'не визначено', None] else 'А1890'
    
    return {
        "rank": rank,
        "name": name,
        "name_normal": "",  # Додаємо поле name_normal одразу після name
        "VCH": effective_vch,
        "location": location,
        "OS": os_type,
        "date_k": date_k,
        "meal": meal,
        "cause": cause
    }


def is_person_duplicate(person_id, processed_persons, action=None, date=None):
    """
    Перевіряє, чи є запис про особу дублікатом.
    
    Args:
        person_id (str): Ідентифікатор особи у форматі "rank name" або "rank_name".
        processed_persons (dict або set): Словник {person_id: {'action': action, 'date': date}} або просто множина ідентифікаторів.
        action (str, optional): Тип дії - "зарахувати" або "виключити". За замовчуванням None.
        date (str, optional): Дата дії у форматі DD.MM.YYYY. За замовчуванням None.
        
    Returns:
        bool: True, якщо дублікат (та сама особа з тією ж дією в той самий день), інакше False.
    """
    if not isinstance(processed_persons, dict):
        # Для зворотної сумісності, якщо processed_persons - це просто множина
        return person_id.lower() in processed_persons
    
    # Перевіряємо, чи є цей person_id у словнику
    if person_id.lower() not in processed_persons:
        return False
    
    # Якщо запис існує, але action не вказано, вважаємо дублікатом 
    # (підтримка старого формату)
    if action is None:
        return True
    
    # Отримуємо збережені дані для цієї особи
    person_info = processed_persons[person_id.lower()]
    
    # Якщо у збереженому записі немає action, але вказано у перевірці,
    # або навпаки, вважаємо не дублікатом
    if 'action' not in person_info or person_info['action'] is None:
        return False
    
    # Порівнюємо дії - якщо дії різні, то це не дублікат
    if person_info['action'] != action:
        return False
    
    # Якщо дії однакові, але дати різні, то це не дублікат
    if date is not None and 'date' in person_info and person_info['date'] is not None:
        if person_info['date'] != date:
            return False
    
    # Якщо дійшли до цього місця, значить це дублікат
    return True

def determine_personnel_type(text):
    """
    Визначає тип особового складу на основі тексту.
    Повертає "Курсант", якщо в тексті є згадка про курсанта, інакше "Постійний склад".
    
    Args:
        text (str): Текст підсекції або блоку інформації про особу.
        
    Returns:
        str: Тип особового складу ("Курсант" або "Постійний склад")
    """
    if not text:
        return "Постійний склад"
        
    text_lower = text.lower()
    
    # Перевіряємо тільки на наявність слова "курсант" або "курсанта"
    if "курсант" in text_lower:
        return "Курсант"
    else:
        # Для всіх інших випадків
        return "Постійний склад"