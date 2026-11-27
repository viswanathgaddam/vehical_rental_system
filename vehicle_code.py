import sqlite3
from datetime import date
from pathlib import Path


DB_PATH = Path(__file__).with_name("vehicle_rental.db")


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory =sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                make TEXT NOT NULL,
                model TEXT NOT NULL,R
                vehicle_type TEXT NOT NULL DEFAULT 'Car',
                registration_no TEXT NOT NULL DEFAULT '',
                year INTEGER NOT NULL CHECK (year >= 1886),
                daily_rate REAL NOT NULL CHECK (daily_rate > 0),
                available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                start_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT,
                total_cost REAL,
                CHECK (due_date >= start_date)
            );
        """)
        # Add the new fields to databases made by an earlier version.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(vehicles)")}
        if "vehicle_type" not in columns:
            db.execute("ALTER TABLE vehicles ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT 'Car'")
        if "registration_no" not in columns:
            db.execute("ALTER TABLE vehicles ADD COLUMN registration_no TEXT NOT NULL DEFAULT ''")


def prompt_int(label, minimum=None):
    while True:
        try:
            value = int(input(label).strip())
            if minimum is not None and value < minimum:
                print(f"Enter a number of at least {minimum}.")
                continue
            return value
        except ValueError:
            print("Please enter a whole number.")


def prompt_rate():
    while True:
        try:
            value = float(input("Daily rental rate: ").strip())
            if value <= 0:
                print("Rate must be greater than zero.")
                continue
            return value
        except ValueError:
            print("Please enter a valid amount, such as 35.00.")


def list_vehicles(available_only=False):
    with connect() as db:
        query = "SELECT * FROM vehicles"
        if available_only:
            query += " WHERE available = 1"
        rows = db.execute(query + " ORDER BY id").fetchall()
    if not rows:
        print("No vehicles found.")
        return
    print("\nID  Type       Make/Model                 Plate       Year  Rate/day  Status")
    print("-" * 82)
    for v in rows:
        status = "Available" if v["available"] else "Rented"
        print(f"{v['id']:<3} {v['vehicle_type']:<10} {v['make']} {v['model']:<17} "
              f"{v['registration_no']:<11} {v['year']:<5} ${v['daily_rate']:<8.2f} {status}")


def add_vehicle():
    vehicle_type = input("Vehicle type (car, van, bike, etc.): ").strip()
    make = input("Make: ").strip()
    model = input("Model: ").strip()
    registration_no = input("Registration number: ").strip()
    if not vehicle_type or not make or not model or not registration_no:
        print("Vehicle type, make, model, and registration number are required.")
        return
    year = prompt_int("Year: ", 1886)
    rate = prompt_rate()
    with connect() as db:
        db.execute("""INSERT INTO vehicles
                      (vehicle_type, make, model, registration_no, year, daily_rate)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (vehicle_type, make, model, registration_no, year, rate))
    print("Vehicle added.")


def rent_vehicle():
    list_vehicles(available_only=True)
    vehicle_id = prompt_int("Vehicle ID to rent (0 to cancel): ", 0)
    if vehicle_id == 0:
        return
    customer = input("Customer name: ").strip()
    phone = input("Customer phone: ").strip()
    if not customer or not phone:
        print("Customer name and phone are required.")
        return
    try:
        start = date.fromisoformat(input("Start date (YYYY-MM-DD): ").strip())
        due = date.fromisoformat(input("Due date (YYYY-MM-DD): ").strip())
        if due < start:
            print("Due date cannot be before the start date.")
            return
    except ValueError:
        print("Enter dates in YYYY-MM-DD format.")
        return

    with connect() as db:
        vehicle = db.execute("SELECT * FROM vehicles WHERE id = ? AND available = 1", (vehicle_id,)).fetchone()
        if vehicle is None:
            print("That vehicle is unavailable or does not exist.")
            return
        db.execute("""INSERT INTO rentals (vehicle_id, customer_name, phone, start_date, due_date)
                      VALUES (?, ?, ?, ?, ?)""",
                   (vehicle_id, customer, phone, start.isoformat(), due.isoformat()))
        db.execute("UPDATE vehicles SET available = 0 WHERE id = ?", (vehicle_id,))
    print("Rental created.")


def show_active_rentals():
    with connect() as db:
        rows = db.execute("""SELECT r.*, v.make, v.model, v.daily_rate
                             FROM rentals r JOIN vehicles v ON v.id = r.vehicle_id
                             WHERE r.returned_date IS NULL ORDER BY r.id""").fetchall()
    if not rows:
        print("No active rentals.")
        return
    print("\nRental  Vehicle                 Customer          Start       Due")
    print("-" * 78)
    for r in rows:
        print(f"{r['id']:<7} {r['make']} {r['model']:<15} {r['customer_name']:<17} {r['start_date']}  {r['due_date']}")


def return_vehicle():
    show_active_rentals()
    rental_id = prompt_int("Rental ID to return (0 to cancel): ", 0)
    if rental_id == 0:
        return
    try:
        returned = date.fromisoformat(input("Return date (YYYY-MM-DD): ").strip())
    except ValueError:
        print("Enter the date in YYYY-MM-DD format.")
        return
    with connect() as db:
        rental = db.execute("""SELECT r.*, v.daily_rate FROM rentals r
                               JOIN vehicles v ON v.id = r.vehicle_id
                               WHERE r.id = ? AND r.returned_date IS NULL""", (rental_id,)).fetchone()
        if rental is None:
            print("Active rental not found.")
            return
        start = date.fromisoformat(rental["start_date"])
        if returned < start:
            print("Return date cannot be before the rental start date.")
            return
        # Count the pickup day as a rental day; a same-day rental costs one day.
        days = max(1, (returned - start).days + 1)
        cost = days * rental["daily_rate"]
        db.execute("UPDATE rentals SET returned_date = ?, total_cost = ? WHERE id = ?",
                   (returned.isoformat(), cost, rental_id))
        db.execute("UPDATE vehicles SET available = 1 WHERE id = ?", (rental["vehicle_id"],))
    print(f"Vehicle returned. Rental duration: {days} day(s). Total: ${cost:.2f}")


def rental_history():
    with connect() as db:
        rows = db.execute("""SELECT r.*, v.make, v.model FROM rentals r
                             JOIN vehicles v ON v.id = r.vehicle_id ORDER BY r.id DESC""").fetchall()
    if not rows:
        print("No rental history.")
        return
    for r in rows:
        status = f"Returned {r['returned_date']} | Total ${r['total_cost']:.2f}" if r["returned_date"] else "Active"
        print(f"#{r['id']} {r['make']} {r['model']} | {r['customer_name']} ({r['phone']}) | "
              f"{r['start_date']} to {r['due_date']} | {status}")


def main():
    initialize_database()
    actions = {
        "1": ("List all vehicles", lambda: list_vehicles()),
        "2": ("List available vehicles", lambda: list_vehicles(True)),
        "3": ("Add a vehicle", add_vehicle),
        "4": ("Rent a vehicle", rent_vehicle),
        "5": ("Return a vehicle", return_vehicle),
        "6": ("View rental history", rental_history),
    }
    while True:
        print("\n=== Vehicle Rental Management ===")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        print("0. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye!")
            break
        action = actions.get(choice)
        if action:
            action[1]()
        else:
            print("Choose one of the listed options.")


if __name__ == "__main__":
    main()
