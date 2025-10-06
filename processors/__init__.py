"""
Пакет з процесорами для різних типів секцій військових наказів.
"""
from processors.arrival_processor import process_arrival_at_assignment, process_arrival_at_training
from processors.return_processor import process_return_from_assignment
from processors.hospital_processor import process_hospital_return
from processors.mobilization_processor import process_mobilization
from processors.vacation_return_processor import process_vacation_return
from processors.szch_processor import process_szch_section, find_szch_sections
from processors.departure_processor import (
    process_departure,
    process_departure_for_further_service,
    process_departure_to_reserve,
    process_departure_to_assignment,
    process_departure_to_vacation,
    process_departure_to_hospital,
    process_personnel_on_assignment_a1890
) 