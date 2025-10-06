def process_arrival_at_training(section_text, rank_map, location_triggers, processed_persons=None):
    """
    Обробляє секції про прибуття у навчальне відрядження.
    
    Args:
        section_text (str): Текст секції
        rank_map (dict): Словник відповідності звань
        location_triggers (dict): Словник тригерів локацій
        processed_persons (set, optional): Множина вже оброблених осіб для уникнення дублікатів
        
    Returns:
        list: Список результатів зі знайденими військовослужбовцями
    """
    import re
    from text_processing import normalize_text
    from section_detection import extract_section_date, extract_meal_info, split_section_into_subsections
    from military_personnel import extract_military_personnel, extract_military_unit, create_personnel_record, is_person_duplicate, determine_personnel_type
    from utils import extract_location

    print("\n*** ENTERING process_arrival_at_training ***\n")
    
    # Ініціалізуємо множину оброблених осіб
    if processed_persons is None:
        processed_persons = set()
    
    results = []
    
    print("=== Обробка прибуття у навчальне відрядження ===")
    print(f"Довжина тексту секції: {len(section_text)} символів")
    print(f"Перші 200 символів: {section_text[:200]}...")
    
    # Розділяємо на підрозділи
    subsections = split_section_into_subsections(section_text)
    print(f"Знайдено {len(subsections)} підрозділів навчального відрядження")
    
    for i, (subsection_src, subsection_text) in enumerate(subsections, 1):
        print(f"\n--- Підрозділ навчального відрядження {i} ---")
        print(f"Довжина тексту підрозділу: {len(subsection_text)} символів")
        print(f"Перші 200 символів підрозділу: {subsection_text[:200]}...")
        
        # Підготовка тексту
        subsection_norm = subsection_text.replace('\n', ' ').replace('  ', ' ')
        
        # Перевіряємо, чи є в тексті фраза про кількість осіб
        count_match = re.search(r"у\s+кількості\s+(\d+)\s+(?:осіб|особи)", subsection_norm)
        expected_count = int(count_match.group(1)) if count_match else 0
        
        # Знаходимо дату
        return_date = extract_section_date(subsection_text)
        if return_date:
            print(f"Знайдено дату прибуття: {return_date}")
        
        # Отримуємо інформацію про харчування
        meal_info = extract_meal_info(subsection_text)
        print(f"Інформація про харчування: {meal_info}")
        
        total_found = 0
        
        # Визначаємо місце призначення
        location = None
        for trigger, loc in location_triggers.items():
            if trigger in subsection_norm:
                location = loc
                print(f"Знайдено місце призначення: {location}")
                break
        
        if not location:
            location = "ППД"  # За замовчуванням
            print(f"Встановлено стандартне місце призначення: {location}")
        
        # Випадок 1: Якщо є фраза про кількість, використовуємо спеціальну логіку розбору
        if expected_count > 0:
            print(f"В підрозділі зазначено {expected_count} осіб - використовуємо спеціальну логіку розбору")
            
            # Шукаємо список військовослужбовців, що слідує після фрази "у кількості X осіб:"
            personnel_match = re.search(r"у\s+кількості\s+\d+\s+осіб:?\s+(.*?)(?:зарахувати|підстава|$)", 
                                      subsection_norm, re.DOTALL | re.IGNORECASE)
            
            if personnel_match:
                personnel_list_text = personnel_match.group(1).strip()
                print(f"Знайдено список військовослужбовців довжиною {len(personnel_list_text)} символів")
                
                # Шукаємо військовослужбовців у списку (можуть бути як через кому, так і через нумерацію)
                
                # Спочатку перевіряємо, чи є нумерований список (1., 2., 3., ...)
                if re.search(r'\d+\.', personnel_list_text):
                    print("Виявлено нумерований список")
                    items = re.findall(r'\d+\.\s+([^,\d\.]+?)(?=\d+\.|$)', personnel_list_text)
                    print(f"Знайдено {len(items)} елементів у нумерованому списку")
                else:
                    # Якщо немає нумерації, розбиваємо по комам
                    print("Розбиваємо список по комам")
                    items = [item.strip() for item in personnel_list_text.split(',')]
                    print(f"Знайдено {len(items)} елементів у списку через кому")
                
                # Витягаємо військовослужбовців зі списку
                for item in items:
                    item = item.strip()
                    if not item:
                        continue
                    
                    # Використовуємо extract_military_personnel для кожного елемента
                    military_persons = extract_military_personnel(item, rank_map)
                    
                    # Якщо extract_military_personnel не знайшов осіб, пробуємо прямий пошук звання та імені
                    if not military_persons:
                        # Шукаємо звання серед відомих
                        found_rank = None
                        for rank in rank_map.keys():
                            if rank.lower() in item.lower():
                                found_rank = rank_map[rank]
                                break
                        
                        # Шукаємо ім'я (прізвище, ім'я та по-батькові)
                        name_match = re.search(r'([А-ЯІЇЄҐ][А-ЯІЇЄҐа-яіїєґ\'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+\s+[А-ЯІЇЄҐ][а-яіїєґ\'-]+)', item)
                        if found_rank and name_match:
                            military_persons = [(found_rank, name_match.group(1))]
                        elif name_match:  # Якщо є тільки ім'я
                            military_persons = [("рядовий", name_match.group(1))]  # За замовчуванням
                    
                    for rank, name in military_persons:
                        # Перевірка на дублікати
                        if is_person_duplicate(f"{rank} {name}", processed_persons):
                            print(f"⚠️ Виявлено дублікат: {rank} {name} - пропускаємо!")
                            continue
                        
                        # Формуємо запис про військовослужбовця
                        person_record = {
                            "rank": rank,
                            "name": name,
                            "military_unit": "A1890",  # Якщо в тексті є інформація про частину, варто витягати
                            "location": location,
                            "reason": "Прибуття у навчальне відрядження",
                            "arrival_date": return_date,
                            "meal_info": meal_info
                        }
                        
                        # Додаємо запис та відмічаємо як оброблений
                        results.append(person_record)
                        processed_persons.add(f"{rank} {name}")
                        total_found += 1
                        print(f"✅ Додано запис: {rank} {name}")
        
        # Випадок 2: Стандартний пошук військовослужбовців
        else:
            print("Використовуємо стандартний пошук військовослужбовців")
            military_persons = extract_military_personnel(subsection_text, rank_map)
            print(f"Знайдено {len(military_persons)} військовослужбовців")
            
            for rank, name in military_persons:
                # Перевірка на дублікати
                if is_person_duplicate(f"{rank} {name}", processed_persons):
                    print(f"⚠️ Виявлено дублікат: {rank} {name} - пропускаємо!")
                    continue
                
                # Формуємо запис про військовослужбовця
                person_record = {
                    "rank": rank,
                    "name": name,
                    "military_unit": "A1890",  # Якщо в тексті є інформація про частину, варто витягати
                    "location": location,
                    "reason": "Прибуття у навчальне відрядження",
                    "arrival_date": return_date,
                    "meal_info": meal_info
                }
                
                # Додаємо запис та відмічаємо як оброблений
                results.append(person_record)
                processed_persons.add(f"{rank} {name}")
                total_found += 1
                print(f"✅ Додано запис: {rank} {name}")
        
        print(f"Знайдено {total_found} військовослужбовців у підрозділі")
    
    print(f"\nЗагальна кількість доданих записів: {len(results)}")
    return results 