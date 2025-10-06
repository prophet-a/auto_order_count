"""
Модуль для обробки секцій, пов'язаних з мобілізацією.
Основні функції:
- process_mobilization: Обробка прибуття військовозобов'язаних за мобілізаційним призначенням
- search_mob: Пошук записів про мобілізованих військовослужбовців
"""

import re
from text_processing import normalize_text
from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
from military_personnel import extract_military_personnel, extract_military_unit, create_personnel_record, is_person_duplicate, determine_personnel_type
from utils import extract_location, determine_paragraph_location

def process_mobilization(section_text, rank_map, location_triggers, default_date=None, default_meal=None, processed_persons=None):
    """
    Обробляє секцію з мобілізаційним призначенням та створює записи для кожного військовослужбовця.
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
    print("\n=== Обробка мобілізаційного призначення (Paragraph Mode) ===")
    results = []
    if processed_persons is None:
        processed_persons = set()
    
    # Спочатку обробляємо преамбулу секції для отримання загальних даних
    # Зазвичай це текст ДО першого нумерованого запису
    preamble_text = ""
    first_entry_match = re.search(r'^\s*1\.\s+', section_text, re.MULTILINE)
    if first_entry_match:
        preamble_text = section_text[:first_entry_match.start()].strip()
    else:
        preamble_text = section_text # Якщо немає нумерації, вся секція - преамбула?
        print("УВАГА: Не знайдено початок нумерованого списку (1.), використовую весь текст як преамбулу.")

    print(f"Текст преамбули (перші 200): {preamble_text[:200]}...")
    preamble_norm = normalize_text(preamble_text)
    
    # Витягуємо загальні дані з преамбули
    vch_to = extract_military_unit(preamble_norm) or "А1890"
    print(f"Військова частина призначення (з преамбули): {vch_to}")
    
    # Загальна дата прибуття з преамбули
    arrival_date_preamble = extract_section_date(preamble_norm, default_date)
    print(f"Загальна дата прибуття (з преамбули): {arrival_date_preamble}")

    # Загальне харчування з преамбули
    meal_type_preamble, meal_date_preamble = extract_meal_info(preamble_norm, default_meal)
    print(f"Загальне харчування (з преамбули): {meal_type_preamble}, дата: {meal_date_preamble}")

    # Загальна локація/НБ з преамбули
    location_preamble = extract_location(preamble_norm, location_triggers)
    if not location_preamble:
        nb_match_preamble = re.search(r'(\d+)\s+навчального\s+батальйону', preamble_norm, re.IGNORECASE)
        if nb_match_preamble:
            location_preamble = f"{nb_match_preamble.group(1)} НБ"
            print(f"Знайдено загальну локацію НБ (з преамбули): {location_preamble}")
        else:
            location_preamble = "НЦ" # Або ППД? Для мобілізації часто НЦ
            print(f"Загальна локація не знайдена, встановлено за замовчуванням: {location_preamble}")
    else:
        print(f"Знайдено загальну локацію за тригером (з преамбули): {location_preamble}")

    # --- Тепер обробляємо список осіб --- 
    # Використовуємо split_section_into_subsections, але вона може не спрацювати ідеально для мобілізації
    # Спробуємо інший підхід: розділити на абзаци після преамбули
    personnel_section_text = section_text[len(preamble_text):].strip()
    # Розділяємо на абзаци за нумерацією "X." на початку рядка
    paragraphs = []
    current_paragraph = ""
    # Використовуємо re.split для розділення за номерами, зберігаючи роздільники
    # Це складно, спробуємо знайти кожен запис
    entry_pattern = r'(^\s*\d+\.\s+.+?)(?=\n\s*\d+\.\s+|\nПідстава:|\Z)' # Знаходить кожен нумерований запис
    paragraphs = re.findall(entry_pattern, personnel_section_text, re.MULTILINE | re.DOTALL)

    print(f"Знайдено {len(paragraphs)} абзаців/записів мобілізованих")
    
    total_found_overall = 0
    
    # Обробляємо кожен абзац/запис
    for para_idx, paragraph_text in enumerate(paragraphs, 1):
        print(f"\n   --- Абзац/Запис {para_idx} --- ")
        print(f"   Текст (перші 100): {paragraph_text[:100]}...")
        paragraph_norm = normalize_text(paragraph_text) # Нормалізуємо абзац

        # Витягуємо військовослужбовців ТІЛЬКИ з цього абзацу
        military_persons_in_para = extract_military_personnel(paragraph_text, rank_map)
        print(f"      Знайдено {len(military_persons_in_para)} військовослужбовців в абзаці")

        if not military_persons_in_para:
            print(f"      УВАГА: Не знайдено військовослужбовців у записі {para_idx}. Текст: {paragraph_norm[:150]}...")
            continue

        # --- Витягуємо локальні дані ТІЛЬКИ з цього абзацу --- 
        # Використовуємо нову функцію для визначення локації
        location_para = determine_paragraph_location(paragraph_norm, location_triggers)
        # Логіка обробки якщо location_para None та використання location_preamble залишається

        final_location = location_para or location_preamble # Пріоритет абзацу
        print(f"      Фінальна локація: {final_location}")

        # Місце прибуття (звідки) - шукаємо "який прибув з ..."
        origin_location = "Не вказано"
        origin_match = re.search(r'який\s+прибув\s+з\s+(.*?)(?:;|\n|Підстава:|\Z)', paragraph_norm, re.IGNORECASE)
        if origin_match:
            origin_location = origin_match.group(1).strip()
            print(f"      Знайдено місце прибуття (з абзацу): {origin_location}")

        # Дата і харчування - зазвичай беруться з преамбули для мобілізації
        final_date = meal_date_preamble or arrival_date_preamble
        final_meal = meal_type_preamble or default_meal or "зі сніданку"
        print(f"      Використано дату/харчування з преамбули: {final_date} / {final_meal}")

        # Обробка знайдених осіб в абзаці
        for person_data in military_persons_in_para:
            rank = person_data['rank']
            name = person_data['name']

            # Тип ОС (з абзацу) - Пріоритет Курсант > Мобілізований
            os_type = determine_personnel_type(paragraph_norm)
            if "курсант" in paragraph_norm.lower(): # Перевіряємо знову на рівні абзацу
                os_type = "Курсант"
            elif "мобілізації" in paragraph_norm.lower(): # Забезпечуємо, що це мобілізований
                os_type = "Мобілізований"
            print(f"         Визначено тип ОС для {rank} {name}: {os_type}")

            # Перевірка дублікатів
            person_id = f"{rank}_{name}"
            if person_id in processed_persons:
                print(f"      ⚠️ Виявлено дублікат (Mobilization): {rank} {name} - пропускаємо!")
                continue

            # Створення запису
            record = create_personnel_record(
                rank=rank,
                name=name,
                vch=vch_to,              # ВЧ призначення (з преамбули)
                location=final_location, # Локація (абзац/преамбула)
                os_type=os_type,         # Тип ОС (з абзацу)
                date_k=final_date,       # Дата (з преамбули)
                meal=final_meal,         # Харчування (з преамбули)
                # Додаємо місце прибуття до причини
                cause=f"ППОС (прибув з: {origin_location})" 
            )
            
            results.append(record)
            processed_persons.add(person_id)
            total_found_overall += 1
            print(f"      ✅ Додано запис (Mobilization): {rank} {name}, ВЧ: {record['VCH']}, Локація: {record['location']}, Причина: {record['cause']}")

    print(f"\nЗагалом знайдено {total_found_overall} записів у секції 'Мобілізаційне призначення' (Paragraph Mode)")
    return results

# --- Функція search_mob більше не потрібна, оскільки логіка інтегрована вище --- 
# --- Функція extract_battalion_info також більше не потрібна --- 
# --- extract_rank_and_name та інші утиліти залишаються в military_personnel.py --- 

# Залишаємо тільки потрібні функції в цьому файлі
# (extract_military_unit, create_personnel_record, is_person_duplicate, determine_personnel_type 
#  переїхали або використовуються з military_personnel.py)