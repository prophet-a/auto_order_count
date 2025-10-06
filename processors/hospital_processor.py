"""
Модуль для обробки секцій, пов'язаних з поверненням з лікувального закладу.
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import extract_military_unit, create_personnel_record, is_person_duplicate, determine_personnel_type, extract_military_personnel
from utils import extract_location, determine_paragraph_location

def process_hospital_return(section_text, rank_map, location_triggers, processed_persons=None, cause_override=None):
    """
    Обробляє секції повернення з лікувального закладу.
    Працює на рівні абзаців.

    Args:
        section_text (str): Текст секції (сирий)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (set, optional): Множина вже оброблених осіб. За замовчуванням None.
        cause_override (str, optional): Перевизначена причина для записів (для спец. випадків, як секція 11.7)
        
    Returns:
        list: Список результатів
    """
    print("\n=== Обробка повернення з лікувального закладу (Paragraph Mode) ===")
    
    results = []
    if processed_persons is None:
        processed_persons = set()
    
    # Розділяємо на підсекції та абзаци
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} підрозділів лікарні")
    
    total_found_overall = 0
    
    # Головна ВЧ наказу (куди повертаються)
    return_vch = "A1890" 
    print(f"Встановлено стандартну ВЧ повернення з лікарні: {return_vch}")

    # Обробка кожної підсекції
    for i, (subsection_number, paragraphs) in enumerate(subsections_with_paragraphs, 1):
        print(f"\n-- Обробка підрозділу лікарні {subsection_number or 'Без номера'} --")
        print(f"Кількість абзаців: {len(paragraphs)}")

        # Визначаємо заклад (лікарню) для цієї підсекції
        hospital_name = "Невідомий лікувальний заклад"
        if paragraphs:
            header_text_search_area = section_text[section_text.find(subsection_number if subsection_number else '') : section_text.find(paragraphs[0])] if subsection_number else paragraphs[0]
            # Шукаємо назву лікарні після "з"
            hospital_match = re.search(r'з\s+(.+?)(?:\s+з\s+\'\'\d{1,2}\'\'|:|$)', header_text_search_area.strip(), re.IGNORECASE)
            if hospital_match:
                hospital_name = hospital_match.group(1).strip().rstrip(':')
                print(f"   Визначено лікувальний заклад для підрозділу: {hospital_name}")
            else:
                print(f"   УВАГА: Не вдалося визначити лікувальний заклад для підрозділу {subsection_number}")

        # Обробка кожного абзацу
        for para_idx, paragraph_text in enumerate(paragraphs, 1):
            print(f"\n   --- Абзац {para_idx} --- ")
            print(f"   Текст абзацу (перші 100): {paragraph_text[:100]}...")
            paragraph_norm = normalize_text(paragraph_text)

            # --- Локальні дані з абзацу --- 
            
            # Перевірка на секцію "Хвороба" (11.7/12.8) в межах абзацу
            is_illness_paragraph = False
            if ("звільнені від виконання службових обов'язків" in paragraph_norm.lower() or
                "звільнений від виконання службових обов'язків" in paragraph_norm.lower()):
                is_illness_paragraph = True
                print("      Виявлено абзац звільнення від обов'язків через хворобу (11.7/12.8)")
            
            # Перевірка на наявність фрази про зарахування на котлове забезпечення
            has_meal_enrollment = ("зарахувати на котлове забезпечення" in paragraph_norm.lower() or
                                   "зарахувати на котлов" in paragraph_norm.lower())
            
            # Якщо це секція хвороби БЕЗ явного зарахування на котлове - пропускаємо
            if is_illness_paragraph and not has_meal_enrollment:
                print("      ⚠️ Секція звільнення від обов'язків через хворобу БЕЗ зарахування на котлове - пропускаємо абзац")
                continue
            
            # Визначаємо причину
            if is_illness_paragraph:
                current_cause = cause_override or "Звільнення від обов'язків через хворобу"
            else:
                # Формуємо причину з назвою лікарні
                current_cause = cause_override or f"Повернення з лікувального закладу ({hospital_name})"
            print(f"      Причина: {current_cause}")

            # Дата повернення/початку хвороби (з абзацу)
            event_date = extract_section_date(paragraph_norm)
            print(f"      Дата події (з абзацу): {event_date}")

            # Харчування (з абзацу)
            meal_type, meal_date = extract_meal_info(paragraph_norm)
            print(f"      Харчування (з абзацу): {meal_type}, дата: {meal_date}")

            # Локація (зазвичай ППД, але може бути НБ)
            location = determine_paragraph_location(paragraph_norm, location_triggers)
            if not location:
                 location = "ППД" # Стандартно для повернення з лікарні/хвороби
                 print(f"      Локація не знайдена ні за НБ, ні за тригером, встановлено за замовчуванням: {location}")
                 
            # Витягуємо військовослужбовців (з абзацу)
            military_persons_in_para = extract_military_personnel(paragraph_text, rank_map)
            print(f"      Знайдено {len(military_persons_in_para)} військовослужбовців в абзаці")

            for person_data in military_persons_in_para:
                rank = person_data['rank']
                name = person_data['name']

                # Тип ОС (з абзацу)
                os_type = determine_personnel_type(paragraph_norm)
                print(f"         Визначено тип ОС для {rank} {name}: {os_type}")
                
                # ВЧ (зазвичай куди повернулись = return_vch)
                # Спробуємо знайти ВЧ в абзаці, якщо це військовослужбовець іншої частини
                vch_in_para = extract_military_unit(paragraph_norm)
                current_vch_for_person = vch_in_para if vch_in_para else return_vch
                print(f"         ВЧ для {rank} {name}: {current_vch_for_person} (з абзацу: {vch_in_para})")

                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if person_id in processed_persons:
                    print(f"      ⚠️ Виявлено дублікат (Hospital): {rank} {name} - пропускаємо!")
                    continue
                    
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=current_vch_for_person, # ВЧ з абзацу або стандартна
                    location=location,
                    os_type=os_type,
                    date_k=meal_date or event_date, # Використовуємо дату харчування якщо є, інакше дату події
                    meal=meal_type or "зі сніданку", # Стандартне харчування якщо не знайдено
                    cause=current_cause
                )
                
                results.append(record)
                processed_persons.add(person_id)
                total_found_overall += 1
                print(f"      ✅ Додано запис (Hospital/Illness): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}, Причина: {record['cause']}")

            if not military_persons_in_para:
                 print(f"      Військовослужбовців в цьому абзаці не знайдено.")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції 'Повернення з лікувального закладу / Хвороба' (Paragraph Mode)")
    return results