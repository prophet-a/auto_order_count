"""
Модуль для виявлення та аналізу секцій у військових наказах.
Основні функції:
- find_sections: Знаходить усі секції в документі за маркерами
- detect_section_type: Визначає тип секції на основі контексту
- extract_section_date: Витягує дату з секції
- extract_meal_info: Витягує інформацію про котлове забезпечення
"""

import re
from text_processing import normalize_text
from utils import parse_date

def find_sections(text, section_markers):
    """
    Знаходить секції в тексті за заданими маркерами.
    
    Args:
        text (str): Текст для аналізу (вже потенційно вирізаний головний блок)
        section_markers (list): Список кортежів (маркер, тип_секції)
        
    Returns:
        list: Список кортежів (тип_секції, текст_секції, початкова_позиція)
    """
    # Нормалізація тексту вже не потрібна тут, бо вона зроблена в main.py
    # Також видаляємо логіку пошуку головних маркерів, бо вона перенесена в main.py
    normalized_text = text # Припускаємо, що текст вже нормалізований та вирізаний
    
    # Знайдемо індекси початку кожної секції
    section_starts = []
    print("\n--- DEBUG: Searching for section markers within the provided text block ---")
    
    for marker, section_type in section_markers:
        # Екрануємо маркер для безпечного пошуку та додаємо підтримку номерів підпунктів
        escaped_marker = re.escape(marker.replace(':', ''))
        # Додаємо підтримку для маркерів, які можуть бути в підпунктах (наприклад, "10.2. З відрядження:")
        pattern = r'(?:\d+\.\d+\.\s*)?' + escaped_marker
        print(f"  Searching for Type: '{section_type}', Marker: '{marker[:50]}...'")
        
        for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
            print(f"    Found raw marker '{marker[:50]}...' at relative index: {match.start()}")
            
            # Визначення типу відрядження на основі контексту (залишаємо, може бути корисно)
            current_section_type = section_type
            if section_type == 'Прибуття у відрядження':
                current_section_type = detect_section_type(normalized_text, match.start(), section_type)
            elif section_type == 'Лікарня':
                current_section_type = detect_hospital_section(normalized_text, match.start(), section_type)
                
            section_starts.append((match.start(), marker, current_section_type))
    
    # Додаткова перевірка для секції "З лікувального закладу" (залишаємо)
    hospital_patterns = [
        r'(?:\d+\.\d+\.\s*)?з\s+лікувального\s+закладу',
        r'(?:\d+\.\d+\.\s*)?з\s+лікарні',
        r'(?:\d+\.\d+\.\s*)?з\s+медичного\s+закладу',
        r'(?:\d+\.\d+\.\s*)?з\s+медичного\s+установи'
    ]
    
    for pattern in hospital_patterns:
        for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
            if not any(start_pos == match.start() for start_pos, _, _ in section_starts):
                print(f"    Found hospital section with alternative pattern '{pattern}' at relative index: {match.start()}")
                section_starts.append((match.start(), pattern, 'Лікарня'))
    
    print(f"--- END DEBUG: Section marker search complete ({len(section_starts)} potential starts found within block) ---")
    
    # Сортуємо знайдені початки секцій за індексом
    section_starts.sort(key=lambda x: x[0])
    
    # Перевірка чи знайдені секції
    if not section_starts:
        print("Увага: не знайдено жодної відомої секції всередині наданого блоку. Обробляємо весь блок як один розділ.")
        # Вирішуємо, який тип присвоїти в такому випадку. Можливо, 'ППОС' або передавати None?
        # Поки що повертаємо як ППОС для сумісності, але це може потребувати уточнення.
        return [('ППОС', normalized_text, 0)]
    
    # Формуємо секції
    sections = []
    for i, (start_pos, marker, section_type) in enumerate(section_starts):
        if i < len(section_starts) - 1:
            end_pos = section_starts[i+1][0]
        else:
            end_pos = len(normalized_text)
        
        section_text = normalized_text[start_pos:end_pos]
        sections.append((section_type, section_text, start_pos))
        print(f"DEBUG: Created section - Type: {section_type}, Relative Start: {start_pos}, Length: {len(section_text)}")
    
    print(f"Знайдено {len(sections)} секцій всередині наданого блоку")
    return sections


def detect_section_type(text, start_pos, initial_type):
    """
    Визначає тип секції на основі контексту.
    
    Args:
        text (str): Повний текст документа
        start_pos (int): Початкова позиція секції
        initial_type (str): Початковий тип секції
        
    Returns:
        str: Визначений тип секції
    """
    # Беремо контекст після маркера для аналізу
    context_window = 500
    context_end = min(start_pos + context_window, len(text))
    context_text = text[start_pos:context_end]
    
    # Визначаємо чи це навчання чи звичайне відрядження через аналіз контексту
    if initial_type == 'Прибуття у відрядження':
        if any(phrase in context_text.lower() for phrase in [
            "з метою проходження навчання",
            "для проходження навчання",
            "з метою навчання",
            "навчального батальйону",
            "школи індивідуальної підготовки"
        ]):
            print(f"    Determined as 'Прибуття у відрядження (навчання)' based on context")
            return 'Прибуття у відрядження (навчання)'
        elif any(phrase in context_text.lower() for phrase in [
            "з метою виконання службового завдання",
            "для виконання службового завдання",
            "для виконання службових обов'язків"
        ]):
            print(f"    Confirmed as 'Прибуття у відрядження' based on context")
            return 'Прибуття у відрядження'
        elif re.search(r'до\s+військової\s+частини\s+[АA][-]?\d{4}', context_text, re.IGNORECASE):
            print(f"    Determined as 'Прибуття у відрядження' based on destination military unit")
            return 'Прибуття у відрядження'
        elif re.search(r'до\s+\d+[-]?(?:го|й|й)?\s+навчальн(?:ого|ий)\s+батальйон', context_text, re.IGNORECASE) or "школи" in context_text.lower():
            print(f"    Determined as 'Прибуття у відрядження (навчання)' based on destination training battalion")
            return 'Прибуття у відрядження (навчання)'
    
    return initial_type


def detect_hospital_section(text, start_pos, initial_type):
    """
    Визначає тип секції лікувального закладу на основі контексту.
    
    Args:
        text (str): Повний текст документа
        start_pos (int): Початкова позиція секції
        initial_type (str): Початковий тип секції
        
    Returns:
        str: Визначений тип секції
    """
    # Беремо контекст після маркера для аналізу
    context_window = 500
    context_end = min(start_pos + context_window, len(text))
    context_text = text[start_pos:context_end]
    
    # Перевіряємо наявність ключових слів для підтвердження, що це секція лікувального закладу
    hospital_keywords = [
        "лікувальний заклад",
        "лікарня",
        "медичний заклад",
        "медична установа",
        "виписаний",
        "виписана",
        "виписаних",
        "виписний епікриз"
    ]
    
    if any(keyword in context_text.lower() for keyword in hospital_keywords):
        print(f"    Confirmed as '{initial_type}' based on hospital keywords")
        return initial_type
    
    # Якщо не знайдено ключових слів, але є маркер "З лікувального закладу", все одно вважаємо це секцією лікарні
    if "з лікувального закладу" in context_text.lower() or "з лікарні" in context_text.lower():
        print(f"    Confirmed as '{initial_type}' based on marker")
        return initial_type
    
    # Якщо не знайдено підтверджень, повертаємо початковий тип
    return initial_type


def extract_section_date(section_text, default_date=None):
    """
    Витягує дату з тексту секції.
    
    Args:
        section_text (str): Текст секції або кортеж (number, text)
        default_date (str, optional): Стандартна дата, якщо не знайдено. За замовчуванням None.
        
    Returns:
        str: Дата у форматі 'DD.MM.YYYY' або None
    """
    # Перевірка, чи section_text є кортежем - вилучаємо текст
    if isinstance(section_text, tuple) and len(section_text) == 2:
        _, section_text = section_text
    
    # Пошук дати за різними шаблонами
    date_match = re.search(r"''(\d{1,2})''\s+(\w+)\s+(\d{4})\s+року", section_text)
    if not date_match:
        date_match = re.search(r"''(\d{1,2})''\s+(\w+)\s+(\d{4})", section_text)
        
    if date_match:
        date_str = f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}"
        return parse_date(date_str)
    else:
        return default_date


def extract_meal_info(section_text, default_meal=None):
    """
    Витягує інформацію про котлове забезпечення з тексту секції.
    
    Args:
        section_text (str): Текст секції
        default_meal (str, optional): Стандартне значення, якщо не знайдено. За замовчуванням None.
        
    Returns:
        tuple: (тип_прийому_їжі, дата_харчування) або (default_meal, None)
    """
    meal_type = default_meal
    meal_date = None
    normalized_section_text = section_text.lower()

    # 1. Шукаємо тип харчування простим пошуком тексту
    if "зі сніданку" in normalized_section_text:
        meal_type = "зі сніданку"
        print("DEBUG: Found 'зі сніданку'")
    elif "з обіду" in normalized_section_text:
        meal_type = "з обіду"
        print("DEBUG: Found 'з обіду'")
    elif "з вечері" in normalized_section_text:
        meal_type = "з вечері"
        print("DEBUG: Found 'з вечері'")
    else:
        print("DEBUG: Meal type keyword not found.")

    # 2. Покращений патерн для пошуку дати, пов'язаної з харчуванням
    # Врахування різних форматів запису з "зарахувати на котлове забезпечення"
    date_patterns = [
        # Стандартний формат з ''дата''
        r"(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})",
        
        # Формат одразу після "зарахувати на котлове забезпечення"
        r"зарахувати\s+на\s+котлов(?:е|ого)\s+забезпечення\s+(?:частини|в\s+місці\s+тимчасового\s+розміщення\s+особового\s+складу,\s+[\d\w\s]+)?\s+(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})",
        
        # Інші варіації запису з "котлове забезпечення"
        r"котлове\s+забезпечення\s+(?:частини\s+)?(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})",
        
        # Запис через кому після частини
        r"зарахувати\s+на\s+котлов(?:е|ого)\s+забезпечення\s+(?:частини|в\s+місці\s+тимчасового\s+розміщення\s+особового\s+складу),\s+[\d\w\s]+\s+(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})",
        
        # Загальний патерн з виділенням всієї фрази котлового забезпечення
        r"зарахувати\s+на\s+котлов(?:е|ого)\s+забезпечення\s+.*?(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})"
    ]
    
    for pattern in date_patterns:
        date_match = re.search(pattern, section_text, re.IGNORECASE)
        if date_match:
            # Всі патерни повинні мати 3 групи для дати
            if len(date_match.groups()) >= 3:
                # Беремо останні 3 групи для дати
                groups = date_match.groups()
                date_day = groups[-3]
                date_month = groups[-2]
                date_year = groups[-1]
                meal_date = parse_date(f"{date_day} {date_month} {date_year}")
                print(f"DEBUG: Found meal date: {meal_date}")
                
                # Якщо ми не знайшли тип харчування в п.1, але знайшли тут, то витягуємо його з контексту
                if not meal_type:
                    meal_context = date_match.group(0).lower()
                    if "зі сніданку" in meal_context:
                        meal_type = "зі сніданку"
                    elif "з обіду" in meal_context:
                        meal_type = "з обіду" 
                    elif "з вечері" in meal_context:
                        meal_type = "з вечері"
                    print(f"DEBUG: Extracted meal type from context: {meal_type}")
                
                break  # Знайшли дату, виходимо з циклу
    
    if not meal_date:
        print("DEBUG: Meal date pattern not found.")
        # Спробуємо знайти хоча б дату повернення з лікарні, якщо немає конкретної дати котлового
        date_match = re.search(r"з\s+''(\d{1,2})''\s+(\w+)\s+(\d{4})\s+року", section_text)
        if date_match:
            meal_date = parse_date(f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}")
            print(f"DEBUG: Fallback to return date: {meal_date}")
    
    # 3. Витягуємо додаткову інформацію про місце харчування для контексту
    # Може бути використано для визначення локації, якщо необхідно
    location_match = re.search(r"зарахувати\s+на\s+котлов(?:е|ого)\s+забезпечення\s+в\s+місці\s+тимчасового\s+розміщення\s+особового\s+складу,\s+([\d\w\s]+)(?:школи|батальйону)", section_text, re.IGNORECASE)
    if location_match:
        meal_location = location_match.group(1).strip()
        print(f"DEBUG: Found meal location: {meal_location}")
    
    # Повертаємо знайдений тип харчування та дату (або стандартні значення)
    print(f"DEBUG: Returning meal info - Type: {meal_type}, Date: {meal_date}")
    return (meal_type, meal_date)


def split_section_into_subsections(section_text, section_type=None):
    """
    Розділяє текст секції на підсекції за маркерами типу '1.2.3.' або '11.2.1' або '11.9' на початку рядка.
    Потім кожну підсекцію розбиває на абзаци (за порожніми рядками).
    Важливо: Не викликає normalize_text на початку, щоб зберегти переноси рядків для re.MULTILINE.

    Args:
        section_text (str): Текст секції (НЕ нормалізований)
        section_type (str, optional): Тип секції

    Returns:
        list: Список кортежів (номер підсекції, список_рядків_абзаців_цієї_підсекції)
              де список_рядків_абзаців_цієї_підсекції - це list[str], кожен str - текст абзацу.
    """
    # НЕ викликаємо normalize_text тут, щоб зберегти \n для MULTILINE
    print(f"DEBUG (split_section): Input text length (raw): {len(section_text)}")
    if len(section_text) > 0:
        print(f"DEBUG: First 100 chars (raw): {section_text[:100]}")

    # Покращуємо патерн, щоб він краще обробляв X.Y.Z формат у військових наказах
    # Та підтримував варіації у форматуванні номерів (з чи без крапки в кінці)
    subsection_numbers_pattern = r'(?:^|\n)\s*(\d+(?:\.\d+)+\.?)\s+'
    subsection_numbers = list(re.finditer(subsection_numbers_pattern, section_text, re.MULTILINE))

    # Доповнюємо патерн для знаходження секцій типу "11.9.1 військовослужбовців військової частини..."
    alt_subsection_pattern = r'(?:^|\n)\s*(\d+\.\d+\.\d+)\s+військовослужбовців\s+військової\s+частини'
    alt_subsection_matches = list(re.finditer(alt_subsection_pattern, section_text, re.MULTILINE))
    
    # Перевіряємо, чи знайдено якісь додаткові підсекції за альтернативним патерном
    if alt_subsection_matches:
        print(f"DEBUG (split_section): Found {len(alt_subsection_matches)} additional subsections with alt pattern.")
        subsection_numbers.extend(alt_subsection_matches)
        subsection_numbers.sort(key=lambda match: match.start())

    positions = []
    number_texts = []
    match_ends = []

    for match in subsection_numbers:
        # Ensure we capture the number group (group 1)
        num_group = match.group(1)
        if num_group:
            # Use start of the number group for position logic
            positions.append(match.start(1))
            number_texts.append(num_group)
            match_ends.append(match.end()) # Use end of the full match for text slicing
        else:
             print(f"DEBUG (split_section): Match found but group 1 (number) is empty. Match: {match.group(0)}")

    print(f"DEBUG (split_section): Found {len(positions)} subsection numbers: {number_texts}")

    # Якщо не знайдено жодного номера підсекції, спробуємо знайти за іншим форматом
    if not positions:
        # Простий патерн для знаходження чисел типу "11.8", "11.9" на початку рядка
        simple_section_pattern = r'(?:^|\n)\s*(\d+\.\d+)(?:$|\s|\n)'
        simple_matches = list(re.finditer(simple_section_pattern, section_text, re.MULTILINE))
        
        if simple_matches:
            print(f"DEBUG (split_section): Found {len(simple_matches)} simple subsections like X.Y")
            
            for match in simple_matches:
                num_group = match.group(1)
                if num_group:
                    positions.append(match.start(1))
                    number_texts.append(num_group)
                    match_ends.append(match.end())

            if positions: # If we found matches with this pattern
                combined = sorted(zip(positions, number_texts, match_ends), key=lambda x: x[0])
                positions, number_texts, match_ends = zip(*combined)

    # Якщо все ще не знайдено жодного номера підсекції
    if not positions:
        # Перевіряємо специфічні випадки, як раніше
        if section_type == "Повернення з відрядження":
            # ... (логіка для повернення з відрядження залишається)
            pass # Залишимо як є, можливо, не потребує нормалізації тут

        print("DEBUG (split_section): No subsection numbers found, processing whole section.")
        # Split the entire section text into paragraphs
        # Using regex to split by one or more newlines, potentially surrounded by whitespace
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n+', section_text) if p.strip()]
        if not paragraphs and section_text.strip(): # Handle case of single paragraph section
             paragraphs = [section_text.strip()]
        print(f"DEBUG (split_section): Whole section split into {len(paragraphs)} paragraphs.")
        return [(None, paragraphs)] # Return paragraphs for the single, non-numbered section

    # --- Main Logic for Splitting Subsections and Paragraphs ---
    subsections_with_paragraphs = []

    for i, num_start_pos in enumerate(positions):
        subsection_number = number_texts[i]
        # Text starts AFTER the matched number pattern (including trailing whitespace)
        text_start_index = match_ends[i]

        # End position is the start of the number text of the *next* subsection
        if i < len(positions) - 1:
            # Use the start position of the *next* number text
            end_pos = positions[i+1]
            # Adjust end_pos back to capture the newline before the next number
            prev_newline = section_text.rfind('\n', 0, end_pos)
            if prev_newline != -1:
                 end_pos = prev_newline
            else: # If no newline before it (unlikely but possible)
                 end_pos = end_pos # Keep the start of the number text

        else:
            # For the last subsection, go to the end of the entire section text
            end_pos = len(section_text)

        # Extract the raw text for this subsection
        raw_subsection_text = section_text[text_start_index:end_pos].strip()

        if raw_subsection_text:
            # Split the raw subsection text into paragraphs
            # Using regex to split by one or more newlines, potentially surrounded by whitespace
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n+', raw_subsection_text) if p.strip()]

            if not paragraphs and raw_subsection_text: # Handle single paragraph subsections
                paragraphs = [raw_subsection_text]

            if paragraphs: # Only add if there are non-empty paragraphs
                 subsections_with_paragraphs.append((subsection_number, paragraphs))
                 print(f"DEBUG (split_section): Added subsection {subsection_number}. Found {len(paragraphs)} paragraphs. First para starts: '{paragraphs[0][:50]}...'")
            else:
                 print(f"DEBUG (split_section): Subsection {subsection_number} resulted in no paragraphs after splitting.")

    print(f"DEBUG (split_section): Returning {len(subsections_with_paragraphs)} subsections with paragraphs.")
    return subsections_with_paragraphs 