"""Enrollment curriculum catalog — keep in sync with js/enrollment-curriculum.js
Source: SHS-Subjects.docx (DepEd SHS curriculum)
"""

ENROLLMENT_TRACKS = {
    'Academic': {
        'label': 'Academic Track',
        'strands': [
            'STEM',
            'ABM',
            'HUMSS',
        ],
    },
    'TechPro': {
        'label': 'Technical-Professional (TechPro)',
        'strands': [
            'ICT',
            'COOKERY',
            'EIM',
        ],
    },
}

ENROLLMENT_STRANDS = ['STEM', 'ABM', 'HUMSS', 'ICT', 'COOKERY', 'EIM']

STRAND_TRACK = {}
for _track, _info in ENROLLMENT_TRACKS.items():
    for _code in _info["strands"]:
        STRAND_TRACK[_code] = _track

# Virtue / hero section names — keep in sync with supabase/section-names.sql and auto-schedule.js
ENROLLMENT_SECTION_LETTERS = ("A", "B")

ENROLLMENT_SECTION_NAMES_BY_GRADE = {
    "Grade 12": {
        "STEM": ["Rizal", "Bonifacio"],
        "ABM": ["Aguinaldo", "Mabini"],
        "HUMSS": ["Luna", "Jacinto"],
        "GAS": ["A", "B"],
        "ICT": ["Zamora", "Gomez"],
        "COOKERY": ["Del Pilar", "Silang"],
        "EIM": ["Aquino", "Malvar"],
    },
    "Grade 11": {
        "STEM": ["Hope", "Fortitude"],
        "ABM": ["Faith", "Integrity"],
        "HUMSS": ["Perseverance", "Courage"],
        "GAS": ["A", "B"],
        "ICT": ["Humility", "Kindness"],
        "COOKERY": ["Wisdom", "Compassion"],
        "EIM": ["Resilience", "Justice"],
    },
}

ENROLLMENT_CURRICULUM = {
    'Grade 11': {
        '1st': {
            'core': [
                {
                    'code': 'G11-C01',
                    'description': 'Oral Communication in Context',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C02',
                    'description': 'Komunikasyon at Pananaliksik sa Wika at Kulturang Pilipino',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C03',
                    'description': 'General Mathematics',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C04',
                    'description': 'Earth and Life Science',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C05',
                    'description': 'Personal Development',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-PE1',
                    'description': 'Physical Education and Health 1',
                    'lec': 2,
                    'lab': 0,
                    'units': 2,
                },
            ],
            'applied': [
                {
                    'code': 'G11-A01',
                    'description': 'Empowerment Technologies',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
            ],
            'specialized': {
                'STEM': [
                    {
                        'code': 'G11-STEM-01',
                        'description': 'Pre-Calculus',
                        'lec': 4,
                        'lab': 0,
                        'units': 4,
                    },
                    {
                        'code': 'G11-STEM-02',
                        'description': 'General Biology 1',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-STEM-03',
                        'description': 'Earth Science',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'ABM': [
                    {
                        'code': 'G11-ABM-01',
                        'description': 'Organization and Management',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-ABM-02',
                        'description': 'Applied Economics',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'HUMSS': [
                    {
                        'code': 'G11-HUM-01',
                        'description': 'Disciplines and Ideas in the Social Sciences',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-HUM-02',
                        'description': 'Creative Writing',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-HUM-03',
                        'description': 'Philippine Politics and Governance',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'GAS': [],
                'ICT': [
                    {
                        'code': 'G11-ICT-01',
                        'description': 'CSS NC II – Install and Configure Computer Systems',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-ICT-02',
                        'description': 'CSS NC II – Set Up Computer Networks',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'COOKERY': [
                    {
                        'code': 'G11-CK-01',
                        'description': 'Use Kitchen Tools, Equipment, and Paraphernalia',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-02',
                        'description': 'Perform Mensuration and Calculation',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-03',
                        'description': 'Interpret Kitchen Layout',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-04',
                        'description': 'Practice Occupational Health and Safety Procedures',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'EIM': [
                    {
                        'code': 'G11-EIM-01',
                        'description': 'Prepare Electrical Materials and Tools',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-EIM-02',
                        'description': 'Interpret Technical Drawings and Plans',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-EIM-03',
                        'description': 'Perform Mensuration and Calculation',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-EIM-04',
                        'description': 'Practice Occupational Safety and Health Procedures',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
            },
        },
        '2nd': {
            'core': [
                {
                    'code': 'G11-C06',
                    'description': 'Reading and Writing Skills',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C07',
                    'description': "Pagbasa at Pagsusuri ng Iba't Ibang Teksto Tungo sa Pananaliksik",
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C08',
                    'description': 'Statistics and Probability',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C09',
                    'description': 'Physical Science',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-C10',
                    'description': 'Understanding Culture, Society and Politics',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G11-PE2',
                    'description': 'Physical Education and Health 2',
                    'lec': 2,
                    'lab': 0,
                    'units': 2,
                },
            ],
            'applied': [
                {
                    'code': 'G11-A02',
                    'description': 'Practical Research 1',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
            ],
            'specialized': {
                'STEM': [
                    {
                        'code': 'G11-STEM-04',
                        'description': 'Basic Calculus',
                        'lec': 4,
                        'lab': 0,
                        'units': 4,
                    },
                    {
                        'code': 'G11-STEM-05',
                        'description': 'General Biology 2',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-STEM-06',
                        'description': 'General Physics 1',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'ABM': [
                    {
                        'code': 'G11-ABM-03',
                        'description': 'Business Finance',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-ABM-04',
                        'description': 'Fundamentals of Accountancy, Business and Management 1',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'HUMSS': [
                    {
                        'code': 'G11-HUM-04',
                        'description': 'Disciplines and Ideas in the Applied Social Sciences',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-HUM-05',
                        'description': 'Creative Nonfiction',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G11-HUM-06',
                        'description': 'Community Engagement, Solidarity and Citizenship',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'GAS': [],
                'ICT': [
                    {
                        'code': 'G11-ICT-03',
                        'description': 'CSS NC II – Install Computer Systems and Networks',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-ICT-04',
                        'description': 'CSS NC II – Maintain and Repair Computer Systems and Networks',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'COOKERY': [
                    {
                        'code': 'G11-CK-05',
                        'description': 'Clean and Maintain Kitchen Tools, Equipment, and Premises',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-06',
                        'description': 'Prepare Appetizers',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-07',
                        'description': 'Prepare Salads and Dressings',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-08',
                        'description': 'Prepare Sandwiches',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-09',
                        'description': 'Prepare Egg Dishes',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-10',
                        'description': 'Prepare Vegetables',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-CK-11',
                        'description': 'Prepare Seafood Dishes',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'EIM': [
                    {
                        'code': 'G11-EIM-05',
                        'description': 'Install Electrical Lighting System',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-EIM-06',
                        'description': 'Install Wiring Devices',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G11-EIM-07',
                        'description': 'Install Conduit, Tubing and Fittings',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
            },
        },
    },
    'Grade 12': {
        '1st': {
            'core': [
                {
                    'code': 'G12-C01',
                    'description': 'Introduction to the Philosophy of the Human Person',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-C02',
                    'description': 'Disaster Readiness and Risk Reduction',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-PE3',
                    'description': 'Physical Education and Health 3',
                    'lec': 2,
                    'lab': 0,
                    'units': 2,
                },
            ],
            'applied': [
                {
                    'code': 'G12-A01',
                    'description': 'English for Academic and Professional Purposes',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-A02',
                    'description': 'Entrepreneurship',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-A03',
                    'description': 'Filipino sa Piling Larang',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
            ],
            'specialized': {
                'STEM': [
                    {
                        'code': 'G12-STEM-01',
                        'description': 'General Chemistry 1',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-STEM-02',
                        'description': 'General Physics 2',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'ABM': [
                    {
                        'code': 'G12-ABM-01',
                        'description': 'Fundamentals of Accountancy, Business and Management 2',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G12-ABM-02',
                        'description': 'Business Ethics and Social Responsibility',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'HUMSS': [
                    {
                        'code': 'G12-HUM-01',
                        'description': 'Trends, Networks and Critical Thinking in the 21st Century',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'GAS': [],
                'ICT': [
                    {
                        'code': 'G12-ICT-01',
                        'description': 'CSS NC II – Diagnose and Troubleshoot Computer Systems',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-ICT-02',
                        'description': 'CSS NC II – Configure Network Services',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'COOKERY': [
                    {
                        'code': 'G12-CK-01',
                        'description': 'Prepare Stocks, Sauces and Soups',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-02',
                        'description': 'Prepare Poultry and Game Dishes',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-03',
                        'description': 'Prepare Meat Dishes',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-04',
                        'description': 'Prepare Desserts',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
                'EIM': [
                    {
                        'code': 'G12-EIM-01',
                        'description': 'Install Electrical Protection System',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-EIM-02',
                        'description': 'Install Electrical Control System',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-EIM-03',
                        'description': 'Maintain and Repair Electrical Systems',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                ],
            },
        },
        '2nd': {
            'core': [
                {
                    'code': 'G12-C03',
                    'description': 'Contemporary Philippine Arts from the Regions',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-PE4',
                    'description': 'Physical Education and Health 4',
                    'lec': 2,
                    'lab': 0,
                    'units': 2,
                },
            ],
            'applied': [
                {
                    'code': 'G12-A04',
                    'description': 'Inquiries, Investigations, and Immersion',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-A05',
                    'description': 'Practical Research 2',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
                {
                    'code': 'G12-A06',
                    'description': 'Work Immersion',
                    'lec': 3,
                    'lab': 0,
                    'units': 3,
                },
            ],
            'specialized': {
                'STEM': [
                    {
                        'code': 'G12-STEM-03',
                        'description': 'General Chemistry 2',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-STEM-04',
                        'description': 'Research/Capstone',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'ABM': [
                    {
                        'code': 'G12-ABM-03',
                        'description': 'Principles of Marketing',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G12-ABM-04',
                        'description': 'Business Enterprise Simulation',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'HUMSS': [
                    {
                        'code': 'G12-HUM-02',
                        'description': 'Introduction to World Religions and Belief Systems',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'GAS': [],
                'ICT': [
                    {
                        'code': 'G12-ICT-03',
                        'description': 'Work Immersion',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                    {
                        'code': 'G12-ICT-04',
                        'description': 'Specialization Enhancement / Entrepreneurship Integration',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'COOKERY': [
                    {
                        'code': 'G12-CK-05',
                        'description': 'Prepare Cakes',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-06',
                        'description': 'Prepare Pastries',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-07',
                        'description': 'Package Prepared Food',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-CK-08',
                        'description': 'Work Immersion',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
                'EIM': [
                    {
                        'code': 'G12-EIM-04',
                        'description': 'Test and Commission Electrical Installation',
                        'lec': 3,
                        'lab': 1,
                        'units': 4,
                    },
                    {
                        'code': 'G12-EIM-05',
                        'description': 'Work Immersion',
                        'lec': 3,
                        'lab': 0,
                        'units': 3,
                    },
                ],
            },
        },
    },
}


def _grade_num(grade_level):
    return "11" if "11" in (grade_level or "") else "12"


def section_slot_name(strand_code, grade_level, slot_key):
    """Display name for section slot A/B (matches SQL section_slot_name)."""
    strand = (strand_code or "STEM").upper()
    slot = (slot_key or "A").upper()
    grade = grade_level if grade_level in ENROLLMENT_SECTION_NAMES_BY_GRADE else "Grade 12"
    names = ENROLLMENT_SECTION_NAMES_BY_GRADE.get(grade, {}).get(strand)
    if not names:
        return slot
    if slot == "A":
        return names[0]
    if slot == "B":
        return names[1] if len(names) > 1 else slot
    return slot


def format_section_name(strand_code, grade_level, slot_key):
    """Full section label e.g. STEM 12-Rizal."""
    strand = (strand_code or "STEM").upper()
    grade_num = _grade_num(grade_level)
    return f"{strand} {grade_num}-{section_slot_name(strand, grade_level, slot_key)}"


def _build_strand_schedules(grade_level, semester, subject_code, day_time, slots=28):
    grade_num = _grade_num(grade_level)
    schedules = []
    for index, strand in enumerate(ENROLLMENT_STRANDS):
        schedules.append({
            "id": f"{subject_code}-{strand}-{grade_num}-{semester}-{index + 1}",
            "slots": slots - index * 2,
            "section": f"{strand} {grade_num}-A",
            "dayTime": day_time or "MW 9:00AM-10:30AM",
        })
    return schedules


def build_enrollment_subjects_catalog():
    catalog = []
    for grade_level, semesters in ENROLLMENT_CURRICULUM.items():
        for semester, config in semesters.items():
            for category, subject_type in (
                ("core", "core"),
                ("applied", "applied"),
            ):
                for item in config.get(category, []):
                    catalog.append({
                        **item,
                        "gradeLevel": grade_level,
                        "semester": semester,
                        "strand": None,
                        "type": subject_type,
                        "schedules": _build_strand_schedules(
                            grade_level, semester, item["code"], item.get("dayTime"), 28
                        ),
                    })
            for strand, specs in config.get("specialized", {}).items():
                grade_num = _grade_num(grade_level)
                for spec in specs:
                    catalog.append({
                        **spec,
                        "gradeLevel": grade_level,
                        "semester": semester,
                        "strand": strand,
                        "type": "specialized",
                        "schedules": [{
                            "id": f"{spec['code']}-{strand}-{grade_num}-{semester}",
                            "slots": 25,
                            "section": f"{strand} {grade_num}-A",
                            "dayTime": spec.get("dayTime") or "TTh 1:00PM-2:30PM",
                        }],
                    })
    return catalog


ENROLLMENT_SUBJECTS_DEMO = build_enrollment_subjects_catalog()


def subjects_for_term(strand_code, grade_level, semester_code):
    """All subjects a student must take for grade/semester/strand."""
    code = (strand_code or "STEM").upper()
    result = []
    config = ENROLLMENT_CURRICULUM.get(grade_level, {}).get(semester_code, {})
    for item in config.get("core", []) + config.get("applied", []):
        result.append({**item, "strand": None, "type": "core"})
    for item in config.get("specialized", {}).get(code, []):
        result.append({**item, "strand": code, "type": "specialized"})
    return result


def required_subjects_count(strand_code, grade_level, semester_code):
    return len(subjects_for_term(strand_code, grade_level, semester_code))


def _build_required_subjects_per_term():
    counts = {}
    for grade_level, semesters in ENROLLMENT_CURRICULUM.items():
        counts[grade_level] = {}
        for semester_code in semesters:
            counts[grade_level][semester_code] = {
                strand: required_subjects_count(strand, grade_level, semester_code)
                for strand in ENROLLMENT_STRANDS
            }
    return counts


REQUIRED_SUBJECTS_PER_TERM = _build_required_subjects_per_term()


def section_matches_student(section_name, strand_code, grade_level):
    section = (section_name or "").upper()
    code = (strand_code or "STEM").upper()
    if not section.startswith(code):
        return False
    if grade_level:
        grade_num = _grade_num(grade_level)
        if grade_num not in section:
            return False
    return True


def filter_demo_subjects_by_strand(strand_code, grade_level="Grade 12", semester_code="1st"):
    code = (strand_code or "STEM").upper()
    subjects = []
    for subj in ENROLLMENT_SUBJECTS_DEMO:
        if grade_level and subj.get("gradeLevel") and subj["gradeLevel"] != grade_level:
            continue
        if semester_code and subj.get("semester") and subj["semester"] != semester_code:
            continue
        sub_strand = subj.get("strand")
        if sub_strand is not None and str(sub_strand).upper() != code:
            continue
        schedules = [
            schedule for schedule in subj.get("schedules", [])
            if section_matches_student(schedule.get("section"), code, grade_level)
        ]
        if not schedules:
            continue
        subjects.append({**subj, "schedules": schedules})
    return subjects
