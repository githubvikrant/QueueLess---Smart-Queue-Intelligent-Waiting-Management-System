"""CityCare clinic demo data. Yahan badlo, seed script khud utha lega."""

SERVICES = [
    # code, name, avg minutes
    ("blood_test", "Blood Test", 6),
    ("ecg", "ECG", 8),
    ("consultation", "General Consultation", 10),
]

COUNTERS = [
    # code, name, services
    ("A", "Counter A", ["blood_test", "ecg", "consultation"]),
    ("B", "Counter B", ["blood_test", "ecg"]),  # consultation nahi karta
]

# code, patient, service, counter, status, priority
TOKENS = [
    ("Q101", "Anita Sharma", "consultation", "A", "in_service", 0),
    ("Q102", "Rahul Verma", "ecg", "B", "in_service", 0),
    ("Q103", "Meera Iyer", "blood_test", "A", "waiting", 0),
    ("Q104", "Imran Khan", "ecg", "B", "waiting", 0),
    ("Q105", "Sunita Devi", "blood_test", "B", "waiting", 0),
    ("Q106", "Arjun Singh", "consultation", "A", "waiting", 0),
    ("Q107", "Pooja Gupta", "blood_test", "B", "waiting", 0),
    ("Q108", "Karan Mehta", "ecg", "B", "waiting", 0),
    ("Q109", "Neha Reddy", "blood_test", "A", "waiting", 0),
    ("Q110", "Vikram Joshi", "blood_test", "B", "waiting", 0),
    ("Q111", "Farah Ali", "ecg", "B", "waiting", 0),
    ("Q112", "Suresh Patel", "consultation", "A", "waiting", 0),
]

WALK_IN_NAMES = [
    "Deepak Rao", "Lata Mishra", "Ishaan Bose", "Zoya Khan", "Mohan Das",
    "Priya Nair", "Harsh Vora", "Kavita Joshi", "Rohit Saini", "Tanvi Shah",
]
