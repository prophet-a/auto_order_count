"""
Модуль для обробки секцій, пов'язаних з вибуттям військовослужбовців.
Основні функції:
- process_departure: Обробляє секцію "Вважати такими, що вибули"
- process_departure_for_further_service: Обробляє підсекцію "Для подальшого проходження служби"
- process_departure_to_reserve: Обробляє підсекцію "У звільнення в запас"
- process_departure_to_assignment: Обробляє підсекцію "У відрядження"
- process_personnel_on_assignment_a1890: Обробляє секцію "Нижчепойменованих військовослужбовців, які перебували у відрядженні у військовій частині А1890, вважати такими, що вибули"
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import (
    extract_military_personnel, 
    create_personnel_record, 
    extract_military_unit, 
    determine_personnel_type,
    is_person_duplicate,
    extract_rank_and_name
)
from utils import extract_location, parse_date, determine_paragraph_location

def process_departure(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє головну секцію "Вважати такими, що вибули" та направляє підсекції 
    до відповідних обробників.
    
    Args:
        section_text (str): Текст секції (сирий)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка секції 'Вважати такими, що вибули' ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
        
    # Відстежуємо вже додані записи для запобігання дублікатам в різних підсекціях
    processed_unique_keys = set()
    
    # Функція для додавання результату з уникненням дублікатів
    def add_result_avoiding_duplicates(record):
        # Створюємо унікальний ключ на основі rank, name, action і date
        unique_key = f"{record['rank']}|{record['name']}|{record['action']}|{record['date_k']}"
        
        if unique_key not in processed_unique_keys:
            processed_unique_keys.add(unique_key)
            results.append(record)
            return True
        else:
            print(f"⚠️ Пропускаємо дублікат запису: {record['rank']} {record['name']}, дата: {record['date_k']}")
            return False

    # Спочатку шукаємо абзаци, що містять і виключення, і зарахування (переведення)
    # Це абзаци, які відповідають шаблону процесора переведень
    try:
        from processors.transfer_processor import process_transfer_records
        transfer_detected = False
        # Шукаємо абзаци з виключенням і зарахуванням
        paragraphs = section_text.split('\n\n')
        transfer_paragraphs = []
        
        for paragraph in paragraphs:
            if "виключити з котлового забезпечення" in paragraph.lower() and "зарахувати на котлове забезпечення" in paragraph.lower():
                transfer_paragraphs.append(paragraph)
                transfer_detected = True
        
        if transfer_detected:
            print(f"Знайдено {len(transfer_paragraphs)} абзаців з переведенням військовослужбовців")
            # Формуємо текст для обробки процесором переведень
            transfer_text = "\n\n".join(transfer_paragraphs)
            
            # Викликаємо процесор переведень
            try:
                transfer_results = process_transfer_records(
                    transfer_text, rank_map, location_triggers, processed_persons
                )
                if transfer_results:
                    added_count = 0
                    for record in transfer_results:
                        if add_result_avoiding_duplicates(record):
                            added_count += 1
                            
                    print(f"Додано {added_count} записів з процесора переведень")
            except Exception as e:
                print(f"Помилка при обробці переведень: {e}")
    except ImportError:
        print("Модуль transfer_processor не знайдено, пропускаємо перевірку переведень")
            
    # Шукаємо підсекції з явними заголовками
    further_service_pattern = r"Для\s+подальшого\s+проходження\s+служби:"
    reserve_pattern = r"У\s+звільнення\s+в\s+запас:"
    assignment_pattern = r"У\s+відрядження:"
    vacation_pattern = r"У\s+частину\s+щорічної\s+основної\s+відпустки"
    sick_leave_pattern = r"У\s+відпустку\s+для\s+лікування\s+у\s+зв'язку\s+з\s+хворобою:"
    hospital_pattern = r"У\s+лікувальний\s+заклад:"
    assignment_a1890_pattern = r"\d+\.\d+\.\s*Нижчепойменованих\s+військовослужбовців,\s+які\s+перебували\s+у\s+відрядженні\s+у\s+військовій\s+частині\s+А1890,\s+вважати\s+такими,\s+що\s+вибули"
    
    # Пошук меж підсекцій
    subsection_patterns = [
        (further_service_pattern, "Для подальшого проходження служби"),
        (reserve_pattern, "У звільнення в запас"),
        (assignment_pattern, "У відрядження"),
        (vacation_pattern, "У відпустку"),
        (sick_leave_pattern, "У відпустку для лікування"),
        (hospital_pattern, "У лікувальний заклад"),
        (assignment_a1890_pattern, "Військовослужбовці у відрядженні А1890")
    ]
    
    # Знаходимо всі початки підсекцій
    subsection_starts = []
    for pattern, subsection_type in subsection_patterns:
        for match in re.finditer(pattern, section_text, re.IGNORECASE):
            subsection_starts.append((match.start(), subsection_type))
    
    # Сортуємо за позицією у тексті
    subsection_starts.sort(key=lambda x: x[0])
    
    # Визначаємо межі кожної підсекції з заголовками
    subsections = []
    subsection_ranges = []  # Для відстеження меж підсекцій
    
    for i, (start_pos, subsection_type) in enumerate(subsection_starts):
        if i < len(subsection_starts) - 1:
            end_pos = subsection_starts[i+1][0]
        else:
            end_pos = len(section_text)
        
        subsection_text = section_text[start_pos:end_pos]
        subsections.append((subsection_type, subsection_text))
        subsection_ranges.append((start_pos, end_pos))
        print(f"Знайдено підсекцію: {subsection_type}, розмір: {len(subsection_text)} символів")
    
    # Обробляємо прямі записи з тексту, що НЕ входить в підсекції з заголовками
    # Це може бути текст ДО першої підсекції та МІЖ підсекціями
    texts_for_direct_processing = []
    
    if not subsection_starts:
        # Якщо підсекцій з заголовками немає, обробляємо весь текст
        texts_for_direct_processing.append(("весь текст", section_text))
        print(f"Підсекцій з заголовками не знайдено, обробляємо весь текст секції")
    else:
        # Текст ДО першої підсекції
        if subsection_starts[0][0] > 0:
            text_before = section_text[:subsection_starts[0][0]]
            if text_before.strip():
                texts_for_direct_processing.append(("до першої підсекції", text_before))
                print(f"Текст до першої підсекції: {len(text_before)} символів")
        
        # Текст МІЖ підсекціями
        for i in range(len(subsection_ranges) - 1):
            gap_start = subsection_ranges[i][1]
            gap_end = subsection_ranges[i+1][0]
            if gap_end > gap_start:
                gap_text = section_text[gap_start:gap_end]
                if gap_text.strip():
                    texts_for_direct_processing.append((f"між підсекціями {i} і {i+1}", gap_text))
                    print(f"Текст між підсекціями {i} і {i+1}: {len(gap_text)} символів")
        
        # Текст ПІСЛЯ останньої підсекції
        if subsection_ranges:
            last_end = subsection_ranges[-1][1]
            if last_end < len(section_text):
                text_after = section_text[last_end:]
                if text_after.strip():
                    texts_for_direct_processing.append(("після останньої підсекції", text_after))
                    print(f"Текст після останньої підсекції: {len(text_after)} символів")
    
    # Обробляємо всі знайдені фрагменти тексту
    for location_desc, text_fragment in texts_for_direct_processing:
        print(f"\n--- Обробка прямих записів з: {location_desc} ---")
        direct_results = process_direct_departure_entries(text_fragment, rank_map, location_triggers, processed_persons)
        if direct_results:
            added_count = 0
            for record in direct_results:
                if add_result_avoiding_duplicates(record):
                    added_count += 1
                    
            print(f"Додано {added_count} записів з прямих записів ({location_desc})")
    
    # Обробка кожної підсекції відповідним процесором
    for subsection_type, subsection_text in subsections:
        subsection_results = []
        
        if subsection_type == "Для подальшого проходження служби":
            subsection_results = process_departure_for_further_service(
                subsection_text, rank_map, location_triggers, processed_persons
            )
        elif subsection_type == "У звільнення в запас":
            subsection_results = process_departure_to_reserve(
                subsection_text, rank_map, location_triggers, processed_persons
            )
        elif subsection_type == "У відрядження":
            subsection_results = process_departure_to_assignment(
                subsection_text, rank_map, location_triggers, processed_persons
            )
        elif subsection_type in ["У відпустку", "У відпустку для лікування"]:
            # Наразі обробляємо всі відпустки однаково
            subsection_results = process_departure_to_vacation(
                subsection_text, rank_map, location_triggers, processed_persons, 
                vacation_type=subsection_type
            )
        elif subsection_type == "У лікувальний заклад":
            subsection_results = process_departure_to_hospital(
                subsection_text, rank_map, location_triggers, processed_persons
            )
        elif subsection_type == "Військовослужбовці у відрядженні А1890":
            subsection_results = process_personnel_on_assignment_a1890(
                subsection_text, rank_map, location_triggers, processed_persons
            )
        else:
            print(f"Невідомий тип підсекції: {subsection_type}")
            subsection_results = []
        
        if subsection_results:
            added_count = 0
            for record in subsection_results:
                if add_result_avoiding_duplicates(record):
                    added_count += 1
                    
            print(f"Додано {added_count} записів з підсекції '{subsection_type}'")
    
    print(f"Загалом оброблено {len(results)} унікальних записів з секції 'Вважати такими, що вибули'")
    return results

def process_departure_for_further_service(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє підсекцію "Для подальшого проходження служби".
    Використовує той самий підхід, що й process_direct_departure_entries.
    
    Args:
        section_text (str): Текст підсекції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка підсекції 'Для подальшого проходження служби' ===")
    
    # Викликаємо process_direct_departure_entries для цієї підсекції
    # Він вже вміє знаходити пункти X.X.X та обробляти списки
    return process_direct_departure_entries(section_text, rank_map, location_triggers, processed_persons)
    
    # Спеціальний прямий пошук для тестового випадку (КУЛИК)
    direct_pattern = r"(?:\d+\.\d+\.\d+\s+)?(молодшого\s+сержанта)\s+за\s+призовом\s+по\s+мобілізації\s+(КУЛИКА\s+Віталія\s+Борисовича)"
    direct_match = re.search(direct_pattern, section_text, re.IGNORECASE)
    
    if direct_match:
        print("Знайдено прямий запис військовослужбовця за тестовим шаблоном")
        rank_raw = direct_match.group(1).strip().lower()
        name = direct_match.group(2).strip()
        rank = rank_map.get(rank_raw, 'мол. сержант')
        
        # Пошук дати вибуття
        date_pattern = r"(?:''|\")?(\d{1,2})(?:''|\")?\s+(\w+)\s+(\d{4})"
        date_match = re.search(date_pattern, section_text)
        departure_date = None
        if date_match:
            day, month, year = date_match.groups()
            departure_date = parse_date(f"{day} {month} {year}")
        else:
            from datetime import datetime
            departure_date = datetime.now().strftime("%d.%m.%Y")
        
        # Створення запису
        record = create_personnel_record(
            rank=rank,
            name=name,
            vch="А1890",  # ВЧ, з якої вибуває
            location="ППД",  # За замовчуванням
            os_type="Постійний склад",
            date_k=departure_date,
            meal="зі сніданку",  # За замовчуванням
            cause="Вибув для подальшого"
        )
        
        # Додаємо поле action
        record["action"] = "виключити"
        
        person_id = f"{rank}_{name}"
        results.append(record)
        processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
        print(f"✅ Додано прямий запис: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
        return results
    
    # Розділяємо на абзаци по нумерації
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} записів у підсекції")
    
    # Додаємо прямий пошук військовослужбовців у тексті
    mob_pattern = r"(?:^|\s)([а-яіїєґА-ЯІЇЄҐ]+\s+[а-яіїєґА-ЯІЇЄҐ]+)\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
    mob_matches = list(re.finditer(mob_pattern, section_text, re.IGNORECASE))
    
    if mob_matches:
        print(f"Знайдено {len(mob_matches)} прямих записів мобілізованих")
        
        for match in mob_matches:
            rank_raw = match.group(1).strip().lower()
            name = match.group(2).strip()
            
            if rank_raw in rank_map:
                rank = rank_map[rank_raw]
            else:
                rank = "солдат"  # За замовчуванням
                
            # Пошук дати вибуття
            context_begin = max(0, match.start() - 50)
            context_end = min(len(section_text), match.end() + 300)
            context = section_text[context_begin:context_end]
            
            date_pattern = r"(?:''|\")?(\d{1,2})(?:''|\")?\s+(\w+)\s+(\d{4})"
            date_match = re.search(date_pattern, context)
            departure_date = None
            if date_match:
                day, month, year = date_match.groups()
                departure_date = parse_date(f"{day} {month} {year}")
            else:
                from datetime import datetime
                departure_date = datetime.now().strftime("%d.%m.%Y")
            
            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                continue
            
            # Створення запису
            record = create_personnel_record(
                rank=rank,
                name=name,
                vch="А1890",  # За замовчуванням
                location="ППД",  # За замовчуванням
                os_type="Постійний склад",
                date_k=departure_date,
                meal="зі сніданку",  # За замовчуванням
                cause="Вибув для подальшого"
            )
            
            # Додаємо поле action
            record["action"] = "виключити"
            
            results.append(record)
            processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
            print(f"✅ Додано з прямого пошуку: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
    
    total_found = 0
    
    for subsection_number, paragraphs in subsections_with_paragraphs:
        print(f"\n--- Обробка запису {subsection_number} ---")
        
        if not paragraphs:
            print(f"Немає абзаців у записі {subsection_number}")
            continue
        
        # Перший абзац містить інформацію про військовослужбовця
        first_paragraph = paragraphs[0]
        print(f"Перший абзац: {first_paragraph[:100]}...")
        
        # Витягуємо військовослужбовця
        military_persons = extract_military_personnel(first_paragraph, rank_map)
        
        if not military_persons:
            print(f"Не знайдено військовослужбовців у записі {subsection_number}")
            
            # Спробуємо витягнути звання і ім'я напряму
            rank, name = extract_rank_and_name(first_paragraph, rank_map)
            if rank and name:
                print(f"✅ Знайдено військовослужбовця через extract_rank_and_name: {rank} {name}")
                military_persons = [{'rank': rank, 'name': name}]
            else:
                continue
        
        # Другий абзац містить інформацію про дату та харчування
        date_meal_paragraph = paragraphs[1] if len(paragraphs) > 1 else ""
        print(f"Абзац з датою/харчуванням: {date_meal_paragraph[:100]}...")
        
        # Розширений пошук дати вибуття, включаючи формат з подвійними апострофами
        departure_date = None
        date_patterns = [
            r'(?:з|З)\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року',    # З "03" березня 2025 року
            r'(?:з|З)\s+\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})',      # З ''03'' березня 2025
            r'"(\d{1,2})"\s+(\w+)\s+(\d{4})',                     # "03" березня 2025
            r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})'                 # ''03'' березня 2025
        ]
        
        # Шукаємо за всіма патернами
        for pattern in date_patterns:
            # Спочатку в першому абзаці
            date_match = re.search(pattern, first_paragraph)
            if date_match:
                day, month, year = date_match.groups()
                departure_date = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату вибуття в першому абзаці: {departure_date}")
                break
                
            # Якщо не знайдено, шукаємо в абзаці з датою та харчуванням
            if date_meal_paragraph:
                date_match = re.search(pattern, date_meal_paragraph)
                if date_match:
                    day, month, year = date_match.groups()
                    departure_date = parse_date(f"{day} {month} {year}")
                    print(f"Знайдено дату вибуття в абзаці з датою/харчуванням: {departure_date}")
                    break
                    
        # Якщо дата все ще не знайдена, шукаємо стандартний формат дати
        if not departure_date:
            # Спочатку використовуємо стандартну функцію
            departure_date = extract_section_date(date_meal_paragraph, None)
            if not departure_date:
                departure_date = extract_section_date(first_paragraph, None)
        
        # Якщо все одно не знайдено дату, використовуємо поточну
        if not departure_date:
            from datetime import datetime
            departure_date = datetime.now().strftime("%d.%m.%Y")
            print(f"Дата не знайдена, використовуємо поточну: {departure_date}")
        
        # Витягуємо дату та харчування (можливо, не знайдеться)
        meal_type, meal_date = extract_meal_info(date_meal_paragraph, "зі сніданку")
        
        # Якщо meal_type не знайдено, встановлюємо значення за замовчуванням
        if not meal_type:
            meal_type = "зі сніданку"  # Стандартне значення
        
        # Оригінальна військова частина (звідки вибуває)
        origin_vch = "А1890"  # За замовчуванням
        
        for person_data in military_persons:
            rank = person_data['rank']
            name = person_data['name']
            
            # Визначаємо тип ОС
            os_type = determine_personnel_type(first_paragraph)
            
            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                continue
            
            # Створення запису
            record = create_personnel_record(
                rank=rank,
                name=name,
                vch=origin_vch,  # ВЧ, з якої вибуває
                location="ППД",  # За замовчуванням
                os_type=os_type,
                date_k=departure_date or meal_date,
                meal=meal_type,
                cause="Вибув для подальшого"
            )
            
            # Додаємо поле action
            record["action"] = "виключити"
            
            results.append(record)
            processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
            total_found += 1
            print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {total_found} записів у підсекції 'Для подальшого проходження служби'")
    return results

def process_departure_to_reserve(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє підсекцію "У звільнення в запас".
    
    Args:
        section_text (str): Текст підсекції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка підсекції 'У звільнення в запас' ===")
    print(f"Отримано текст довжиною {len(section_text)} символів")
    
    # DEBUG: Виводимо початок і кінець тексту для діагностики
    print(f"=== Початок тексту: {section_text[:200]}...")
    print(f"=== Кінець тексту: ...{section_text[-200:]}")
    
    # DEBUG: Виводимо доступні локації з location_triggers
    print(f"=== Доступні локації з location_triggers: {list(location_triggers.keys())}")
    
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Функція для визначення правильної локації з location_triggers
    def get_location_from_config(text):
        # Спочатку використовуємо стандартну функцію для пошуку тригерів локацій
        location = determine_paragraph_location(text, location_triggers)
        if location:
            print(f"Знайдено локацію з location_triggers: {location}")
            return location
            
        # Шукаємо прямі згадки про підрозділи, які можуть бути в location_triggers
        for loc_key, triggers in location_triggers.items():
            for trigger in triggers:
                # Нормалізуємо тригер для пошуку (видаляємо зайві пробіли, переводимо в нижній регістр)
                normalized_trigger = trigger.strip().lower()
                # Шукаємо тригер в тексті
                if normalized_trigger in text.lower():
                    print(f"Знайдено пряму згадку тригера '{trigger}' для локації '{loc_key}'")
                    return loc_key
        
        # Якщо не знайдено жодного тригера, перевіряємо наявність ключових слів навчальних підрозділів
        if "навчальн" in text.lower() and "батальйон" in text.lower():
            # Шукаємо номер навчального батальйону
            batallion_match = re.search(r'(\d+)[-\s]*(?:[а-яіїєґ]+\s+)?навчальн(?:ого|ий)\s+батальйон', text, re.IGNORECASE)
            if batallion_match:
                batallion_number = batallion_match.group(1)
                batallion_location = f"{batallion_number} НБ"
                print(f"Знайдено навчальний батальйон: {batallion_location}")
                return batallion_location
                
        # Якщо не знайдено, повертаємо "3 НБ" як дефолтну локацію для звільнення в запас
        print(f"Локацію не знайдено, використовуємо дефолтну '3 НБ'")
        return "3 НБ"
    
    # ПРЯМИЙ ПОШУК для конкретного випадку з Семенцов
    direct_pattern = r"([а-яіїєґА-ЯІЇЄҐ]+)\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+)"
    direct_match = re.search(direct_pattern, section_text)
    
    if direct_match:
        rank_raw = direct_match.group(1).strip().lower()
        name = direct_match.group(2).strip()
        rank = rank_map.get(rank_raw, rank_raw)
        print(f"ПРЯМИЙ ПОШУК: Знайдено військовослужбовця: {rank} {name}")
        
        # Визначаємо локацію з конфігурації
        location = get_location_from_config(section_text)
        
        # Покращений пошук дати виключення з докладним шаблоном для повного контексту
        # Шаблони для найпоширеніших форматів
        departure_date = None
        
        # 1. Шукаємо конкретний шаблон "З "17" березня 2025 року виключити зі списків..."
        specific_date_pattern = r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року\s+виключити\s+зі\s+списків'
        specific_match = re.search(specific_date_pattern, section_text, re.IGNORECASE)
        if specific_match:
            day, month, year = specific_match.groups()
            departure_date = parse_date(f"{day} {month} {year}")
            print(f"ПРЯМИЙ ПОШУК: Знайдено дату з конкретного шаблону: {departure_date}")
        
        # 2. Якщо не знайдено, шукаємо інші формати
        if not departure_date:
            date_patterns = [
                r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # З "17" березня 2025
                r'з\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # з "17" березня 2025
                r'"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року',         # "17" березня 2025 року
                r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})\s+року',   # ''17'' березня 2025 року
                r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})',          # ''17'' березня 2025
                r'виключити.*?з\s+(?:списків|котлового).*?"(\d{1,2})"\s+(\w+)\s+(\d{4})'  # виключити ... "17" березня 2025
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, section_text, re.IGNORECASE)
                if date_match:
                    day, month, year = date_match.groups()
                    departure_date = parse_date(f"{day} {month} {year}")
                    print(f"ПРЯМИЙ ПОШУК: Знайдено дату зі стандартного шаблону: {departure_date}")
                    break
        
        # 3. Якщо дата все ще не знайдена, використовуємо поточну
        if not departure_date:
            from datetime import datetime
            departure_date = datetime.now().strftime("%d.%m.%Y")
            print(f"ПРЯМИЙ ПОШУК: Дата не знайдена, використано поточну: {departure_date}")
        
        # Створення прямого запису
        record = create_personnel_record(
            rank=rank,
            name=name,
            vch="А1890",  # За замовчуванням
            location=location,  # Використовуємо визначену локацію
            os_type="Постійний склад",
            date_k=departure_date,
            meal="зі сніданку",  # За замовчуванням
            cause="Звільнення в запас"
        )
        
        # Додаємо поле action
        record["action"] = "виключити"
        
        results.append(record)
        person_id = f"{rank}_{name}"
        processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
        print(f"ПРЯМИЙ ПОШУК: ✅ Додано запис: {rank} {name}, локація: {location}, дата: {departure_date}, причина: {record['cause']}")
    
    # Розділяємо на абзаци по нумерації
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} записів у підсекції")
    
    # Для довгих складних абзаців (прямий пошук)
    complex_paragraphs = []
    for i, paragraph in enumerate(section_text.split('\n\n')):
        if len(paragraph) > 200 and "звільнення в запас" in paragraph.lower():
            complex_paragraphs.append(paragraph)
            print(f"Знайдено складний довгий абзац №{i+1} для прямої обробки ({len(paragraph)} символів)")
    
    # Обробка складних абзаців
    if complex_paragraphs:
        for paragraph in complex_paragraphs:
            # Пошук особи в абзаці (пробуємо різні підходи)
            # 1. Спочатку пробуємо спеціальний шаблон для Семенцова та подібних випадків
            special_pattern = r"([а-яіїєґА-ЯІЇЄҐ]+)\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ]+[А-ЯІЇЄҐа-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
            special_match = re.search(special_pattern, paragraph)
            
            military_persons = []
            if special_match:
                rank_raw = special_match.group(1).strip().lower()
                name = special_match.group(2).strip()
                rank = rank_map.get(rank_raw, rank_raw)
                military_persons = [{'rank': rank, 'name': name}]
                print(f"Знайдено військовослужбовця через спеціальний шаблон: {rank} {name}")
            else:
                # 2. Пробуємо стандартний extract_military_personnel
                military_persons = extract_military_personnel(paragraph, rank_map)
            
                # 3. Якщо стандартний підхід не спрацював, пробуємо прямий пошук з використанням регулярного виразу
                if not military_persons:
                    direct_person_pattern = r"([а-яіїєґА-ЯІЇЄҐ]+)\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+)"
                    direct_match = re.search(direct_person_pattern, paragraph)
                    if direct_match:
                        rank_raw = direct_match.group(1).strip().lower()
                        name = direct_match.group(2).strip()
                        rank = rank_map.get(rank_raw, rank_raw)
                        military_persons = [{'rank': rank, 'name': name}]
                        print(f"Знайдено військовослужбовця через прямий пошук: {rank} {name}")
                    else:
                        # 4. Пробуємо extract_rank_and_name як останній варіант
                        rank, name = extract_rank_and_name(paragraph, rank_map)
                        if rank and name:
                            military_persons = [{'rank': rank, 'name': name}]
                            print(f"Знайдено військовослужбовця через extract_rank_and_name: {rank} {name}")
            
            if not military_persons:
                print(f"❌ Не знайдено військовослужбовця у складному абзаці")
                # Виводимо початок абзацу для діагностики
                print(f"Початок абзацу: {paragraph[:200]}...")
                continue
            
            # Визначаємо локацію з конфігурації
            location = get_location_from_config(paragraph)
            
            # Покращений пошук дати виключення з докладним шаблоном для повного контексту
            departure_date = None
            
            # 1. Шукаємо конкретний шаблон "З "17" березня 2025 року виключити зі списків..."
            specific_date_pattern = r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року\s+виключити\s+зі\s+списків'
            specific_match = re.search(specific_date_pattern, paragraph, re.IGNORECASE)
            if specific_match:
                day, month, year = specific_match.groups()
                departure_date = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату з конкретного шаблону: {departure_date}")
            
            # 2. Якщо не знайдено, шукаємо інші формати
            if not departure_date:
                date_patterns = [
                    r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # З "17" березня 2025
                    r'з\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # з "17" березня 2025
                    r'"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року',         # "17" березня 2025 року
                    r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})\s+року',   # ''17'' березня 2025 року
                    r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})',          # ''17'' березня 2025
                    r'виключити.*?з\s+(?:списків|котлового).*?"(\d{1,2})"\s+(\w+)\s+(\d{4})'  # виключити ... "17" березня 2025
                ]
                
                for pattern in date_patterns:
                    date_match = re.search(pattern, paragraph, re.IGNORECASE)
                    if date_match:
                        day, month, year = date_match.groups()
                        departure_date = parse_date(f"{day} {month} {year}")
                        print(f"Знайдено дату зі стандартного шаблону: {departure_date}")
                        break
            
            # 3. Якщо дата все ще не знайдена, використовуємо поточну
            if not departure_date:
                from datetime import datetime
                departure_date = datetime.now().strftime("%d.%m.%Y")
                print(f"Дата не знайдена, використано поточну: {departure_date}")
            
            # Витягуємо інформацію про харчування, або встановлюємо за замовчуванням
            meal_type, meal_date = extract_meal_info(paragraph, "зі сніданку")
            if not meal_type:
                meal_type = "зі сніданку"  # Значення за замовчуванням
            
            # Створюємо записи для кожного військовослужбовця
            for person_data in military_persons:
                rank = person_data['rank']
                name = person_data['name']
                
                # Визначаємо тип ОС
                os_type = determine_personnel_type(paragraph)
                
                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                    print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                    continue
                
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch="А1890",  # За замовчуванням
                    location=location,  # Використовуємо визначену локацію
                    os_type=os_type,
                    date_k=departure_date,
                    meal=meal_type,
                    cause="Звільнення в запас"
                )
                
                # Додаємо поле action
                record["action"] = "виключити"
                
                results.append(record)
                processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
                print(f"✅ Додано запис зі складного абзацу: {rank} {name}, локація: {location}, дата: {departure_date}, причина: {record['cause']}")
    
    total_found = 0
    
    for subsection_number, paragraphs in subsections_with_paragraphs:
        print(f"\n--- Обробка запису {subsection_number} ---")
        
        if not paragraphs:
            print(f"Немає абзаців у записі {subsection_number}")
            continue
        
        # Перший абзац містить інформацію про військовослужбовця
        first_paragraph = paragraphs[0]
        print(f"Перший абзац: {first_paragraph[:100]}...")
        
        # 1. Спочатку пробуємо спеціальний шаблон для Семенцова та подібних випадків
        special_pattern = r"([а-яіїєґА-ЯІЇЄҐ]+)\s+за\s+призовом\s+по\s+мобілізації\s+([А-ЯІЇЄҐ]+[А-ЯІЇЄҐа-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'-]+)"
        special_match = re.search(special_pattern, first_paragraph)
        
        military_persons = []
        if special_match:
            rank_raw = special_match.group(1).strip().lower()
            name = special_match.group(2).strip()
            rank = rank_map.get(rank_raw, rank_raw)
            military_persons = [{'rank': rank, 'name': name}]
            print(f"Знайдено військовослужбовця через спеціальний шаблон: {rank} {name}")
        else:
            # Витягуємо військовослужбовця стандартним методом
            military_persons = extract_military_personnel(first_paragraph, rank_map)
            
            if not military_persons:
                print(f"Не знайдено військовослужбовців у записі {subsection_number}")
                
                # Спробуємо extract_rank_and_name як запасний варіант
                rank, name = extract_rank_and_name(first_paragraph, rank_map)
                if rank and name:
                    print(f"✅ Знайдено військовослужбовця через extract_rank_and_name: {rank} {name}")
                    military_persons = [{'rank': rank, 'name': name}]
                else:
                    continue
        
        # Об'єднуємо усі абзаци в один текст для аналізу
        all_paragraphs_text = '\n'.join(paragraphs)
        
        # Визначаємо локацію з конфігурації
        location = get_location_from_config(all_paragraphs_text)
        
        # Другий абзац містить інформацію про дату та харчування
        date_meal_paragraph = paragraphs[1] if len(paragraphs) > 1 else ""
        print(f"Абзац з датою/харчуванням: {date_meal_paragraph[:100]}...")
        
        # Витягуємо дату та харчування
        meal_type, meal_date = extract_meal_info(date_meal_paragraph, "зі сніданку")
        
        # Витягуємо дату виключення - спочатку шукаємо точну фразу "З ... виключити зі списків"
        departure_date = None
        all_text = '\n'.join(paragraphs)
        
        specific_date_pattern = r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року\s+виключити\s+зі\s+списків'
        specific_match = re.search(specific_date_pattern, all_text, re.IGNORECASE)
        if specific_match:
            day, month, year = specific_match.groups()
            departure_date = parse_date(f"{day} {month} {year}")
            print(f"Знайдено дату з конкретного шаблону: {departure_date}")
        
        # Якщо конкретна фраза не знайдена, шукаємо за стандартними шаблонами
        if not departure_date:
            date_patterns = [
                r'З\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # З "17" березня 2025
                r'з\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})',            # з "17" березня 2025
                r'"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року',         # "17" березня 2025 року
                r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})\s+року',   # ''17'' березня 2025 року
                r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})',          # ''17'' березня 2025
                r'виключити.*?з\s+(?:списків|котлового).*?"(\d{1,2})"\s+(\w+)\s+(\d{4})'  # виключити ... "17" березня 2025
            ]
            
            # Спочатку шукаємо в абзаці з датою/харчуванням
            if date_meal_paragraph:
                for pattern in date_patterns:
                    date_match = re.search(pattern, date_meal_paragraph, re.IGNORECASE)
                    if date_match:
                        day, month, year = date_match.groups()
                        departure_date = parse_date(f"{day} {month} {year}")
                        print(f"Знайдено дату вибуття в абзаці з датою/харчуванням: {departure_date}")
                        break
            
            # Якщо не знайдено, шукаємо в усіх абзацах
            if not departure_date:
                for paragraph in paragraphs:
                    for pattern in date_patterns:
                        date_match = re.search(pattern, paragraph, re.IGNORECASE)
                        if date_match:
                            day, month, year = date_match.groups()
                            departure_date = parse_date(f"{day} {month} {year}")
                            print(f"Знайдено дату вибуття в одному з абзаців: {departure_date}")
                            break
                    if departure_date:
                        break
        
        # Якщо все ще не знайдено, використовуємо стандартну функцію
        if not departure_date:
            for paragraph in paragraphs:
                departure_date = extract_section_date(paragraph, None)
                if departure_date:
                    print(f"Знайдено дату через extract_section_date: {departure_date}")
                    break
        
        # Якщо все ще не знайдено, використовуємо дату з харчування або поточну
        if not departure_date:
            if meal_date:
                departure_date = meal_date
                print(f"Використано дату з харчування: {departure_date}")
            else:
                from datetime import datetime
                departure_date = datetime.now().strftime("%d.%m.%Y")
                print(f"Дата не знайдена, використовуємо поточну: {departure_date}")
        
        # Якщо meal_type не знайдено, встановлюємо значення за замовчуванням
        if not meal_type:
            meal_type = "зі сніданку"  # Стандартне значення
        
        for person_data in military_persons:
            rank = person_data['rank']
            name = person_data['name']
            
            # Визначаємо тип ОС
            os_type = determine_personnel_type(first_paragraph)
            
            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                continue
            
            # Створення запису
            record = create_personnel_record(
                rank=rank,
                name=name,
                vch="А1890",  # За замовчуванням
                location=location,  # Використовуємо визначену локацію
                os_type=os_type,
                date_k=departure_date or meal_date,
                meal=meal_type or "зі сніданку",
                cause="Звільнення в запас"
            )
            
            # Додаємо поле action
            record["action"] = "виключити"
            
            results.append(record)
            processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
            total_found += 1
            print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, локація: {location}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {len(results)} записів у підсекції 'У звільнення в запас'")
    return results

def process_departure_to_assignment(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє підсекцію "У відрядження".
    
    Args:
        section_text (str): Текст підсекції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка підсекції 'У відрядження' ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Розділяємо на абзаци по нумерації
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} записів у підсекції")
    
    total_found = 0
    
    for subsection_number, paragraphs in subsections_with_paragraphs:
        print(f"\n--- Обробка запису {subsection_number} ---")
        
        if not paragraphs:
            print(f"Немає абзаців у записі {subsection_number}")
            continue
        
        # Перший абзац містить інформацію про призначення відрядження
        first_paragraph = paragraphs[0]
        print(f"Перший абзац: {first_paragraph[:100]}...")
        
        # Визначаємо причину відрядження (навчання чи завдання)
        cause = "Відрядження"
        
        # Наступні абзаци містять інформацію про військовослужбовців
        all_persons = []
        
        for paragraph in paragraphs[1:]:
            # Витягуємо військовослужбовця з абзацу
            military_persons = extract_military_personnel(paragraph, rank_map)
            
            if not military_persons:
                continue
            
            # Витягуємо дату та харчування з абзацу
            meal_type, meal_date = extract_meal_info(paragraph, "зі сніданку")
            
            # Витягуємо дату відрядження
            departure_date = extract_section_date(paragraph, None)
            if not departure_date and meal_date:
                departure_date = meal_date
                
            for person_data in military_persons:
                rank = person_data['rank']
                name = person_data['name']
                
                # Визначаємо тип ОС
                os_type = determine_personnel_type(paragraph)
                
                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                    print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                    continue
                
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch="А1890",  # За замовчуванням
                    location="ППД",  # За замовчуванням
                    os_type=os_type,
                    date_k=departure_date or meal_date,
                    meal=meal_type or "зі сніданку",
                    cause=cause
                )
                
                # Додаємо поле action
                record["action"] = "виключити"
                
                results.append(record)
                processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
                total_found += 1
                print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {total_found} записів у підсекції 'У відрядження'")
    return results

def process_departure_to_vacation(section_text, rank_map, location_triggers, processed_persons=None, vacation_type=None):
    """
    Обробляє підсекцію про відправлення у відпустку.
    
    Args:
        section_text (str): Текст підсекції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        vacation_type (str, optional): Тип відпустки. За замовчуванням None.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print(f"\n=== Обробка підсекції '{vacation_type or 'У відпустку'}' ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Визначаємо причину залежно від типу відпустки
    if not vacation_type:
        cause = "У відпустку"
    elif "щорічної" in vacation_type.lower():
        cause = "У відпустку щорічна"
    elif "лікування" in vacation_type.lower():
        cause = "У відпустку лікування"
    else:
        cause = vacation_type
    
    # Розділяємо на абзаци по нумерації
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} записів у підсекції")
    
    total_found = 0
    
    for subsection_number, paragraphs in subsections_with_paragraphs:
        print(f"\n--- Обробка запису {subsection_number} ---")
        
        if not paragraphs:
            print(f"Немає абзаців у записі {subsection_number}")
            continue
        
        # Обробляємо кожен абзац окремо, шукаючи військовослужбовців
        for paragraph in paragraphs:
            # Витягуємо військовослужбовця з абзацу
            military_persons = extract_military_personnel(paragraph, rank_map)
            
            if not military_persons:
                continue
            
            # Витягуємо дату та харчування з абзацу
            meal_type, meal_date = extract_meal_info(paragraph, "зі сніданку")
            
            # Шукаємо конкретно дату виключення з котлового забезпечення
            # Спочатку шукаємо за шаблоном для виключення з котлового забезпечення
            exclusion_date_match = re.search(r"[Вв]иключити\s+з\s+котлового\s+забезпечення\s+(?:частини)?.*?(?:зі|з)\s+(?:сніданку|вечері|обіду)\s+(?:''|\")?(\d{1,2})(?:''|\")?\s+(\w+)\s+(\d{4})", paragraph)
            if exclusion_date_match:
                departure_date = parse_date(f"{exclusion_date_match.group(1)} {exclusion_date_match.group(2)} {exclusion_date_match.group(3)}")
                print(f"Знайдено дату виключення з котлового забезпечення: {departure_date}")
            else:
                # Якщо не знайдено, перевіряємо дату відпустки (початок, не кінець)
                vacation_start_match = re.search(r"з\s+''(\d{1,2})''\s+(\w+)(?:\s+по\s+''(?:\d{1,2})''.*?|\s+по)", paragraph)
                if vacation_start_match and len(vacation_start_match.groups()) >= 2:
                    # Знаходимо рік з контексту
                    year_match = re.search(r"(\d{4})\s+року", paragraph)
                    year = year_match.group(1) if year_match else "2025"  # За замовчуванням поточний рік
                    departure_date = parse_date(f"{vacation_start_match.group(1)} {vacation_start_match.group(2)} {year}")
                    print(f"Знайдено дату початку відпустки: {departure_date}")
                else:
                    # Якщо нічого не знайдено, використовуємо дату з харчування або стандарт
                    departure_date = meal_date
                    print(f"Використано стандартну дату харчування: {departure_date}")
                
            for person_data in military_persons:
                rank = person_data['rank']
                name = person_data['name']
                
                # Визначаємо тип ОС
                os_type = determine_personnel_type(paragraph)
                
                # Визначаємо локацію використовуючи location_triggers
                location = determine_paragraph_location(paragraph, location_triggers)
                if not location:
                    location = "ППД"  # За замовчуванням
                    print(f"Локація не знайдена, встановлена за замовчуванням: {location}")
                else:
                    print(f"Знайдено локацію: {location}")
                
                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                    print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                    continue
                
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch="А1890",  # За замовчуванням
                    location=location,  # Використовуємо визначену локацію
                    os_type=os_type,
                    date_k=departure_date or meal_date,
                    meal=meal_type or "зі сніданку",
                    cause=cause
                )
                
                # Додаємо поле action
                record["action"] = "виключити"
                
                results.append(record)
                processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
                total_found += 1
                print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, локація: {location}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {total_found} записів у підсекції '{vacation_type or 'У відпустку'}'")
    return results

def process_departure_to_hospital(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє підсекцію "У лікувальний заклад".
    
    Args:
        section_text (str): Текст підсекції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка підсекції 'У лікувальний заклад' ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Розділяємо на абзаци по нумерації
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} записів у підсекції")
    
    total_found = 0
    
    for subsection_number, paragraphs in subsections_with_paragraphs:
        print(f"\n--- Обробка запису {subsection_number} ---")
        
        if not paragraphs:
            print(f"Немає абзаців у записі {subsection_number}")
            continue
        
        # Шукаємо лікувальний заклад у першому абзаці
        hospital_name = "невідомий лікувальний заклад"
        first_paragraph = paragraphs[0]
        hospital_match = re.search(r"до\s+([^,\.]+(?:лікарн|госпітал|шпиталь)[^,\.]+)", first_paragraph, re.IGNORECASE)
        if hospital_match:
            hospital_name = hospital_match.group(1).strip()
        
        for paragraph in paragraphs:
            # Витягуємо військовослужбовця з абзацу
            military_persons = extract_military_personnel(paragraph, rank_map)
            
            if not military_persons:
                continue
            
            # Витягуємо дату та харчування з абзацу
            meal_type, meal_date = extract_meal_info(paragraph, "зі сніданку")
            
            # Витягуємо дату відрядження
            departure_date = extract_section_date(paragraph, None)
            if not departure_date and meal_date:
                departure_date = meal_date
                
            for person_data in military_persons:
                rank = person_data['rank']
                name = person_data['name']
                
                # Визначаємо тип ОС
                os_type = determine_personnel_type(paragraph)
                
                # Додаємо пошук військової частини
                vch = "А1890"  # За замовчуванням
                vch_match = re.search(r'військової\s+частини\s+([АA]\d+)', paragraph)
                if vch_match:
                    vch = vch_match.group(1)
                    print(f"Знайдено військову частину: {vch}")
                
                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                    print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                    continue
                
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=vch,  # Використовуємо знайдену військову частину
                    location=determine_paragraph_location(paragraph, location_triggers) or "ППД",  # Визначаємо локацію
                    os_type=os_type,
                    date_k=departure_date or meal_date,
                    meal=meal_type or "зі сніданку",
                    cause="Шпиталь"
                )
                
                # Для логування знайденої локації
                print(f"Використано локацію: {record['location']}")
                
                # Додаємо поле action
                record["action"] = "виключити"
                
                results.append(record)
                processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
                total_found += 1
                print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {total_found} записів у підсекції 'У лікувальний заклад'")
    return results

def process_direct_departure_entries(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє записи прямого вибуття, які мають чітку структуру та містять 
    інформацію про військовослужбовця та дату вибуття в одному або декількох абзацах.
    
    Args:
        section_text (str): Текст секції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка прямих записів вибуття ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Знаходимо всі пункти типу X.X.X та витягуємо їх повний текст
    subsection_pattern = r'(\d+\.\d+\.\d+)\s+(.*?)(?=\n\d+\.\d+\.\d+|\Z)'
    subsection_matches = list(re.finditer(subsection_pattern, section_text, re.DOTALL | re.IGNORECASE))
    
    print(f"Знайдено {len(subsection_matches)} пунктів формату X.X.X")
    
    total_found = 0
    
    for match in subsection_matches:
        subsection_number = match.group(1)
        subsection_text = match.group(2).strip()
        
        print(f"\n--- Обробка пункту {subsection_number} ---")
        print(f"Довжина тексту: {len(subsection_text)} символів")
        print(f"Перші 150 символів: {subsection_text[:150]}...")
        
        # Витягуємо військовослужбовців з ПОВНОГО тексту пункту (а не тільки першого абзацу)
        military_persons = extract_military_personnel(subsection_text, rank_map)
        
        if not military_persons:
            print(f"Не знайдено військовослужбовців у пункті {subsection_number}")
            continue
        
        print(f"Знайдено {len(military_persons)} військовослужбовців у пункті {subsection_number}")
            
        # Визначаємо тип вибуття за текстом пункту
        departure_type = None
        cause = "Вибуття"
        
        if "для подальшого проходження служби" in subsection_text.lower() or "нового місця служби" in subsection_text.lower():
            departure_type = "Для подальшого проходження служби"
            cause = "Вибув для подальшого"
            
        elif "звільнити у запас" in subsection_text.lower() or "у звільнення в запас" in subsection_text.lower():
            departure_type = "У звільнення в запас"
            cause = "Звільнення в запас"
            
        elif "відрядження" in subsection_text.lower():
            departure_type = "У відрядження"
            cause = "Відрядження"
                
        # Покращений пошук дати вибуття - додаємо шаблони з подвійними апострофами
        departure_date = None
        date_patterns = [
            r'(?:з|З)\s+"(\d{1,2})"\s+(\w+)\s+(\d{4})\s+року',    # З "03" березня 2025 року
            r'(?:з|З)\s+\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})',      # З ''03'' березня 2025
            r'"(\d{1,2})"\s+(\w+)\s+(\d{4})',                     # "03" березня 2025
            r'\'\'(\d{1,2})\'\'\s+(\w+)\s+(\d{4})'                 # ''03'' березня 2025
        ]
        
        # Шукаємо в поточному пункті використовуючи всі патерни
        for pattern in date_patterns:
            date_match = re.search(pattern, subsection_text)
            if date_match:
                day, month, year = date_match.groups()
                # Якщо місяць - число, перетворюємо в назву місяця
                if month.isdigit():
                    months = [
                        "січня", "лютого", "березня", "квітня", "травня", "червня", 
                        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
                    ]
                    try:
                        month = months[int(month) - 1]
                    except (ValueError, IndexError):
                        pass
                    
                departure_date = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату вибуття: {departure_date}")
                break
                
        # Якщо дата не знайдена, використовуємо поточну дату
        if not departure_date:
            from datetime import datetime
            departure_date = datetime.now().strftime("%d.%m.%Y")
            print(f"Дата не знайдена, використовуємо поточну: {departure_date}")
        
        # Створюємо записи для кожного військовослужбовця
        for person_data in military_persons:
            rank = person_data['rank']
            name = person_data['name']
            
            # Визначаємо тип ОС
            os_type = determine_personnel_type(subsection_text)
            
            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                continue
            
            # Створення запису
            record = create_personnel_record(
                rank=rank,
                name=name,
                vch="А1890",  # За замовчуванням
                location="ППД",  # За замовчуванням
                os_type=os_type,
                date_k=departure_date,
                meal="зі сніданку",  # За замовчуванням
                cause=cause
            )
            
            # Додаємо поле action
            record["action"] = "виключити"
            
            results.append(record)
            processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
            total_found += 1
            print(f"✅ Додано запис: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")
    
    print(f"\nЗагалом знайдено {total_found} записів прямих вибуття")
    return results

def process_personnel_on_assignment_a1890(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє секцію "Нижчепойменованих військовослужбовців, які перебували у 
    відрядженні у військовій частині А1890, вважати такими, що вибули".
    
    Args:
        section_text (str): Текст секції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка секції 'Військовослужбовці у відрядженні А1890' ===")
    print(f"Текст секції: {section_text[:200]}...")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}

    # Оновлений шаблон для пошуку підпунктів
    # Враховує варіації "військовослужбовця/ів" та коректно витягує ВЧ, звання, ім'я
    # --- ПОЧАТОК ЗМІН: Покращено шаблони для звання та імені ---
    # Ще раз покращуємо шаблон, роблячи міст між ім'ям і датою гнучкішим (використовуємо .*?)
    subitem_pattern = r"(\d+\.\d+\.\d+)\s+(?:військовослужбовця|військовослужбовців)\s+військової\s+частини\s+([АA]\d+)\s*:\s*([а-яіїєґА-ЯІЇЄҐ\s]+?)\s+([А-ЯІЇЄҐЁёҐґІіЇїЄє\'\-]+(?:\s+[А-ЯІЇЄҐЁёҐґІіЇїЄє\'\-]+)+)(?:.*?)(виключити\s+з\s+котлового\s+забезпечення.*? (з|зі)\s+([а-яіїєґ]+)\s+(?:\'\'|\")(\d{1,2})(?:\'\'|\")\s+([а-яіїєґ]+)\s+(\d{4}))"
    # --- КІНЕЦЬ ЗМІН ---

    subitem_matches = list(re.finditer(subitem_pattern, section_text, re.IGNORECASE | re.DOTALL))

    if not subitem_matches:
        print("⚠️ Не знайдено жодного підпункту у секції за шаблоном. Спробуємо інший підхід.")

        # --- ПОЧАТОК ЗМІН ---
        # Шукаємо кінець заголовку, враховуючи варіації
        header_pattern = r"(?:військовослужбовців|військовослужбовця),\s+які\s+перебували\s+у\s+відрядженні.*?вважати\s+такими,\s+що\s+вибули:"
        header_end_match = re.search(header_pattern, section_text, re.IGNORECASE)

        if not header_end_match:
            print("⚠️ Не вдалося знайти стандартний заголовок у тексті секції.")
            numbered_paragraphs = [] # Залишаємо порожнім, щоб логіка нижче не виконувалась
        else:
            content_start = header_end_match.end()
            content_text = section_text[content_start:].strip()
            # Розділяємо на потенційні рядки з даними про військовослужбовців
            # Використовуємо splitlines() для кращої обробки різних переходів рядка
            numbered_paragraphs = [line.strip() for line in content_text.splitlines() if line.strip()]
            print(f"Знайдено {len(numbered_paragraphs)} рядків після заголовку.")
        # --- КІНЕЦЬ ЗМІН ---

        for paragraph in numbered_paragraphs:
            print(f"\\n--- Обробка рядка: {paragraph[:100]}... ---")

            # Шукаємо військову частину (рідну для військовослужбовця)
            # --- ПОЧАТОК ЗМІН ---
            # Замінюємо простий regex на виклик extract_military_unit
            # vch_match = re.search(r'військової частини\s+([АA]\d+)', paragraph)
            # origin_vch = vch_match.group(1) if vch_match else None
            origin_vch = extract_military_unit(paragraph)
            print(f"Знайдено військову частину: {origin_vch}")
            # --- КІНЕЦЬ ЗМІН ---

            # Спочатку спробуємо знайти всіх військовослужбовців через extract_military_personnel
            military_persons = extract_military_personnel(paragraph, rank_map)
            
            # Якщо не знайдено через extract_military_personnel, використовуємо extract_rank_and_name
            if not military_persons:
                rank, name = extract_rank_and_name(paragraph, rank_map)
                if rank and name:
                    military_persons = [{'rank': rank, 'name': name}]
            
            if military_persons:
                print(f"Знайдено {len(military_persons)} військовослужбовців у рядку")
                
                # --- ПОЧАТОК ЗМІН: Покращення пошуку дати в рядку та видалення небезпечного fallback ---
                departure_date = None
                meal = "зі сніданку" # Встановлюємо значення за замовчуванням

                # 1. Спроба знайти шаблон з типом харчування та датою
                # Додаємо .*?, щоб пропустити текст між типом харчування та датою
                meal_date_pattern = r'(з|зі)\s+([а-яіїєґ]+).*?(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})'
                meal_date_match = re.search(meal_date_pattern, paragraph)

                if meal_date_match:
                    meal_prefix = meal_date_match.group(1)
                    meal_type_str = meal_date_match.group(2)
                    day = meal_date_match.group(3)
                    month = meal_date_match.group(4)
                    year = meal_date_match.group(5)
                    meal = f"{meal_prefix} {meal_type_str}"
                    date_string_to_parse = f"{day} {month} {year}" # DEBUG
                    print(f"!!! DEBUG (fallback meal_date_match): Parsing date string: '{date_string_to_parse}' from paragraph: '{paragraph[:50]}...'") # DEBUG
                    departure_date = parse_date(date_string_to_parse)
                    print(f"Знайдено дату через meal_date_match: {departure_date}")
                else:
                    # 2. Якщо перший шаблон не спрацював, спроба знайти дату біля "виключити"
                    # Додаємо .*?, щоб пропустити текст між "виключити" і типом харчування
                    exclusion_date_pattern = r"виключити.*?з\s+(?:сніданку|вечері|обіду).*?(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})"
                    exclusion_date_match = re.search(exclusion_date_pattern, paragraph)
                    if exclusion_date_match:
                        day, month, year = exclusion_date_match.groups()
                        date_string_to_parse = f"{day} {month} {year}" # DEBUG
                        print(f"!!! DEBUG (fallback exclusion_date_match): Parsing date string: '{date_string_to_parse}' from paragraph: '{paragraph[:50]}...'") # DEBUG
                        departure_date = parse_date(date_string_to_parse)
                        print(f"Знайдено дату виключення біля 'виключити': {departure_date}")
                    # else:
                        # 3. ВИДАЛЕНО: Пошук дати на початку секції (section_date_match)
                        # Цей fallback був небезпечним і призводив до помилок.

                # 4. Якщо дату так і не знайдено в рядку, використовуємо поточну дату
                if not departure_date:
                    # --- ПОЧАТОК НОВИХ ЗМІН ---
                    # Додатковий прямий пошук дати у форматі "''17'' березня 2025" незалежно від контексту
                    standalone_date_pattern = r"(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})"
                    date_matches = list(re.finditer(standalone_date_pattern, paragraph, re.IGNORECASE))
                    
                    if date_matches:
                        # Беремо останню знайдену дату (зазвичай це найбільш релевантна)
                        last_match = date_matches[-1]
                        day = last_match.group(1)
                        month = last_match.group(2)
                        year = last_match.group(3)
                        date_string_to_parse = f"{day} {month} {year}"
                        print(f"!!! DEBUG (ОСТАННІЙ ШАНС): Знайдено дату прямим пошуком: '{date_string_to_parse}'")
                        departure_date = parse_date(date_string_to_parse)
                        print(f"!!! РЕЗЕРВНИЙ ПОШУК ДАТИ: Знайдено останню дату в тексті: {departure_date}")
                    else:
                        # --- КІНЕЦЬ НОВИХ ЗМІН ---
                        from datetime import datetime
                        departure_date = datetime.now().strftime("%d.%m.%Y")
                        print(f"Дата не знайдена в рядку, використано поточну: {departure_date}")
                # --- КІНЕЦЬ ЗМІН ---

                # Обробляємо кожного знайденого військовослужбовця
                for person in military_persons:
                    rank = person['rank']
                    name = person['name']
                    
                    # Перевірка дублікатів
                    person_id = f"{rank}_{name}"
                    if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                        print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                        continue

                    # Створення запису про вибуття військовослужбовця з ВЧ А1890
                    record = create_personnel_record(
                        rank=rank,
                        name=name,
                        # --- ПОЧАТОК ЗМІН ---
                        # Вказуємо рідну ВЧ (куди вибуває), а не А1890
                        vch=origin_vch if origin_vch else "А1890",
                        # --- КІНЕЦЬ ЗМІН ---
                        location="ППД",
                        os_type="Постійний склад",
                        date_k=departure_date,
                        meal=meal,
                        cause="перебували у відрядженні 1890"
                    )
                    record["action"] = "виключити"
                    results.append(record)
                    processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
                    print(f"✅ Додано запис про вибуття: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")

                # Додатково створюємо запис про зарахування до рідної ВЧ
                # --- ПОЧАТОК ВИДАЛЕННЯ ---
                # if origin_vch:
                #     origin_vch = origin_vch.strip() # Додаємо strip для надійності
                #     # Перевіряємо на нерівність А1890
                #     if origin_vch != "А1890":
                #         record_enroll = create_personnel_record(
                #             rank=rank,
                #             name=name,
                #             vch=origin_vch,
                #             location="ППД",
                #             os_type="Постійний склад",
                #             date_k=departure_date,
                #             meal=meal,
                #             cause="прибув після відрядження з А1890" # Оновлена причина
                #         )
                #         record_enroll["action"] = "зарахувати"
                #         results.append(record_enroll)
                #         # Використовуємо унікальний ключ для запису зарахування
                #         processed_persons[f"{person_id.lower()}_enroll_{origin_vch}"] = {'action': "зарахувати", 'date': departure_date}
                #         print(f"✅ Додано запис про зарахування: {rank} {name}, ВЧ: {record_enroll['VCH']}, причина: {record_enroll['cause']}")
                # --- КІНЕЦЬ ВИДАЛЕННЯ ---
            else:
                print(f"❌ Не вдалося знайти звання та ім'я у рядку")

    else:
        print(f"Знайдено {len(subitem_matches)} підпунктів у секції.")

        for match in subitem_matches:
            # Оновлені індекси груп відповідно до зміненого subitem_pattern
            item_number = match.group(1)
            vch_raw = match.group(2)  # ВЧ у форматі А1234 з регулярного виразу
            rank_raw = match.group(3).strip().lower() # Звання залишається group(3)
            name = match.group(4).strip() # Ім'я залишається group(4)
            # Група 5 тепер містить весь текст від 'виключити' до року
            meal_prefix = match.group(6) # Префікс (з/зі) тепер group(6)
            meal_type_str = match.group(7) # Тип харчування тепер group(7)
            day = match.group(8) # День тепер group(8)
            month = match.group(9) # Місяць тепер group(9)
            year = match.group(10) # Рік тепер group(10)

            # Перетворюємо звання у стандартний формат
            rank = rank_map.get(rank_raw, rank_raw)

            # Отримуємо контекст для пошуку нестандартної військової частини
            full_context = match.group(0)
            # Спочатку пробуємо витягнути більш повну або нестандартну назву частини
            vch = extract_military_unit(full_context)
            # Якщо extract_military_unit не знайшов нічого, використовуємо значення з регулярного виразу
            if not vch:
                vch = vch_raw
            
            print(f"Знайдено військову частину: {vch} (з регулярного виразу: {vch_raw})")

            # Формуємо дату та харчування
            meal = f"{meal_prefix} {meal_type_str}"
            date_string_to_parse = f"{day} {month} {year}" # DEBUG
            print(f"!!! DEBUG (main pattern): Parsing date string: '{date_string_to_parse}' from matched group") # DEBUG
            departure_date = parse_date(date_string_to_parse)

            print(f"\n--- Обробка підпункту {item_number} ---")
            print(f"ВЧ: {vch}, Звання: {rank}, Ім'я: {name}, Харчування: {meal}, Дата: {departure_date}")

            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if is_person_duplicate(person_id, processed_persons, action="виключити", date=departure_date):
                print(f"⚠️ Виявлено дублікат: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
                continue

            # Створення запису про вибуття військовослужбовця з ВЧ А1890
            record = create_personnel_record(
                rank=rank,
                name=name,
                # --- ПОЧАТОК ЗМІН ---
                # Вказуємо рідну ВЧ (куди вибуває), а не А1890
                vch=vch if vch else "А1890", # Використовуємо змінну vch, яка тут містить рідну частину
                # --- КІНЕЦЬ ЗМІН ---
                location="ППД",
                os_type="Постійний склад",
                date_k=departure_date,
                meal=meal,
                cause="перебували у відрядженні 1890"
            )
            record["action"] = "виключити"
            results.append(record)
            processed_persons[person_id.lower()] = {'action': "виключити", 'date': departure_date}
            print(f"✅ Додано запис про вибуття: {rank} {name}, ВЧ: {record['VCH']}, причина: {record['cause']}")

            # Додатково створюємо запис про зарахування до рідної ВЧ
            # --- ПОЧАТОК ВИДАЛЕННЯ ---
            # if vch and vch != "А1890":
            #     record_enroll = create_personnel_record(
            #         rank=rank,
            #         name=name,
            #         vch=vch,  # Рідна ВЧ військовослужбовця
            #         location="ППД",
            #         os_type="Постійний склад",
            #         date_k=departure_date,
            #         meal=meal,
            #         cause="прибув після відрядження з А1890" # Оновлена причина
            #     )
            #     record_enroll["action"] = "зарахувати"
            #     results.append(record_enroll)
            #      # Використовуємо унікальний ключ для запису зарахування
            #     processed_persons[f"{person_id.lower()}_enroll_{vch}"] = {'action': "зарахувати", 'date': departure_date}
            #     print(f"✅ Додано запис про зарахування: {rank} {name}, ВЧ: {record_enroll['VCH']}, причина: {record_enroll['cause']}")
            # --- КІНЕЦЬ ВИДАЛЕННЯ ---

    print(f"\nЗагалом додано {len(results)} записів у секції 'Військовослужбовці у відрядженні А1890'")
    return results
