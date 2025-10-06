from military_personnel import extract_military_personnel, create_personnel_record, is_person_duplicate, determine_personnel_type, extract_military_unit
from utils import extract_location
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
import re

def process_vacation_return(section_text, rank_map, location_triggers, default_date=None, default_meal=None, processed_persons=None):
    """
    Обробляє секцію "Повернення з відпустки" та створює записи для кожного військовослужбовця.
    """
    print("\n=== Обробка Повернення з відпустки ===")
    results = [] # Initialize results list
    if processed_persons is None:
        processed_persons = set()

    # Extract the main cause for the entire section first
    section_cause_match = re.search(r"Повернення\s+з\s+(.*?)(?:[:,]|$)", section_text, re.IGNORECASE)
    base_cause = section_cause_match.group(1).strip() if section_cause_match else "Повернення з відпустки (не вказано тип)"
    print(f"Основна причина для секції: {base_cause}")

    # Split into subsections based on vacation type or date
    subsections = split_section_into_subsections(section_text, r"^\d+\.\d+\.\d+\.\s*(?:з|по)\s") # Use a generic pattern

    total_found = 0
    if not subsections:
        print("Увага: Не знайдено нумерованих підсекцій. Обробляємо весь текст секції.")
        subsections = [(section_text, None)] # Process the whole text as one subsection

    for i, (subsection_text, header) in enumerate(subsections):
        print(f"\n--- Обробка підсекції {i+1} ---")
        if header:
            print(f"Заголовок підсекції: {header.strip()}")

        # Extract specific details for the subsection
        return_date = extract_section_date(subsection_text, default_date)
        meal_type, meal_date = extract_meal_info(subsection_text, default_meal)
        
        # Refine cause based on subsection header or content if possible
        subsection_cause = base_cause # Default to section cause
        if header:
            # Try to extract a more specific cause from the header
            cause_match = re.search(r"Повернення\s+з\s+(.*)", header, re.IGNORECASE)
            if cause_match:
                subsection_cause = cause_match.group(1).strip()
        print(f"Причина для підсекції: {subsection_cause}")
        print(f"Дата повернення/харчування: {return_date} / {meal_date}")
        print(f"Тип харчування: {meal_type}")

        # Extract personnel
        personnel_data_list = extract_military_personnel(subsection_text, rank_map)
        print(f"Знайдено {len(personnel_data_list)} військовослужбовців у підсекції")
        total_found += len(personnel_data_list)

        for person_data in personnel_data_list:
            rank = person_data['rank']
            name = person_data['name']
            vch_from_extraction = person_data.get('vch') # Optional VCH from the line

            person_id = f"{rank}_{name}"
            if person_id in processed_persons:
                print(f"⚠️ Виявлено дублікат: {rank} {name} - пропускаємо!")
                continue

            # Determine VCH: Use extracted if available, otherwise fallback might be needed (e.g., from config or main order VCH)
            # For now, let's prioritize extraction, then maybe a default? Needs context.
            vch_to_use = vch_from_extraction or extract_military_unit(subsection_text) or "A1890" # Placeholder default
            
            # Determine location
            location = extract_location(subsection_text, location_triggers) or "ППД"

            # Determine personnel type
            os_type = determine_personnel_type(subsection_text)
            print(f"    Визначено тип ОС для {rank} {name}: {os_type}")

            record = create_personnel_record(
                rank=rank,
                name=name,
                vch=vch_to_use,
                location=location,
                os_type=os_type,
                date_k=meal_date or return_date, # Use meal date if specific, else return date
                meal=meal_type,
                cause=subsection_cause # Use the determined cause for the subsection
            )

            results.append(record)
            processed_persons.add(person_id)
            print(f"✅ Додано запис: {rank} {name} - ВЧ: {record['VCH']}, Причина: {record['cause']}")

    print(f"\nЗагалом знайдено {total_found} записів у секції '{base_cause}'")
    return results 