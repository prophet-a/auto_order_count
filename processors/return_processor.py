"""
Модуль для обробки секцій, пов'язаних з поверненням з відрядження.
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import extract_military_personnel, extract_military_unit, create_personnel_record, is_person_duplicate, determine_personnel_type
from utils import extract_location, determine_paragraph_location

print("\n*** ENTERING process_return ***\n")

def process_return_from_assignment(section_text, rank_map, location_triggers, default_date=None, default_meal=None, processed_persons=None):
    """
    Обробляє секцію "Повернення з відрядження" та створює записи для кожного військовослужбовця.
    Працює на рівні абзаців.

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
    print("\n=== Обробка Повернення з відрядження (Paragraph Mode) ===")
    results = []
    if processed_persons is None:
        processed_persons = set()
        
    # Розділяємо на підсекції та абзаци
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} підрозділів повернення")
    
    total_found_overall = 0
    
    # Головна ВЧ наказу (куди повертаються)
    return_vch = "A1890" # Потрібно передавати або визначати з контексту наказу
    print(f"Встановлено стандартну ВЧ повернення: {return_vch}")

    for i, (subsection_number, paragraphs) in enumerate(subsections_with_paragraphs, 1):
        print(f"\n-- Обробка підрозділу повернення {subsection_number or 'Без номера'} --")
        print(f"Кількість абзаців: {len(paragraphs)}")

        # Визначаємо "звідки" повернулись для цієї підсекції (з заголовка/першого абзацу)
        origin = "Unknown Origin" 
        if paragraphs:
             # Шукаємо в заголовку або першому абзаці щось типу "з [Місце/ВЧ]"
             header_text_search_area = section_text[section_text.find(subsection_number if subsection_number else '') : section_text.find(paragraphs[0])] if subsection_number else paragraphs[0]
             origin_match = re.search(r'з\s+((?:військової\s+частини\s+[А-Я]\d{4})|[^,\n]+?)(?:,|\s+з\s+)?\'\'\d{1,2}\'\'', header_text_search_area, re.IGNORECASE)
             if origin_match:
                 origin = origin_match.group(1).strip()
                 print(f"   Визначено походження для підрозділу: {origin}")
             else:
                 # Спробуємо знайти просто "з [Місце/ВЧ]:" в кінці заголовка
                 simple_origin_match = re.search(r'з\s+(.*?):?$', header_text_search_area.strip(), re.IGNORECASE)
                 if simple_origin_match:
                     origin = simple_origin_match.group(1).strip()
                     print(f"   Визначено походження для підрозділу (простий): {origin}")
                 else:
                     print(f"   УВАГА: Не вдалося визначити походження для підрозділу {subsection_number}")
        
        # Обробка кожного абзацу
        for para_idx, paragraph_text in enumerate(paragraphs, 1):
            print(f"\n   --- Абзац {para_idx} --- ")
            print(f"   Текст абзацу (перші 100): {paragraph_text[:100]}..." )
            paragraph_norm = normalize_text(paragraph_text)

            # --- Локальні дані з абзацу --- 
            # Дата повернення
            return_date = extract_section_date(paragraph_norm, default_date)
            print(f"      Дата повернення (з абзацу): {return_date}")
            
            # Харчування
            meal_type, meal_date = extract_meal_info(paragraph_norm, default_meal)
            print(f"      Харчування (з абзацу): {meal_type}, дата: {meal_date}")
            
            # Локація повернення (зазвичай ППД)
            location = determine_paragraph_location(paragraph_norm, location_triggers)
            if not location:
                 location = "ППД" # Стандартно для повернення
                 print(f"      Локація не знайдена ні за НБ, ні за тригером, встановлено за замовчуванням: {location}")

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
                    print(f"      ⚠️ Виявлено дублікат (Return): {rank} {name} - пропускаємо!")
                    continue
                
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=return_vch, # Використовуємо ВЧ, КУДИ повернулись
                    location=location, # Локація з абзацу/стандартна
                    os_type=os_type, # OS з абзацу
                    date_k=meal_date or return_date, # Дата з абзацу
                    meal=meal_type or default_meal, # Харчування з абзацу
                    # Використовуємо origin, визначений для підсекції
                    cause=f"Повернення з відрядження ({origin})" 
                )
                
                results.append(record)
                processed_persons.add(person_id)
                total_found_overall += 1
                print(f"      ✅ Додано запис (Return): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}, Причина: {record['cause']}")

            if not military_persons_in_para:
                 print(f"      Військовослужбовців в цьому абзаці не знайдено.")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції 'Повернення з відрядження' (Paragraph Mode)")
    return results 