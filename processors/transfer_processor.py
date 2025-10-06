"""
Модуль для обробки секцій, пов'язаних з переведенням військовослужбовців між підрозділами.
Обробляє записи, де військовослужбовець в одному абзаці і виключається з однієї локації, і зараховується до іншої.
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
from name_converter import process_full_name

def process_transfer_records(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє секції, де військовослужбовці переводяться з одного підрозділу в інший
    (виключення з одного місця і зарахування в інше).
    
    Args:
        section_text (str): Текст секції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (dict або set, optional): Словник вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка секції переведення військовослужбовців ===")
    results = []
    if processed_persons is None:
        processed_persons = {}
    elif not isinstance(processed_persons, dict):
        # Конвертуємо set у dict, якщо потрібно (для зворотної сумісності)
        processed_persons = {p: {'action': None, 'date': None} for p in processed_persons}
    
    # Розділяємо на абзаци по нумерації або порожніх рядках
    paragraphs = section_text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    # Знаходимо абзац із загальною інформацією про переведення (якщо є)
    header_paragraph = None
    if paragraphs and re.search(r'^\d+\.\d+\.\d+', paragraphs[0]):
        header_paragraph = paragraphs[0]
        paragraphs = paragraphs[1:]  # Відділяємо заголовок від списку військовослужбовців
        print(f"Знайдено заголовок секції: {header_paragraph[:100]}...")
    
    destination_location = None
    if header_paragraph:
        # Спробуємо знайти локацію призначення в заголовку
        match = re.search(r'до\s+(\d+)\s+навчального\s+батальйону', header_paragraph)
        if match:
            destination_nb = match.group(1)
            destination_location = f"{destination_nb} НБ"
            print(f"Знайдено локацію призначення з заголовка: {destination_location}")
    
    # Special case handling for the format with general exclusion and enrollment paragraphs
    # followed by a list of personnel with VCH codes
    if len(paragraphs) >= 3:
        # Check if first paragraph contains exclusion info and second contains enrollment info
        has_exclusion_info = re.search(r'[Вв]иключити\s+з\s+котлового\s+забезпечення', paragraphs[0])
        has_enrollment_info = re.search(r'[Зз]арахувати\s+на\s+котлове\s+забезпечення', paragraphs[1])
        
        # If we have the special format, process it
        if has_exclusion_info and has_enrollment_info:
            print("\n=== Виявлено спеціальний формат з загальною інформацією по виключенню/зарахуванню ===")
            
            # Extract exclusion info
            exclusion_info = {}
            # Extract source location
            source_match = re.search(r'(\d+)\s+навчального\s+батальйону', paragraphs[0])
            if source_match:
                exclusion_info['location'] = f"{source_match.group(1)} НБ"
                print(f"Знайдено локацію виключення: {exclusion_info['location']}")
            
            # Extract date and meal
            date_match = re.search(r"(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})", paragraphs[0])
            if date_match:
                day, month, year = date_match.groups()
                exclusion_info['date'] = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату виключення: {exclusion_info['date']}")
            
            meal_match = re.search(r'(зі|з)\s+([а-яіїєґ]+)', paragraphs[0])
            if meal_match:
                prefix, meal = meal_match.groups()
                exclusion_info['meal'] = f"{prefix} {meal}"
                print(f"Знайдено харчування для виключення: {exclusion_info['meal']}")
            
            # Extract enrollment info
            enrollment_info = {}
            # Extract destination location
            dest_match = re.search(r'(\d+)\s+навчального\s+батальйону', paragraphs[1])
            if dest_match:
                enrollment_info['location'] = f"{dest_match.group(1)} НБ"
                print(f"Знайдено локацію зарахування: {enrollment_info['location']}")
            
            # Extract date and meal
            date_match = re.search(r"(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})", paragraphs[1])
            if date_match:
                day, month, year = date_match.groups()
                enrollment_info['date'] = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату зарахування: {enrollment_info['date']}")
            
            meal_match = re.search(r'(зі|з)\s+([а-яіїєґ]+)', paragraphs[1])
            if meal_match:
                prefix, meal = meal_match.groups()
                enrollment_info['meal'] = f"{prefix} {meal}"
                print(f"Знайдено харчування для зарахування: {enrollment_info['meal']}")
            
            # Set defaults if not found
            if 'location' not in exclusion_info:
                exclusion_info['location'] = "ППД"
                print("Локація виключення не знайдена, використовуємо 'ППД'")
            
            if 'date' not in exclusion_info:
                from datetime import datetime
                exclusion_info['date'] = datetime.now().strftime("%d.%m.%Y")
                print(f"Дата виключення не знайдена, використовуємо поточну: {exclusion_info['date']}")
            
            if 'meal' not in exclusion_info:
                exclusion_info['meal'] = "зі сніданку"
                print("Харчування для виключення не знайдене, використовуємо 'зі сніданку'")
                
            if 'location' not in enrollment_info:
                enrollment_info['location'] = "ППД"
                print("Локація зарахування не знайдена, використовуємо 'ППД'")
            
            if 'date' not in enrollment_info:
                enrollment_info['date'] = exclusion_info['date']
                print(f"Дата зарахування не знайдена, використовуємо дату виключення: {enrollment_info['date']}")
            
            if 'meal' not in enrollment_info:
                enrollment_info['meal'] = exclusion_info['meal']
                print(f"Харчування для зарахування не знайдене, використовуємо те ж що для виключення: {enrollment_info['meal']}")
            
            # Process personnel paragraphs (starting from the third paragraph)
            special_format_found = False
            for i in range(2, len(paragraphs)-1):
                # Check if paragraph contains numbered entries
                lines = paragraphs[i].strip().split('\n')
                for line in lines:
                    # Match format: number, VCH code, rank, name
                    personnel_match = re.match(r'^\d+\.\s+([AА]\d+)\s+([а-яіїєґ\s]+)\s+([А-ЯІЇЄҐ]+\s+[А-ЯІЇЄҐа-яіїєґ]+\s+[А-ЯІЇЄҐа-яіїєґ]+)', line)
                    if personnel_match:
                        special_format_found = True
                        vch = personnel_match.group(1)
                        rank = personnel_match.group(2).strip()
                        name = personnel_match.group(3).strip()
                        
                        print(f"\nОбробка військовослужбовця зі спеціального формату: {rank} {name}, ВЧ: {vch}")
                        
                        # Determine personnel type
                        os_type = determine_personnel_type(" ".join(paragraphs))
                        
                        # Create unique identifiers for duplicate checking
                        person_id_exclusion = f"{rank}_{name}_exclusion_{exclusion_info['date']}"
                        person_id_enrollment = f"{rank}_{name}_enrollment_{enrollment_info['date']}"
                        
                        # Create exclusion record if not a duplicate
                        if not is_person_duplicate(person_id_exclusion, processed_persons, action="виключити", date=exclusion_info['date']):
                            record_exclusion = create_personnel_record(
                                rank=rank,
                                name=name,
                                vch=vch,
                                location=exclusion_info['location'],
                                os_type=os_type,
                                date_k=exclusion_info['date'],
                                meal=exclusion_info['meal'],
                                cause="Переміщення"
                            )
                            record_exclusion["action"] = "виключити"
                            results.append(record_exclusion)
                            processed_persons[person_id_exclusion.lower()] = {'action': "виключити", 'date': exclusion_info['date']}
                            print(f"✅ Додано запис про виключення: {rank} {name}, ВЧ: {vch}, локація: {exclusion_info['location']}")
                            total_found += 1
                        else:
                            print(f"⚠️ Виявлено дублікат виключення: {rank} {name} - пропускаємо!")
                        
                        # Create enrollment record if not a duplicate
                        if not is_person_duplicate(person_id_enrollment, processed_persons, action="зарахувати", date=enrollment_info['date']):
                            record_enrollment = create_personnel_record(
                                rank=rank,
                                name=name,
                                vch=vch,
                                location=enrollment_info['location'],
                                os_type=os_type,
                                date_k=enrollment_info['date'],
                                meal=enrollment_info['meal'],
                                cause="Переміщення"
                            )
                            record_enrollment["action"] = "зарахувати"
                            results.append(record_enrollment)
                            processed_persons[person_id_enrollment.lower()] = {'action': "зарахувати", 'date': enrollment_info['date']}
                            print(f"✅ Додано запис про зарахування: {rank} {name}, ВЧ: {vch}, локація: {enrollment_info['location']}")
                            total_found += 1
                        else:
                            print(f"⚠️ Виявлено дублікат зарахування: {rank} {name} - пропускаємо!")
            
            # If we successfully processed using the special format, return the results
            if special_format_found:
                print(f"\nЗагалом додано {total_found} записів зі спеціального формату")
                
                # Нормалізація імен
                for record in results:
                    original_name = record.get('name')
                    if original_name and isinstance(original_name, str):
                        try:
                            normalized_name = process_full_name(original_name)
                            record['name_normal'] = normalized_name
                            print(f"Нормалізовано ім'я: '{original_name}' -> '{normalized_name}'")
                        except Exception as e:
                            print(f"Помилка нормалізації імені '{original_name}': {e}")
                            record['name_normal'] = original_name # Запасний варіант - оригінальне ім'я
                
                return results
    
    total_found = 0
    
    for i, paragraph in enumerate(paragraphs):
        print(f"\n--- Обробка абзацу {i+1} ---")
        print(f"Текст: {paragraph[:100]}...")
        
        # Витягуємо військовослужбовця
        military_persons = extract_military_personnel(paragraph, rank_map)
        
        if not military_persons:
            print(f"Не знайдено військовослужбовців у абзаці {i+1}")
            # Спробуємо використати інший метод для витягнення
            rank, name = extract_rank_and_name(paragraph, rank_map)
            if rank and name:
                print(f"Знайдено військовослужбовця через extract_rank_and_name: {rank} {name}")
                military_persons = [{'rank': rank, 'name': name}]
            else:
                continue
        
        # Визначаємо причину переведення
        cause = "Переміщення"  # За замовчуванням
        #if header_paragraph and "набуття досвіду" in header_paragraph:
        #    cause = "Навчання (набуття досвіду)"
        #elif header_paragraph and "медичного обслуговування" in header_paragraph:
        #    cause = "Медичне обслуговування"
        
        # Шукаємо інформацію про виключення
        exclusion_match = re.search(r'[Вв]иключити\s+з\s+котлового\s+забезпечення.*?(\d+)\s+навчального\s+батальйону.*?(з|зі)\s+([а-яіїєґ]+)\s+(?:\'\'|\"?)(\d{1,2})(?:\'\'|\"?)\s+([а-яіїєґ]+)\s+(\d{4})', paragraph)
        
        source_location = None
        exclusion_meal = None
        exclusion_date = None
        
        if exclusion_match:
            source_nb = exclusion_match.group(1)
            source_location = f"{source_nb} НБ"
            meal_prefix = exclusion_match.group(2)
            meal_type_str = exclusion_match.group(3)
            exclusion_meal = f"{meal_prefix} {meal_type_str}"
            day = exclusion_match.group(4)
            month = exclusion_match.group(5)
            year = exclusion_match.group(6)
            exclusion_date = parse_date(f"{day} {month} {year}")
            print(f"Знайдено інформацію про виключення: локація {source_location}, харчування {exclusion_meal}, дата {exclusion_date}")
        else:
            # Спробуємо інший підхід до пошуку локації виключення
            location_pattern = r'виключити\s+з\s+котлового\s+забезпечення[^,]*?(\d+)\s*навчального\s+батальйону'
            location_match = re.search(location_pattern, paragraph, re.IGNORECASE)
            if location_match:
                source_nb = location_match.group(1)
                source_location = f"{source_nb} НБ"
                print(f"Знайдено локацію виключення альтернативним методом: {source_location}")
        
        # Шукаємо інформацію про зарахування
        enrollment_match = re.search(r'[Зз]арахувати\s+на\s+котлове\s+забезпечення.*?(\d+)\s+навчального\s+батальйону.*?(з|зі)\s+([а-яіїєґ]+)\s+(?:\'\'|\"?)(\d{1,2})(?:\'\'|\"?)\s+([а-яіїєґ]+)\s+(\d{4})', paragraph)
        
        if not destination_location and enrollment_match:
            dest_nb = enrollment_match.group(1)
            destination_location = f"{dest_nb} НБ"
        
        enrollment_meal = None
        enrollment_date = None
        
        if enrollment_match:
            meal_prefix = enrollment_match.group(2)
            meal_type_str = enrollment_match.group(3)
            enrollment_meal = f"{meal_prefix} {meal_type_str}"
            day = enrollment_match.group(4)
            month = enrollment_match.group(5)
            year = enrollment_match.group(6)
            enrollment_date = parse_date(f"{day} {month} {year}")
            print(f"Знайдено інформацію про зарахування: локація {destination_location}, харчування {enrollment_meal}, дата {enrollment_date}")
        
        # Якщо не знайдено локацію призначення, шукаємо в тексті абзацу
        if not destination_location:
            dest_match = re.search(r'до\s+(\d+)\s+навчального\s+батальйону', paragraph)
            if dest_match:
                dest_nb = dest_match.group(1)
                destination_location = f"{dest_nb} НБ"
                print(f"Знайдено локацію призначення з тексту абзацу: {destination_location}")
        
        # Для надійності встановлюємо значення за замовчуванням
        if not source_location:
            source_location = "ППД"
            print("Локація відправлення не знайдена, використовуємо 'ППД'")
        
        if not destination_location:
            destination_location = "ППД"
            print("Локація призначення не знайдена, використовуємо 'ППД'")
        
        if not exclusion_meal:
            exclusion_meal = "зі сніданку"
            print("Тип харчування для виключення не знайдений, використовуємо 'зі сніданку'")
        
        if not enrollment_meal:
            enrollment_meal = exclusion_meal if exclusion_meal else "зі сніданку"
            print(f"Тип харчування для зарахування не знайдений, використовуємо '{enrollment_meal}'")
        
        if not exclusion_date:
            # Спробуємо знайти будь-яку дату в абзаці
            date_pattern = r"(?:''|\")(\d{1,2})(?:''|\")\s+([а-яіїєґ]+)\s+(\d{4})"
            date_match = re.search(date_pattern, paragraph)
            if date_match:
                day, month, year = date_match.groups()
                exclusion_date = parse_date(f"{day} {month} {year}")
                print(f"Знайдено дату в абзаці: {exclusion_date}")
            else:
                from datetime import datetime
                exclusion_date = datetime.now().strftime("%d.%m.%Y")
                print(f"Дата виключення не знайдена, використовуємо поточну: {exclusion_date}")
        
        if not enrollment_date:
            enrollment_date = exclusion_date
            print(f"Дата зарахування не знайдена, використовуємо дату виключення: {enrollment_date}")
        
        # Визначаємо військову частину
        vch = "А1890"  # За замовчуванням
        vch_match = re.search(r'військової\s+частини\s+([АA]\d+)', paragraph)
        if vch_match:
            vch = vch_match.group(1)
            print(f"Знайдено військову частину: {vch}")
        
        # Створюємо записи для кожного військовослужбовця
        for person_data in military_persons:
            rank = person_data['rank']
            name = person_data['name']
            
            # Визначаємо тип ОС
            os_type = determine_personnel_type(paragraph)
            
            # Створюємо унікальні ідентифікатори для перевірки дублікатів
            person_id_exclusion = f"{rank}_{name}_exclusion_{exclusion_date}"
            person_id_enrollment = f"{rank}_{name}_enrollment_{enrollment_date}"
            
            # Перевірка дублікатів для виключення
            if is_person_duplicate(person_id_exclusion, processed_persons, action="виключити", date=exclusion_date):
                print(f"⚠️ Виявлено дублікат виключення: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
            else:
                # Створення запису про виключення
                record_exclusion = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=vch,
                    location=source_location,
                    os_type=os_type,
                    date_k=exclusion_date,
                    meal=exclusion_meal,
                    cause=cause
                )
                record_exclusion["action"] = "виключити"
                results.append(record_exclusion)
                processed_persons[person_id_exclusion.lower()] = {'action': "виключити", 'date': exclusion_date}
                total_found += 1
                print(f"✅ Додано запис про виключення: {rank} {name}, ВЧ: {vch}, локація: {source_location}, причина: {cause}")
            
            # Перевірка дублікатів для зарахування
            if is_person_duplicate(person_id_enrollment, processed_persons, action="зарахувати", date=enrollment_date):
                print(f"⚠️ Виявлено дублікат зарахування: {rank} {name} з тією ж дією в той самий день - пропускаємо!")
            else:
                # Створення запису про зарахування
                record_enrollment = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=vch,
                    location=destination_location,
                    os_type=os_type,
                    date_k=enrollment_date,
                    meal=enrollment_meal,
                    cause=cause
                )
                record_enrollment["action"] = "зарахувати"
                results.append(record_enrollment)
                processed_persons[person_id_enrollment.lower()] = {'action': "зарахувати", 'date': enrollment_date}
                total_found += 1
                print(f"✅ Додано запис про зарахування: {rank} {name}, ВЧ: {vch}, локація: {destination_location}, причина: {cause}")
    
    print(f"\nЗагалом додано {total_found} записів у секції переведення військовослужбовців")
    
    # Нормалізація імен
    for record in results:
        original_name = record.get('name')
        if original_name and isinstance(original_name, str):
            try:
                normalized_name = process_full_name(original_name)
                record['name_normal'] = normalized_name
                print(f"Нормалізовано ім'я: '{original_name}' -> '{normalized_name}'")
            except Exception as e:
                print(f"Помилка нормалізації імені '{original_name}': {e}")
                record['name_normal'] = original_name # Запасний варіант - оригінальне ім'я
    
    return results 