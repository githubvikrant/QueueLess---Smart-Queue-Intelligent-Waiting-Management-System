"""Ek command: python seed.py  -> CityCare demo data DB me load (purana data saaf)."""
from app.db.session import SessionLocal, init_db
from app.seeding.seeder import reseed

if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        print("Seeded:", reseed(db))
