"""
Модуль для обробки секцій, пов'язаних з поверненням з відпусток.
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import extract_military_personnel, create_personnel_record, is_person_duplicate, determine_personnel_type
from utils import extract_location, extract_vch, determine_paragraph_location

def process_vacation_return(section_text, rank_map, location_triggers, default_date=None, default_meal=None, processed_persons=None):
    """
    Обробляє секцію повернення з відпустки та створює записи для кожного військовослужбовця.
    Працює на рівні абзаців.
    
    Args:
        section_text (str): Текст секції (сирий)
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        default_date (str, optional): Стандартна дата, якщо не знайдено
        default_meal (str, optional): Стандартне харчування, якщо не знайдено
        processed_persons (set, optional): Множина вже оброблених осіб
        
    Returns:
        list: Список записів про військовослужбовців
    """
    print("\n=== Обробка Повернення з відпустки (Paragraph Mode) ===")
    results = []
    if processed_persons is None:
        processed_persons = set()

    # Визначаємо загальний тип відпустки для секції (як fallback)
    base_vacation_type = determine_vacation_type(section_text)
    print(f"Базовий тип відпустки для секції: {base_vacation_type}")

    # Розділяємо на підсекції та абзаци
    subsections_with_paragraphs = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections_with_paragraphs)} підрозділів відпустки")
    
    total_found_overall = 0
    
    # Головна ВЧ наказу (куди повертаються)
    return_vch = "A1890"
    print(f"Встановлено стандартну ВЧ повернення з відпустки: {return_vch}")

    # Обробка кожної підсекції
    for i, (subsection_number, paragraphs) in enumerate(subsections_with_paragraphs, 1):
        print(f"\n-- Обробка підрозділу відпустки {subsection_number or 'Без номера'} --")
        print(f"Кількість абзаців: {len(paragraphs)}")

        # Визначаємо тип відпустки для підсекції (більш точно)
        subsection_vacation_type = base_vacation_type # Починаємо з базового
        if paragraphs:
            # Шукаємо ключові слова в першому абзаці або заголовку
            header_text_search_area = section_text[section_text.find(subsection_number if subsection_number else '') : section_text.find(paragraphs[0])] if subsection_number else paragraphs[0]
            subsection_vacation_type = determine_vacation_type(header_text_search_area) 
            print(f"   Визначено тип відпустки для підрозділу: {subsection_vacation_type}")

        # Обробка кожного абзацу
        for para_idx, paragraph_text in enumerate(paragraphs, 1):
            print(f"\n   --- Абзац {para_idx} --- ")
            print(f"   Текст абзацу (перші 100): {paragraph_text[:100]}...")
            paragraph_norm = normalize_text(paragraph_text)

            # --- Локальні дані з абзацу --- 

            # Визначаємо причину повернення
            # Використовуємо тип, визначений для підсекції
            current_cause = f"Повернення з {subsection_vacation_type}" 
            print(f"      Причина: {current_cause}")

            # Дата повернення (з абзацу)
            return_date = extract_section_date(paragraph_norm, default_date)
            print(f"      Дата повернення (з абзацу): {return_date}")

            # Харчування (з абзацу)
            meal_type, meal_date = extract_meal_info(paragraph_norm, default_meal)
            print(f"      Харчування (з абзацу): {meal_type}, дата: {meal_date}")

            # Локація (зазвичай ППД, але може бути НБ)
            location = determine_paragraph_location(paragraph_norm, location_triggers)
            if not location:
                location = "ППД" # Стандартно для повернення з відпустки
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
                
                # ВЧ (завжди та, куди повернулись)
                current_vch_for_person = return_vch
                print(f"         ВЧ для {rank} {name}: {current_vch_for_person}")

                # Перевірка дублікатів
                person_id = f"{rank}_{name}"
                if person_id in processed_persons:
                    print(f"      ⚠️ Виявлено дублікат (Vacation): {rank} {name} - пропускаємо!")
                    continue
                    
                # Створення запису
                record = create_personnel_record(
                    rank=rank,
                    name=name,
                    vch=current_vch_for_person,
                    location=location,
                    os_type=os_type,
                    date_k=meal_date or return_date,
                    meal=meal_type or default_meal,
                    cause=current_cause
                )
                
                results.append(record)
                processed_persons.add(person_id)
                total_found_overall += 1
                print(f"      ✅ Додано запис (Vacation): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}, Причина: {record['cause']}")

            if not military_persons_in_para:
                 print(f"      Військовослужбовців в цьому абзаці не знайдено.")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції 'Повернення з відпустки' (Paragraph Mode)")
    return results

def determine_vacation_type(section_text):
    """
    Визначає тип відпустки на основі тексту секції.
    
    Args:
        section_text (str): Текст секції
        
    Returns:
        str: Тип відпустки (наприклад, 'щорічної основної відпустки')
    """
    section_text_lower = section_text.lower()
    
    # Шукаємо найспецифічніші типи спочатку
    if "щорічної основної відпустки" in section_text_lower or "частини щорічної" in section_text_lower:
        return "щорічної основної відпустки"
    elif "відпустки за сімейними обставинами" in section_text_lower:
        return "відпустки за сімейними обставинами"
    elif "відпустки для лікування" in section_text_lower or "відпустки у зв'язку з хворобою" in section_text_lower:
        return "відпустки для лікування"
    elif "відпустки за іншими поважними причинами" in section_text_lower:
        return "відпустки за іншими поважними причинами"
    # Менш специфічні
    elif "відпустки" in section_text_lower:
        return "відпустки (тип не уточнено)"
    else:
        return "відпустки (тип не знайдено)"

# Remove the local determine_personnel_type function as it's now centralized
# def determine_personnel_type(text, rank):
#     """
#     Визначає тип особового складу на основі тексту та звання.
#     
#     Args:
#         text (str): Текст підсекції
#         rank (str): Звання військовослужбовця
#         
#     Returns:
#         str: Тип особового складу
#     """
#     text = text.lower()
#     
#     if "за призовом по мобілізації" in text:
#         return "Мобілізований"
#     elif "за призовом" in text:
#         return "Призовник"
#     else:
#         return "Постійний склад" 