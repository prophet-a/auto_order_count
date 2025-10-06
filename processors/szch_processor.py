"""
Модуль для обробки секцій СЗЧ (самовільного залишення частини) у військових наказах.
Знаходить пункти про самовільне залишення частини та витягує з них інформацію.
"""

import re
from datetime import datetime
import json
import time  # Додаємо імпорт time

from text_processing import normalize_text
from utils import parse_date
from military_personnel import extract_military_personnel, extract_military_unit
from section_detection import extract_meal_info, extract_section_date

def process_szch_section(text, rank_map, location_triggers=None, processed_persons=None):
    """
    Обробляє секцію про самовільне залишення частини (СЗЧ).
    
    Args:
        text (str): Текст секції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (set): Множина вже оброблених осіб
        
    Returns:
        list: Список записів про військовослужбовців
    """
    results = []
    
    # Перевірка мінімальної довжини тексту
    if len(text.strip()) < 10:  # Мінімальна довжина для обробки
        print(f"  Text is too short for processing: {len(text.strip())} characters")
        return results
    
    # Перевірка на наявність ключових слів СЗЧ - розширюємо список для відповідності з find_szch_sections
    szch_keywords = ["самовільним залишенням", "виключити з усіх видів забезпечення", 
                     "самовільним залишенням частини", "самовільним залишенням лікувального закладу"]
    
    # Додаємо детальну діагностику для кращого налагодження
    print(f"  Повний текст секції для аналізу СЗЧ ({len(text)} символів): {text[:200]}...")
    
    szch_keyword_found = False
    for keyword in szch_keywords:
        if keyword in text.lower():
            szch_keyword_found = True
            print(f"  Знайдено ключове слово СЗЧ: '{keyword}'")
            break
    
    if not szch_keyword_found:
        print(f"  Section text does not contain any СЗЧ keywords, skipping.")
        return results
    
    if processed_persons is None:
        processed_persons = set()
    
    print("\n--- Entering process_szch_section ---")
    print(f"  Input text (first 300 chars): {text[:300]}...")
    print(f"  Input text length: {len(text)}")
    
    # Ділимо на пункти, які починаються з номера та крапки
    # Шукаємо пункти типу "5. Солдата за призовом..."
    # Оновлений паттерн, який враховує прізвища написані великими літерами і різні формати ПІБ
    point_pattern = r'(\d+)\.\s+([А-ЯІЇЄa-яіїє\s]+?)\s+([А-ЯІЇЄ][А-ЯІЇЄа-яіїє\']*(?:\s+[А-ЯІЇЄа-яіїє][А-ЯІЇЄа-яіїє\']*){1,2})'
    print(f"  Using main point_pattern: '{point_pattern}'")
    
    # Знаходимо всі пункти
    szch_points = list(re.finditer(point_pattern, text))
    print(f"  Found {len(szch_points)} points with main pattern.")
    
    if not szch_points:
        # Альтернативний паттерн для випадку коли прізвище повністю великими літерами
        alt_point_pattern = r'(\d+)\.\s+([А-ЯІЇЄa-яіїє\s]+?)\s+([А-ЯІЇЄ]+)\s+([А-ЯІЇЄ][а-яіїє\']+\s+[А-ЯІЇЄ][а-яіїє\']+)'
        print(f"  Using alternative point_pattern: '{alt_point_pattern}'")
        szch_points = list(re.finditer(alt_point_pattern, text))
        print(f"  Found {len(szch_points)} points with alternative pattern.")
    
    for i, point_match in enumerate(szch_points):
        print(f"\n  --- Processing Point Match #{i+1} ---")
        point_num = point_match.group(1)
        rank_text = point_match.group(2).strip()
        
        # Обробка залежно від кількості груп у регулярному виразі
        if len(point_match.groups()) == 4:  # альтернативний паттерн
            surname = point_match.group(3)
            name_patronymic = point_match.group(4)
            name_start = f"{surname} {name_patronymic}"
            print(f"  Detected alternative pattern match.")
        else:  # основний паттерн
            name_start = point_match.group(3)
            print(f"  Detected main pattern match.")
        
        print(f"  Extracted point num: '{point_num}'")
        print(f"  Extracted rank_text: '{rank_text}'")
        print(f"  Extracted name_start: '{name_start}'")
        
        # Початок тексту пункту
        point_start_idx = point_match.start()
        
        # Знаходимо кінець пункту (початок наступного пункту або кінець тексту)
        # next_point_pattern = r'\d+\.\s+[А-ЯІЇЄa-яіїє\s]+' # Original - might be too restrictive
        next_point_pattern = r'\n\s*\d+\.\s+' # Змінений паттерн - шукаємо номер з новою лінією
        next_point_match = re.search(next_point_pattern, text[point_start_idx + 1:])
        
        if next_point_match:
            point_end_idx = point_start_idx + 1 + next_point_match.start()
            point_text = text[point_start_idx:point_end_idx]
            print(f"  Point end found using next point pattern at rel pos {next_point_match.start()}")
        else:
            # Шукаємо інші маркери кінця пункту
            end_markers = ["Підстава:", "\nПідстава:"]
            end_idx = None
            
            for marker in end_markers:
                marker_pos = text.find(marker, point_start_idx + 1)
                if marker_pos != -1:
                    if end_idx is None or marker_pos < end_idx:
                        end_idx = marker_pos
            
            if end_idx:
                point_text = text[point_start_idx:end_idx]
                print(f"  Point end found using end marker at position {end_idx - point_start_idx}")
            else:
                point_text = text[point_start_idx:]
                print(f"  Next point pattern not found, taking text to the end.")
        print(f"  Extracted point_text (first 200): {point_text[:200]}...")
        print(f"  Extracted point_text length: {len(point_text)}")
        
        # Перевіряємо чи дійсно цей пункт стосується СЗЧ
        point_szch_keyword_found = False
        found_keyword = "None"
        for keyword in szch_keywords:
            if keyword in point_text.lower():
                point_szch_keyword_found = True
                found_keyword = keyword
                # print(f"  Found keyword '{keyword}' in point {point_num}") # Reduced verbosity
                break
        print(f"  SZCH keyword check in point_text: Found='{point_szch_keyword_found}', Keyword='{found_keyword}'")
                
        if not point_szch_keyword_found:
            print(f"  Point {point_num} is not about unauthorized absence (based on keywords), skipping processing.")
            continue
        
        print(f"  Point {point_num} confirmed as СЗЧ, extracting personnel info...")
        
        # Витягуємо інформацію про військовослужбовця
        # Створюємо новий текст з рангом і ПІБ + додаємо весь текст пункту для контексту
        combined_text = f"{rank_text} {name_start}. {point_text}"
        # print(f"  Calling extract_military_personnel with combined_text (len={len(combined_text)}):
        #    {combined_text[:200]}...") # Multiline print causes issues - REMOVING THIS COMMENT
        print(f"  Calling extract_military_personnel with combined_text snippet (len={len(combined_text)}): {combined_text[:200]}...")
        personnel_info = extract_military_personnel(combined_text, rank_map)
        print(f"  Result from extract_military_personnel: {personnel_info}")
        
        if not personnel_info:
            print(f"  Warning: Could not extract personnel info from point {point_num}, skipping point.")
            continue
        
        for person in personnel_info:
            # Використовуємо поля 'rank' і 'name' замість 'lastname', 'firstname', 'patronymic'
            person_id = f"{person['rank']}_{person['name']}"
            print(f"    Processing extracted person: {person_id}")
            
            if person_id in processed_persons:
                print(f"    Person {person_id} already processed, skipping")
                continue
            
            processed_persons.add(person_id)
            
            # Витягуємо додаткову інформацію
            print(f"    Extracting military unit from point_text...")
            military_unit = extract_military_unit(point_text)
            print(f"    Extracted military_unit: {military_unit}")
            
            # Витягуємо дату самовільного залишення
            print(f"    Extracting departure date from point_text...")
            
            # Спробуємо знайти дату в різних форматах
            date_patterns = [
                # Формат: з "10" серпня 2023 року
                (r"з\s+(?:'|\")(\d{1,2})(?:'|\") \s*(\w+)\s+(\d{4})\s+року", "з 'DD' місяць YYYY року"),
                # Формат: "10" серпня 2023
                (r"(?:'|\")(\d{1,2})(?:'|\") \s*(\w+)\s+(\d{4})", "'DD' місяць YYYY"),
                # Формат: 10 серпня 2023 року
                (r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+року", "DD місяць YYYY року"),
                # Формат: з 10 серпня 2023
                (r"з\s+(\d{1,2})\s+(\w+)\s+(\d{4})", "з DD місяць YYYY"),
                # Формат: 10.08.2023
                (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "DD.MM.YYYY")
            ]
            
            departure_date = None
            date_pattern_used = "None"
            
            for pattern, pattern_name in date_patterns:
                date_match = re.search(pattern, point_text)
                if date_match:
                    date_pattern_used = pattern_name
                    
                    # Обробка різних форматів дат
                    if pattern_name == "DD.MM.YYYY":
                        # Формат ДД.ММ.РРРР
                        try:
                            day = int(date_match.group(1))
                            month = int(date_match.group(2))
                            year = int(date_match.group(3))
                            departure_date = datetime(year, month, day).strftime("%d.%m.%Y")
                            break
                        except (ValueError, IndexError):
                            print(f"    Failed to parse date in DD.MM.YYYY format: {date_match.group(0)}")
                    else:
                        # Формати з назвою місяця
                        try:
                            date_str = f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}"
                            departure_date = parse_date(date_str)
                            if departure_date:
                                break
                        except (ValueError, IndexError):
                            print(f"    Failed to parse date: {date_match.group(0)}")
            
            print(f"    Departure date extraction: Pattern='{date_pattern_used}', Date='{departure_date}'")
            
            # Додаткова перевірка для випадків, коли дату не знайдено
            if not departure_date:
                # Шукаємо дату в більш складних конструкціях
                complex_date_match = re.search(r"самовільно залишив.*?(\d{1,2})[\s\.]+(\w+)[\s\.]+(\d{4})", point_text, re.IGNORECASE | re.DOTALL)
                if complex_date_match:
                    try:
                        date_str = f"{complex_date_match.group(1)} {complex_date_match.group(2)} {complex_date_match.group(3)}"
                        departure_date = parse_date(date_str)
                        date_pattern_used = "complex pattern (after 'самовільно залишив')"
                        print(f"    Found date using complex pattern: {departure_date}")
                    except (ValueError, IndexError):
                        print(f"    Failed to parse date from complex pattern")
            
            # Витягуємо інформацію про котлове забезпечення
            print(f"    Extracting meal info from point_text...")
            meal_info, meal_date = extract_meal_info(point_text)
            print(f"    Extracted meal info: '{meal_info}', Meal date: '{meal_date}'")
            
            # Визначаємо статус особи - курсант чи постійний склад
            personnel_status = "Курсант" if "курсант" in point_text.lower() else "Постійний склад"
            
            # Визначаємо місце розташування - шукаємо згадки про навчальні батальйони
            location = "ППД"  # За замовчуванням
            match_nb = re.search(r'(\d+)\s*навчальн(?:ого|ий)\s*батальйон', point_text, re.IGNORECASE)
            if match_nb:
                nb_number = match_nb.group(1)
                location = f"{nb_number} НБ"
            
            # Використовуємо дату meal_date як основну дату для date_k, 
            # або departure_date якщо meal_date відсутня
            effective_date = meal_date if meal_date else departure_date
            
            # Створюємо запис про військовослужбовця
            record = {
                "rank": person["rank"],
                "name": person["name"],
                "name_normal": '',  # Заповнюється пізніше в main.py
                "VCH": military_unit or 'A1890',
                "location": location,
                "OS": personnel_status,
                "date_k": effective_date,
                "meal": meal_info or 'зі сніданку',
                "cause": 'СЗЧ',
                "action": 'виключити'  # Додаємо поле 'action' зі значенням 'виключити'
            }
            
            results.append(record)
            print(f"    >>> Successfully processed and appended SZCH record for: {person['rank']} {person['name']}")
    
    print(f"--- Exiting process_szch_section --- Total records: {len(results)} ---")
    return results


def find_szch_sections(text, rank_map):
    """
    Знаходить секції СЗЧ в тексті.
    
    Args:
        text (str): Текст документа
        rank_map (dict): Словник відповідності звань
        
    Returns:
        list: Список кортежів (тип_секції, текст_секції, початкова_позиція)
    """
    print("START find_szch_sections: Починаємо пошук СЗЧ секцій...")
    
    # Збільшуємо часове обмеження на виконання функції
    start_time = time.time()
    max_execution_time = 20  # Збільшуємо до 20 секунд
    
    sections = []
    # Для запобігання нескінченних циклів - зберігаємо позиції вже доданих секцій
    added_positions = set()
    
    # Отримуємо список всіх звань з rank_map
    ranks = list(rank_map.keys())
    
    # Розширюємо список ключових слів для кращого пошуку СЗЧ
    szch_keys = [
        "самовільним залишенням частини", 
        "самовільним залишенням лікувального закладу", 
        "самовільне залишення",
        "самовільно залишив",
        "самовільно залишивши",
        "залишенням частини", 
        "залишенням лікувального",
        "виключити з усіх видів забезпечення",
        "виключити з котлового забезпечення",
        "виключити зі всіх видів забезпечення",
        "виключити з забезпечення",
        "у зв'язку з самовільним",
        "вважати таким, що самовільно залишив"
    ]
    
    # Перевірка часового обмеження
    def time_limit_reached():
        elapsed = time.time() - start_time
        if elapsed > max_execution_time:
            print(f"WARNING: Time limit of {max_execution_time} seconds reached in find_szch_sections. Stopping search.")
            return True
        return False
    
    # Збільшуємо розмір тексту для пошуку
    max_search_length = 100000  # Збільшуємо максимальний розмір тексту для пошуку
    search_text = text[:min(len(text), max_search_length)]
    print(f"Searching for СЗЧ in the first {len(search_text)} characters of text")
    
    # 1. Спочатку шукаємо пронумеровані пункти, що починаються з числа, наприклад "2."
    numbered_points_pattern = r'(\d+)\.\s+' # Спрощений патерн: шукаємо тільки номер і крапку
    numbered_points = list(re.finditer(numbered_points_pattern, search_text))
    print(f"Found {len(numbered_points)} potential numbered points using pattern: '{numbered_points_pattern}'")
    
    # Перевіряємо кожен пронумерований пункт на наявність ключових слів СЗЧ
    for point_match in numbered_points:
        if time_limit_reached():
            print("Time limit reached during numbered points search")
            break
        
        point_num = point_match.group(1)
        point_start = point_match.start()
        
        # Пропускаємо вже оброблені позиції
        if point_start in added_positions:
            continue
        
        # Визначаємо межі пункту: до наступного пронумерованого пункту або максимум 2000 символів
        # Збільшуємо діапазон пошуку до 2500 символів для довших секцій
        next_point_search_start = point_match.end() # Починаємо пошук після поточного номера
        next_point_match = re.search(numbered_points_pattern, search_text[next_point_search_start:point_start + 2500])
        if next_point_match:
            point_end = next_point_search_start + next_point_match.start()
        else:
            point_end = min(point_start + 2000, len(search_text)) # Increased from 1500 to 2000
        
        point_text = search_text[point_start:point_end]
        
        # Перевіряємо чи містить цей пункт ключові слова СЗЧ
        contains_szch = False
        keyword_found_in_point = "None" # Debugging variable
        for key in szch_keys:
            if key in point_text.lower():
                contains_szch = True
                keyword_found_in_point = key
                break

        # Check more specific phrases
        phrase_found_in_point = "None" # Debugging variable
        if not contains_szch: # Only check if keyword wasn't already found
            # Додаємо більш загальні фрази для перевірки
            if re.search(r'виключити.{1,50}забезпеч', point_text.lower()):
                contains_szch = True
                phrase_found_in_point = "виключити ... забезпечення (pattern)"
            elif re.search(r'самовільн.{1,30}залиш', point_text.lower()):
                contains_szch = True
                phrase_found_in_point = "самовільне залишення (pattern)"

        # Check conscript conditions
        conscript_check_passed = False # Debugging variable
        if not contains_szch: # Only check if not already found
            if "за призовом" in point_text and (
                "самовільн" in point_text.lower() or
                "виключити" in point_text.lower() or
                "залишенн" in point_text.lower()):
                contains_szch = True
                conscript_check_passed = True
                
        # Додаткова перевірка для військовослужбовців
        military_personnel_check = False
        if not contains_szch and any(rank.lower() in point_text.lower() for rank in ranks):
            # Якщо знайдено військове звання та є ознаки СЗЧ
            if (re.search(r'з\s+(?:котлового|усіх|всіх).{1,20}забезпечення', point_text.lower()) or
                "виключити" in point_text.lower() and "забезпечення" in point_text.lower()):
                contains_szch = True
                military_personnel_check = True

        # Final decision for the point
        if contains_szch:
            sections.append(('СЗЧ', point_text, point_start))
            added_positions.add(point_start)
            print(f"Point {point_num}: Added SZCH section (keyword: {keyword_found_in_point or phrase_found_in_point})")
        else:
            # Detailed logging ONLY for points with potential indicators
            lower_text = point_text.lower()
            if ("виключити" in lower_text or 
                "самовільн" in lower_text or 
                "забезпечення" in lower_text and "виключ" in lower_text):
                print(f"--- POTENTIAL СЗЧ Point {point_num} but NOT matched ---")
                print(f"  Text snippet: {point_text[:150]}...")
                print(f"  Military personnel check: {military_personnel_check}")
                print(f"  Conscript check: {conscript_check_passed}")

    # Якщо не знайдено секції за номерами пунктів, шукаємо за розширеним набором ключових слів
    if not sections:
        print("No СЗЧ points found by number, performing thorough keyword search")
        
        # Шукаємо за розширеними ключовими фразами та паттернами СЗЧ
        for key in szch_keys:
            if time_limit_reached():
                break
                
            matches = list(re.finditer(key, search_text, re.IGNORECASE))
            print(f"Searching for key '{key}': found {len(matches)} occurrences")
            
            for match in matches:
                if time_limit_reached():
                    break
                    
                match_start = match.start()
                # Пропускаємо вже оброблені позиції
                if any(abs(pos - match_start) < 50 for pos in added_positions):
                    continue
                
                # Визначаємо контекст навколо ключового слова
                context_start = max(0, match_start - 500)  # Збільшуємо контекст до 500 символів
                context_end = min(len(search_text), match_start + 1500)  # Збільшуємо контекст після ключового слова
                
                # Шукаємо початок пункту перед ключовим словом
                context_before = search_text[context_start:match_start]
                point_match = re.search(r'(\d+)\.\s+', context_before)
                
                if point_match:
                    section_start = context_start + point_match.start()
                    # Шукаємо кінець секції
                    context_after = search_text[match_start:context_end]
                    next_point_match = re.search(r'\d+\.\s+', context_after)
                    
                    if next_point_match:
                        section_end = match_start + next_point_match.start()
                    else:
                        section_end = context_end
                else:
                    # Якщо не знайдено номер пункту, беремо контекст навколо ключового слова
                    section_start = context_start
                    section_end = context_end
                
                section_text = search_text[section_start:section_end]
                
                # Перевіряємо чи є в секції військові звання
                has_military_rank = any(rank.lower() in section_text.lower() for rank in ranks)
                
                if has_military_rank:
                    sections.append(('СЗЧ', section_text, section_start))
                    added_positions.add(section_start)
                    print(f"Found СЗЧ section by keyword '{key}' at position {section_start}")
                    print(f"  Section content begins with: {section_text[:100]}...")
    
    # Додатковий пошук за допомогою більш загальних регулярних виразів
    if len(sections) < 3:  # Якщо знайдено менше 3 секцій, спробуємо знайти додаткові
        print("Searching for additional СЗЧ sections using more general patterns")
        szch_patterns = [
            r'виключити\s+з\s+(?:усіх|всіх|котлового)\s+видів\s+забезпечення',
            r'самовільн[а-яіїєґ]+\s+залиш[а-яіїєґ]+',
            r'у\s+зв\'язку\s+з\s+самовільн[а-яіїєґ]+'
        ]
        
        for pattern in szch_patterns:
            if time_limit_reached() or len(sections) >= 10:  # Обмежуємо пошук до розумної кількості секцій
                break
                
            try:
                matches = list(re.finditer(pattern, search_text, re.IGNORECASE))
                print(f"Searching with pattern '{pattern}': found {len(matches)} occurrences")
                
                for match in matches:
                    match_start = match.start()
                    # Пропускаємо вже оброблені позиції
                    if any(abs(pos - match_start) < 100 for pos in added_positions):
                        continue
                    
                    # Визначаємо контекст навколо матчу
                    context_start = max(0, match_start - 500)
                    context_end = min(len(search_text), match_start + 1500)
                    section_text = search_text[context_start:context_end]
                    
                    # Перевіряємо чи є в секції військові звання
                    has_military_rank = any(rank.lower() in section_text.lower() for rank in ranks)
                    
                    if has_military_rank:
                        sections.append(('СЗЧ', section_text, context_start))
                        added_positions.add(context_start)
                        print(f"Found additional СЗЧ section with pattern '{pattern}' at position {context_start}")
            except Exception as e:
                print(f"Error while searching with pattern '{pattern}': {e}")

    elapsed_time = time.time() - start_time
    print(f"Total СЗЧ sections found: {len(sections)} (time: {elapsed_time:.2f} seconds)")
    
    # Додаємо вивід знайдених секцій для детальної діагностики
    for i, (section_type, section_text, pos) in enumerate(sections, 1):
        print(f"Section {i} starts with: {section_text[:100]}...")
        
    print("END find_szch_sections: Завершено пошук СЗЧ секцій")
    return sections 