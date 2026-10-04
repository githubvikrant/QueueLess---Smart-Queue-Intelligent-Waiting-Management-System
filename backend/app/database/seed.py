"""
Seed data loader for CityCare Diagnostic Centre demo.

This module loads the initial demo state for the hackathon:
- 3 service types (Blood Test, ECG, Consultation)
- 2 counters (Counter A, Counter B)
- 12 tokens in various states (WAITING, IN_SERVICE, etc.)

PURPOSE: Initialize database with CityCare demo data for hackathon presentation
DEPENDENCIES: sqlalchemy, app.database.db, app.database.models, datetime
SIDE EFFECTS: Drops and recreates all tables, inserts demo data
USAGE: Run with: python -m app.database.seed
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database.db import engine, SessionLocal, Base, init_db
from app.database.models import ServiceType, Counter, Token


def seed_database():
    """
    PURPOSE: Populate database with CityCare demo data
    
    WORKFLOW:
        1. Drop all existing tables and recreate them (clean slate)
        2. Create 3 service types with duration statistics
        3. Create 2 counters with their supported services
        4. Create 12 tokens in the correct demo state at 10:00 AM
        5. Print confirmation message
    
    DEPENDENCIES: init_db(), SQLAlchemy models
    SIDE EFFECTS: Modifies database, overwrites existing data
    
    DEMO STATE (10:00 AM):
        - Counter A: BUSY, serving Q101 (Blood Test), free at 10:06
        - Counter B: AVAILABLE, idle
        - Q101: IN_SERVICE at Counter A
        - Q102-Q112: WAITING in queue
        - Q103: Bottleneck demo token (Blood Test, long wait)
        - Q104: No-show demo token (ECG, will be called at 10:20)
        - Q108: Late appointment (Consultation, appointment 10:10, arrives 10:15)
    """
    print("Seeding CityCare demo data...")
    
    # Initialize database (drops and recreates tables)
    init_db()
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Demo start time: 10:00 AM
        demo_start = datetime(2025, 1, 1, 10, 0, 0)
        
        # ===== STEP 1: Create Service Types =====
        print("Creating service types...")
        
        service_types = [
            ServiceType(
                name="Blood Test",
                avg_duration_min=6.0,
                spread_min=1.5,
                recent_durations=[5.5, 6.0, 6.5, 5.8, 6.2]
            ),
            ServiceType(
                name="ECG",
                avg_duration_min=8.0,
                spread_min=2.0,
                recent_durations=[7.5, 8.0, 8.5, 7.8, 8.2]
            ),
            ServiceType(
                name="Consultation",
                avg_duration_min=10.0,
                spread_min=2.5,
                recent_durations=[9.5, 10.0, 10.5, 9.8, 10.2]
            )
        ]
        
        db.add_all(service_types)
        db.commit()
        
        # Get service type IDs for reference
        blood_test = db.query(ServiceType).filter_by(name="Blood Test").first()
        ecg = db.query(ServiceType).filter_by(name="ECG").first()
        consultation = db.query(ServiceType).filter_by(name="Consultation").first()
        
        # ===== STEP 2: Create Counters =====
        print("Creating counters...")
        
        counters = [
            Counter(
                id="A",
                name="Counter A",
                status="BUSY",
                supported_services=["Blood Test", "Consultation"],
                current_token_id="Q101",
                expected_free_at=demo_start + timedelta(minutes=6)  # 10:06 AM
            ),
            Counter(
                id="B",
                name="Counter B",
                status="AVAILABLE",
                supported_services=["Blood Test", "ECG"],
                current_token_id=None,
                expected_free_at=demo_start  # 10:00 AM (now)
            )
        ]
        
        db.add_all(counters)
        db.commit()
        
        # ===== STEP 3: Create Tokens =====
        print("Creating tokens...")
        
        tokens = [
            # Q101: Currently being served at Counter A
            Token(
                id="Q101",
                service_id=blood_test.id,
                kind="WALK_IN",
                priority_class=0,
                status="IN_SERVICE",
                assigned_counter_id="A",
                created_at=demo_start - timedelta(minutes=5),  # Created at 9:55
                called_at=demo_start - timedelta(minutes=5),
                eta_expected=demo_start + timedelta(minutes=1),  # Will complete at 10:01
                eta_reason="Currently in service at Counter A"
            ),
            
            # Q102: First in waiting queue
            Token(
                id="Q102",
                service_id=consultation.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start - timedelta(minutes=4),
                eta_reason="Waiting for Counter A (supports Consultation)"
            ),
            
            # Q103: Bottleneck demo token (Blood Test, long wait)
            Token(
                id="Q103",
                service_id=blood_test.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start - timedelta(minutes=3),
                eta_reason="Bottleneck demo - should be reassigned to Counter B"
            ),
            
            # Q104: No-show demo token (ECG, will be called at 10:20)
            Token(
                id="Q104",
                service_id=ecg.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start - timedelta(minutes=2),
                eta_reason="No-show demo - will be marked as no-show in demo"
            ),
            
            # Q105-Q112: Additional waiting patients
            Token(
                id="Q105",
                service_id=consultation.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start - timedelta(minutes=1),
                eta_reason="Waiting in queue"
            ),
            Token(
                id="Q106",
                service_id=blood_test.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start,
                eta_reason="Waiting in queue"
            ),
            Token(
                id="Q107",
                service_id=ecg.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start,
                eta_reason="Waiting in queue"
            ),
            # Q108: Late appointment (appointment 10:10, arrives 10:15)
            Token(
                id="Q108",
                service_id=consultation.id,
                kind="APPOINTMENT",
                appointment_time=demo_start + timedelta(minutes=10),  # 10:10 AM
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start + timedelta(minutes=5),  # Arrives at 10:05
                eta_reason="Late appointment demo - grace period applies"
            ),
            Token(
                id="Q109",
                service_id=blood_test.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start + timedelta(minutes=6),
                eta_reason="Waiting in queue"
            ),
            Token(
                id="Q110",
                service_id=ecg.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start + timedelta(minutes=7),
                eta_reason="Waiting in queue"
            ),
            Token(
                id="Q111",
                service_id=consultation.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start + timedelta(minutes=8),
                eta_reason="Waiting in queue"
            ),
            Token(
                id="Q112",
                service_id=blood_test.id,
                kind="WALK_IN",
                priority_class=0,
                status="WAITING",
                assigned_counter_id=None,
                created_at=demo_start + timedelta(minutes=9),
                eta_reason="Waiting in queue"
            )
        ]
        
        db.add_all(tokens)
        db.commit()
        
        # ===== CONFIRMATION =====
        print("\n✓ Database seeded successfully!")
        print(f"  - {len(service_types)} service types created")
        print(f"  - {len(counters)} counters created")
        print(f"  - {len(tokens)} tokens created")
        print("\nDemo state at 10:00 AM:")
        print("  - Counter A: BUSY (serving Q101)")
        print("  - Counter B: AVAILABLE")
        print("  - 11 tokens waiting (Q102-Q112)")
        print("  - Q103: Bottleneck demo token")
        print("  - Q104: No-show demo token")
        print("  - Q108: Late appointment token")
        
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    """
    PURPOSE: Allow script to be run directly from command line
    
    USAGE: python -m app.database.seed
    """
    seed_database()
