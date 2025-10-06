"""
Модуль для обробки секцій, пов'язаних з прибуттям у відрядження.
Основні функції:
- process_arrival_at_assignment: Обробка прибуття у відрядження для виконання службового завдання
- process_arrival_at_training: Обробка прибуття у відрядження на навчання
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import extract_military_personnel, create_personnel_record, is_person_duplicate, determine_personnel_type, extract_military_unit
from utils import extract_location, determine_paragraph_location

def process_arrival_at_assignment(section_text, rank_map, location_triggers, default_date=None, default_meal="зі сніданку", processed_persons=None):
    """
    Обробляє прибуття у відрядження та створює записи для кожного військовослужбовця.
    Працює на рівні абзаців для точного визначення контексту.
    
    Args:
        section_text (str): Текст секції (сирий)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        default_date (str, optional): Стандартна дата, якщо не знайдено.
        default_meal (str, optional): Стандартне харчування, якщо не знайдено.
        processed_persons (set, optional): Множина вже оброблених осіб.
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка прибуття у службове відрядження (Paragraph Mode) ===\n")
    
    results = []
    if processed_persons is None:
        processed_persons = set()
    
    # Розділяємо на підсекції, а потім на абзаци
    # split_section_into_subsections тепер повертає [(subsection_number, list_of_paragraphs), ...]
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    
    print(f"Знайдено {len(subsections_with_paragraphs)} підрозділів відрядження")
    
    total_found_overall = 0
    
    # Обробка кожного підрозділу
    for i, (subsection_number, paragraphs) in enumerate(subsections_with_paragraphs, 1):
        print(f"\n-- Обробка підсекції {subsection_number or 'Без номера'} --")
        print(f"Кількість абзаців: {len(paragraphs)}")

        subsection_vch_from_header = None # ВЧ, витягнута з заголовка підрозділу, якщо є
        # Спробуємо витягнути ВЧ з самого початку (з заголовка підрозділу)
        if paragraphs:
             # Дивимось на текст самого номера і перший абзац
             header_text_search_area = section_text[section_text.find(subsection_number if subsection_number else '') : section_text.find(paragraphs[0])] if subsection_number else paragraphs[0]
             header_vch_match = re.search(r'з\\s+військової\\s+частини\\s+([А-Я]\\d{4})', header_text_search_area, re.IGNORECASE)
             if header_vch_match:
                  subsection_vch_from_header = header_vch_match.group(1)
                  print(f"   Знайдено ВЧ ({subsection_vch_from_header}) в заголовку/початку підрозділу {subsection_number}")


        # Обробка кожного абзацу в межах підрозділу
        for para_idx, paragraph_text in enumerate(paragraphs, 1):
            print(f"\n   --- Абзац {para_idx} --- ")
            print(f"   Текст абзацу (перші 100): {paragraph_text[:100]}...")

            # --- Локалізація вилучення даних ТІЛЬКИ до поточного абзацу ---
            
            # Нормалізуємо ТІЛЬКИ поточний абзац для вилучення даних
            paragraph_norm = normalize_text(paragraph_text)
            
            # Визначення ВЧ ЗВІДКИ прибули (з абзацу)
            # Пріоритет: явна згадка в абзаці, потім згадка в заголовку підрозділу
            vch_from = extract_military_unit(paragraph_norm)
            if vch_from:
                 print(f"      Знайдено ВЧ (з абзацу): {vch_from}")
            elif subsection_vch_from_header:
                 vch_from = subsection_vch_from_header
                 print(f"      Використано ВЧ з заголовка підрозділу: {vch_from}")
            else:
                 # Якщо ВЧ немає ні в абзаці, ні в заголовку, можемо встановити стандартне або None
                 # У випадку службового відрядження, частіше за все ВЧ вказана
                 vch_from = None # Або "А1890" якщо це припущення логічне
                 print(f"      УВАГА: Не знайдено ВЧ ні в абзаці, ні в заголовку підрозділу.")
            
            # ВЧ ПРИЗНАЧЕННЯ (Куди прибули) - зазвичай A1890 для служб. відряджень
            vch_to = "A1890" # Стандартно для службових відряджень до цієї частини
            
            # Визначення локації (з абзацу)
            location = determine_paragraph_location(paragraph_norm, location_triggers)
            if not location:
                location = "ППД" # Стандартно для служб. відрядження
                print(f"      Локація не знайдена ні за НБ, ні за тригером, встановлено за замовчуванням: {location}")

            # Отримуємо дату прибуття (з абзацу)
            return_date = extract_section_date(paragraph_norm, default_date)
            if return_date:
                 print(f"      Знайдено дату прибуття (з абзацу): {return_date}")
            else:
                 # Можна спробувати взяти з контексту підсекції, якщо потрібно, але обережно
                 print(f"      Дата прибуття не знайдена в абзаці.")


            # Отримуємо інформацію про харчування (з абзацу)
            meal_info, meal_date = extract_meal_info(paragraph_norm, default_meal)
            if meal_info:
                 print(f"      Знайдено харчування (з абзацу): {meal_info}, дата: {meal_date}")
            else:
                 print(f"      Інформація про харчування не знайдена в абзаці.")

            # Визначаємо мету відрядження (з абзацу)
            # Можна використовувати загальну причину або шукати деталі в абзаці
            mission_purpose = "Прибуття у відрядження для виконання службового завдання:" # Загальна
            # Тут можна додати логіку для пошуку специфічної мети в paragraph_norm, якщо потрібно
            
            # Витягуємо інформацію про військовослужбовців ТІЛЬКИ з поточного абзацу
            # Використовуємо paragraph_norm або paragraph_text?
            # extract_military_personnel очікує рядок, paragraph_text (сирий) може бути краще для span?
            # Давайте спробуємо з paragraph_text, а rank_map застосуємо пізніше
            military_persons_in_para = extract_military_personnel(paragraph_text, rank_map)
            print(f"      Знайдено {len(military_persons_in_para)} військовослужбовців в абзаці")
            
            # Обробка знайдених в абзаці військовослужбовців
            for person_data in military_persons_in_para:
                rank = person_data['rank']
                name = person_data['name']
                # person_span = person_data.get('span') # span тепер відноситься до paragraph_text

                # Визначаємо тип ОС (з абзацу)
                # Важливо: передаємо paragraph_norm або paragraph_text?
                # determine_personnel_type очікує рядок, нормалізований краще
                os_type = determine_personnel_type(paragraph_norm)
                print(f"         Визначено тип ОС для {rank} {name}: {os_type}")

                # Перевірка дублікатів (використовуємо загальний processed_persons)
                person_id = f"{rank}_{name}"
                if person_id in processed_persons:
                    print(f"      ⚠️ Виявлено дублікат (Assignment): {rank} {name} - пропускаємо!")
                    continue

                # Створення запису - використовуємо дані, витягнуті з АБЗАЦУ
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=vch_from if vch_from else vch_to, # Якщо ВЧ звідки неясно, використовуємо куди? Або None?
                    location=location,                 # Локація з абзацу (або стандартна)
                    os_type=os_type,                   # OS з абзацу
                    date_k=meal_date if meal_date else return_date, # Дата з абзацу
                    meal=meal_info if meal_info else default_meal,  # Харчування з абзацу
                    cause="Відрядження (завдання)"       # Прямо вказуємо правильну причину
                )
                
                # Валідація VCH перед додаванням (приклад)
                if not record['VCH']:
                    print(f"      УВАГА: Пропускаємо запис для {rank} {name} через відсутність VCH.")
                    continue # Або записуємо з None/Default?

                results.append(record)
                processed_persons.add(person_id)
                total_found_overall += 1
                print(f"      ✅ Додано запис (Assignment): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}")
            
            if not military_persons_in_para:
                 print(f"      Військовослужбовців в цьому абзаці не знайдено.")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції 'Прибуття у відрядження' (Paragraph Mode)")
    return results


def process_arrival_at_training(section_text, rank_map, location_triggers, default_date=None, default_meal="зі сніданку", processed_persons=None):
    """
    Обробляє прибуття у відрядження з метою навчання та створює записи для кожного військовослужбовця.
    Працює на рівні абзаців для точного визначення контексту.

    Args:
        section_text (str): Текст секції (сирий)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        default_date (str, optional): Стандартна дата, якщо не знайдено.
        default_meal (str, optional): Стандартне харчування, якщо не знайдено.
        processed_persons (set, optional): Множина вже оброблених осіб.

    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка прибуття у навчальне відрядження (Paragraph Mode) ===")
    results = []
    if processed_persons is None:
        processed_persons = set()

    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} підрозділів навчання")
    total_found_overall = 0

    for i, (subsection_number, paragraphs) in enumerate(subsections_with_paragraphs, 1):
        print(f"\n-- Обробка підрозділу навчання {subsection_number or 'Без номера'} --")
        print(f"Кількість абзаців: {len(paragraphs)}")

        subsection_vch_from_header = None # ВЧ, витягнута з заголовка підрозділу, якщо є
        # Спробуємо витягнути ВЧ з заголовка підрозділу (наприклад, 'військовослужбовців військової частини XXXX')
        if paragraphs:
             header_text_search_area = section_text[section_text.find(subsection_number if subsection_number else '') : section_text.find(paragraphs[0])] if subsection_number else paragraphs[0]
             header_vch_match = re.search(r'(?:з|до)\s+військової\\s+частини\\s+([А-Я]\\d{4})', header_text_search_area, re.IGNORECASE)
             if header_vch_match:
                  subsection_vch_from_header = header_vch_match.group(1)
                  print(f"   Знайдено ВЧ ({subsection_vch_from_header}) в заголовку/початку підрозділу {subsection_number}")

        for para_idx, paragraph_text in enumerate(paragraphs, 1):
            print(f"\n   --- Абзац {para_idx} --- ")
            print(f"   Текст абзацу (перші 100): {paragraph_text[:100]}...")
            paragraph_norm = normalize_text(paragraph_text)

            # --- Extract data strictly from paragraph_norm / paragraph_text ---
            # ВЧ звідки (пріоритет: абзац, заголовок підрозділу)
            vch_from = extract_military_unit(paragraph_norm)
            if vch_from:
                print(f"      Знайдено ВЧ (з абзацу): {vch_from}")
            elif subsection_vch_from_header:
                vch_from = subsection_vch_from_header
                print(f"      Використано ВЧ з заголовка підрозdілу: {vch_from}")
            else:
                vch_from = None # Для навчання ВЧ звідки може бути важлива
                print(f"      УВАГА: Не знайдено ВЧ звідки для абзацу.")

            # ВЧ куди (для навчання це A1890)
            vch_to = "A1890"

            # Локація (з абзацу)
            location = determine_paragraph_location(paragraph_norm, location_triggers)
            if not location:
                 location = "НЦ" # Стандартна локація для навчання
                 print(f"      Локація не знайдена ні за НБ, ні за тригером, встановлено за замовчуванням: {location}")

            # Дата прибуття (з абзацу)
            arrival_date = extract_section_date(paragraph_norm, default_date)
            if arrival_date:
                print(f"      Знайдено дату прибуття (з абзацу): {arrival_date}")
            else:
                print(f"      Дата прибуття не знайдена в абзаці.")

            # Харчування (з абзацу)
            meal_info, meal_date = extract_meal_info(paragraph_norm, default_meal)
            if meal_info:
                 print(f"      Знайдено харчування (з абзацу): {meal_info}, дата: {meal_date}")
            else:
                 print(f"      Інформація про харчування не знайдена в абзаці.")

            # Причина
            training_purpose = "Прибуття у відрядження для навчання"

            # Військовослужбовці (з абзацу)
            military_persons_in_para = extract_military_personnel(paragraph_text, rank_map)
            print(f"      Знайдено {len(military_persons_in_para)} військовослужбовців в абзаці")

            for person_data in military_persons_in_para:
                rank = person_data['rank']
                name = person_data['name']

                # Тип ОС (з абзацу)
                os_type = determine_personnel_type(paragraph_norm)
                print(f"         Визначено тип ОС для {rank} {name}: {os_type}")

                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if person_id in processed_persons:
                    print(f"      ⚠️ Виявлено дублікат (Training): {rank} {name} - пропускаємо!")
                    continue

                # Створення запису з даними абзацу
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    # Якщо vch_from не знайдено, використовуємо vch_to (A1890)
                    # Це припущення, що якщо ВЧ не вказана, то це персонал A1890, що прибув на навчання
                    vch=vch_from if vch_from else vch_to, 
                    location=location,
                    os_type=os_type,
                    date_k=meal_date or arrival_date,
                    meal=meal_info or default_meal,
                    cause=training_purpose
                )

                # Валідація VCH (можливо, варто дозволити None для деяких випадків навчання?)
                if not record['VCH']:
                    print(f"      УВАГА: VCH для {rank} {name} не визначено, записуємо з None.")
                    record['VCH'] = None # Або залишити як є, залежно від вимог

                results.append(record)
                processed_persons.add(person_id)
                total_found_overall += 1
                print(f"      ✅ Додано запис (Training): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}")

            if not military_persons_in_para:
                 print(f"      Військовослужбовців в цьому абзаці не знайдено.")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції \'Прибуття у відрядження (навчання)\' (Paragraph Mode)")
    return results 